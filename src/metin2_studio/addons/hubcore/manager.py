"""Transactional composition and installation of explicitly reviewed add-ons.

The backend decides whether a target may be written and builds physical packs.
The manager owns baselines, desired state, hashes, ownership and crash recovery.
No live target is modified by inspection or planning.
"""
from __future__ import annotations

import copy
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from metin2_studio.filesystem import retry_windows_lock

from .packages import COMMON_INIT, SHA_RE, Package, PackageError, confined_file, discover_packages, logical_path, load_package, sha256

VERSION = "0.10.0-alpha.1"
CONFIG_PATH = "m2hub_config.py"


def _display_order(ident):
    return (ident != 'community.addon-menu', ident)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hashes(files: dict[str, bytes]) -> dict[str, str]:
    return {name: sha256(content) for name, content in sorted(files.items())}


def _json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Cannot read Hub state %s: %s" % (path, exc)) from exc


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".hub-" + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        retry_windows_lock(os.replace, temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_json(path: Path, data: Any) -> None:
    _atomic_bytes(path, (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8"))


def _logical_key(name: Any) -> str:
    # Client packs contain virtual names such as d:/ymir work/... . These keys
    # are never filesystem paths: only their SHA-addressed bytes are persisted.
    if not isinstance(name, str) or not name or len(name) > 2048 or any(ord(c) < 32 for c in name):
        raise ValueError("Backend returned an invalid logical pack name.")
    return name


def _snapshot(data: Any, label: str) -> dict[str, bytes]:
    if not isinstance(data, dict):
        raise ValueError("Backend %s must return a file dictionary." % label)
    result: dict[str, bytes] = {}
    seen: set[str] = set()
    for name, content in data.items():
        name = _logical_key(name) if label == "snapshot" else logical_path(name)
        if name.casefold() in seen:
            raise ValueError("Backend %s contains a Windows case collision: %s" % (label, name))
        if not isinstance(content, bytes):
            raise ValueError("Backend %s content must be bytes: %s" % (label, name))
        seen.add(name.casefold())
        result[name] = content
    return result


class Manager:
    def __init__(self, state_dir: str | Path, catalog_dir: str | Path, backend_factory, catalog_provider=None):
        self.state_dir = Path(state_dir).resolve()
        self.catalog_dir = Path(catalog_dir).resolve()
        self.catalog_provider = catalog_provider or (lambda: discover_packages(self.catalog_dir))
        self.backend_factory = backend_factory
        self._lock = threading.RLock()
        self._backend = None
        self._target_dir: Path | None = None
        self._pending: dict | None = None
        self._generation = 0
        self._connection_error: str | None = None
        connection = _json(self.state_dir / "connection.json", {})
        if connection.get("path"):
            try:
                self._select(connection["path"])
            except Exception as exc:
                self._connection_error = "Previous installation could not be opened: %s" % exc

    def _select(self, path: str | Path) -> None:
        backend = self.backend_factory(str(Path(path).resolve()))
        root = Path(backend.target_root).resolve()
        profile = backend.profile()
        if not isinstance(profile, dict) or profile.get("kind") not in ("sandbox", "installation", "test-client"):
            raise ValueError("Backend must describe an installation or owned test target profile.")
        key = sha256(os.path.normcase(str(root)).encode("utf-8"))[:24]
        self._backend = backend
        self._target_dir = self.state_dir / "targets" / key
        self._connection_error = None

    def _require(self):
        if self._backend is None or self._target_dir is None:
            raise ValueError("Connect this world's game client in Add-on settings first.")
        return self._backend

    @property
    def _state_path(self) -> Path:
        self._require()
        return self._target_dir / "state.json"

    @property
    def _journal_path(self) -> Path:
        self._require()
        return self._target_dir / "journal.json"

    def _stored(self) -> dict:
        state = _json(self._state_path, {"schema_version": 1, "installed": {}, "baseline": None,
                                          "baseline_physical": None, "logical_hashes": None, "physical_hashes": None})
        if state.get("schema_version") != 1 or not isinstance(state.get("installed"), dict):
            raise ValueError("Unsupported or corrupt installation state; preserve the Hub state directory for recovery.")
        return state

    def _invalidate(self) -> None:
        self._pending = None
        self._generation += 1

    def catalog_changed(self) -> None:
        with self._lock:
            self._invalidate()

    def connect(self, path: str | Path) -> dict:
        with self._lock:
            # Do not strand a physical transaction by switching its target.
            if self._backend is not None and self._journal_path.exists():
                raise ValueError("Recover the current installation before connecting another target.")
            self._select(path)
            _atomic_json(self.state_dir / "connection.json", {"path": str(self._backend.target_root)})
            self._invalidate()
            return self.state()

    def _installed_public(self, installed: dict, profile: dict | None = None) -> list[dict]:
        result = []
        for addon_id, record in sorted(installed.items(), key=lambda row: _display_order(row[0])):
            item = copy.deepcopy(record["manifest"])
            item.pop('distribution', None)
            item.update(id=addon_id, enabled=record["enabled"], installed=True,
                        settings=copy.deepcopy(record.get("settings", {})), package_digest=record.get("package_digest"))
            item.update(self._compatibility_info(record['manifest'], profile or {}))
            if record.get('distribution'):
                item['distribution'] = copy.deepcopy(record['distribution'])
            result.append(item)
        return result

    def state(self) -> dict:
        with self._lock:
            installation = None
            installed: dict = {}
            recovery = None
            warnings = []
            if self._backend is not None:
                installation = self._backend.profile()
                stored = self._stored()
                installed = stored["installed"]
                if not stored.get("baseline"):
                    warnings.append("Baseline has not been established. Existing customizations have unknown provenance.")
                if self._journal_path.exists():
                    journal = _json(self._journal_path)
                    recovery = {"id": journal["id"], "phase": journal.get("phase"),
                                "message": "An unfinished installation transaction requires recovery."}
            if self._connection_error:
                warnings.append(self._connection_error)
            integrity = self._integrity(stored) if self._backend is not None else None
            public_installed = self._installed_public(installed, installation)
            for item in public_installed:
                item['integrity'] = integrity['addons'].get(item['id'], {})
            return {"version": VERSION, "installation": installation,
                    "reference": copy.deepcopy(stored.get('reference')) if self._backend is not None else None,
                    "installed": public_installed, "integrity": integrity,
                    "pending_plan": copy.deepcopy(self._pending["public"]) if self._pending else None,
                    "game_update": self._game_update(stored) if self._backend is not None else None,
                    "recovery": recovery, "warnings": warnings}

    def _compatibility(self, manifest: dict, profile: dict) -> tuple[list[str], list[str]]:
        warnings = []
        compatibility = manifest.get("compatibility", {})
        fields = (("client_versions", "client_version", "client version"),
                  ("server_versions", "server_version", "server version"),
                  ("profile_ids", "profile_id", "client profile"))
        for field, profile_field, label in fields:
            expected = compatibility.get(field)
            actual = str(profile.get(profile_field) or '')
            if expected and str(actual) not in expected:
                declared = ', '.join(expected[:8]) + (' …' if len(expected) > 8 else '')
                warnings.append('%s: compatibility is unverified for %s %s. Publisher lists: %s. A different version or profile does not prove incompatibility; you can review and apply it to your supported game client.' % (manifest['name'], label, actual or 'unknown', declared))
        if not any(compatibility.get(field) for field, _, _ in fields):
            warnings.append('%s: compatibility is unverified because the publisher has not declared game versions or client profiles.' % manifest['name'])
        elif compatibility.get("experimental"):
            warnings.append('%s: compatibility is unverified; in-game play-testing has not been independently recorded.' % manifest['name'])
        # Version declarations record coverage, not observed failures. Concrete
        # pack/adapter, dependency and ownership checks remain blocking elsewhere.
        return [], warnings

    def _compatibility_info(self, manifest: dict, profile: dict) -> dict:
        _, warnings = self._compatibility(manifest, profile) if profile else ([], [])
        return {'compatibility_status': 'unverified' if warnings else 'declared' if profile else 'unknown',
                'warnings': warnings, 'errors': [], 'tested_in_game': False,
                'verification': 'In-game play-test has not been recorded by this manager.'}

    @staticmethod
    def _compatibility_target(profile: dict) -> tuple[str, ...]:
        return tuple(str(profile.get(key) or '') for key in ('client_version', 'server_version', 'profile_id'))

    def catalog(self) -> dict:
        with self._lock:
            packages, errors = self.catalog_provider()
            installed = self._stored()["installed"] if self._backend else {}
            profile = self._backend.profile() if self._backend else {}
            integrity = self._integrity(self._stored()) if self._backend else None
            items = []
            for addon_id, package in sorted(packages.items(), key=lambda row: _display_order(row[0])):
                item = package.metadata()
                item['bundled'] = package.path.resolve().is_relative_to(self.catalog_dir)
                record = installed.get(addon_id)
                item.update(installed=record is not None, enabled=bool(record and record["enabled"]),
                            installed_version=record["manifest"]["version"] if record else None,
                            update_available=bool(record and record.get("package_digest") != package.digest),
                            status="installed" if record else "available")
                item.update(self._compatibility_info(package.manifest, profile))
                if record:
                    item['integrity'] = integrity['addons'].get(addon_id, {})
                items.append(item)
            for item in errors:
                item.update(installed=False, enabled=False)
                items.append(item)
            return {"items": items, "count": len(items), "source": str(self.catalog_dir)}

    def _object(self, digest: str) -> Path:
        if not isinstance(digest, str) or not SHA_RE.fullmatch(digest):
            raise ValueError("Invalid content hash in Hub state.")
        return self._target_dir / "objects" / digest[:2] / digest

    def _read_object(self, digest: str) -> bytes:
        try:
            content = self._object(digest).read_bytes()
        except OSError as exc:
            raise ValueError("A saved baseline or add-on file is missing. Preserve Hub backups: %s" % digest) from exc
        if sha256(content) != digest:
            raise ValueError("A saved baseline or add-on file is corrupt: %s" % digest)
        return content

    def _put_object(self, content: bytes) -> str:
        digest = sha256(content)
        path = self._object(digest)
        if path.exists():
            if sha256(path.read_bytes()) != digest:
                raise ValueError("Hub content store is corrupt: %s" % digest)
        else:
            _atomic_bytes(path, content)
        return digest

    def _baseline(self, stored: dict, current: dict[str, bytes]) -> dict[str, bytes]:
        if not stored.get("baseline"):
            return dict(current)
        return {_logical_key(name): self._read_object(digest) for name, digest in stored["baseline"].items()}

    def _record(self, package: Package, previous: dict | None = None) -> dict:
        settings = copy.deepcopy(package.manifest.get("settings", {}))
        schema = package.manifest.get("settings_schema", {})
        for name, spec in schema.get("properties", {}).items() if isinstance(schema.get("properties", {}), dict) else []:
            if isinstance(spec, dict) and "default" in spec:
                settings.setdefault(name, copy.deepcopy(spec["default"]))
        if previous:
            settings.update(previous.get("settings", {}))
        return {"manifest": copy.deepcopy(package.manifest), "package_digest": package.digest,
                "file_hashes": _hashes(package.files), "enabled": previous["enabled"] if previous else True,
                "settings": settings, "distribution": copy.deepcopy(package.distribution)}

    def _validate_settings(self, manifest: dict, settings: Any) -> dict:
        if not isinstance(settings, dict):
            raise ValueError("Settings must be an object.")
        try:
            settings = json.loads(json.dumps(settings, allow_nan=False))
        except (TypeError, ValueError) as exc:
            raise ValueError("Settings must contain JSON-compatible values.") from exc

        def validate(value, spec, field):
            if not isinstance(spec, dict):
                raise ValueError("Invalid setting schema for %s." % field)
            kind = spec.get("type")
            valid = {"boolean": isinstance(value, bool),
                     "integer": isinstance(value, int) and not isinstance(value, bool),
                     "number": isinstance(value, (int, float)) and not isinstance(value, bool),
                     "string": isinstance(value, str), "array": isinstance(value, list),
                     "object": isinstance(value, dict), "null": value is None}
            if kind is not None and (kind not in valid or not valid[kind]):
                raise ValueError("Setting %s must have type %s." % (field, kind))
            if "enum" in spec and value not in spec["enum"]:
                raise ValueError("Setting %s is not an allowed value." % field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if "minimum" in spec and value < spec["minimum"]:
                    raise ValueError("Setting %s is below its minimum." % field)
                if "maximum" in spec and value > spec["maximum"]:
                    raise ValueError("Setting %s exceeds its maximum." % field)
            if isinstance(value, str):
                if len(value) < spec.get("minLength", 0) or len(value) > spec.get("maxLength", 16384):
                    raise ValueError("Setting %s has an unsupported string length." % field)
            if isinstance(value, list):
                if len(value) > spec.get("maxItems", 1024):
                    raise ValueError("Setting %s contains too many items." % field)
                for index, item in enumerate(value):
                    validate(item, spec.get("items", {}), "%s[%d]" % (field, index))
            if isinstance(value, dict):
                properties = spec.get("properties", {})
                for key, item in value.items():
                    if key not in properties:
                        raise ValueError("Unknown setting %s.%s." % (field, key))
                    validate(item, properties[key], "%s.%s" % (field, key))
                for key in spec.get("required", []):
                    if key not in value:
                        raise ValueError("Required setting %s.%s is missing." % (field, key))
        validate(settings, manifest.get("settings_schema", {"type": "object", "properties": {}}), manifest["id"])
        return settings

    def _desired_valid(self, desired: dict, profile: dict) -> tuple[list[str], list[str]]:
        conflicts, warnings = [], []
        for addon_id, record in desired.items():
            manifest = record["manifest"]
            problems, caution = self._compatibility(manifest, profile)
            conflicts.extend(problems)
            warnings.extend(caution)
            for required in manifest["requires"]:
                if required not in desired:
                    conflicts.append("%s requires %s. Install that add-on first." % (addon_id, required))
                elif record["enabled"] and not desired[required]["enabled"]:
                    conflicts.append("%s requires enabled add-on %s." % (addon_id, required))
                elif required in manifest.get('dependency_versions', {}):
                    from ..versions import satisfies
                    expression = manifest['dependency_versions'][required]
                    try:
                        supported = satisfies(desired[required]['manifest']['version'], expression)
                    except ValueError:
                        supported = False
                    if not supported:
                        conflicts.append('%s requires %s %s.' % (addon_id, required, expression))
            for other in manifest["conflicts"]:
                if other in desired:
                    conflicts.append("%s conflicts with installed add-on %s." % (addon_id, other))
        # Cycles cannot provide a stable initialization order.
        visiting, visited = set(), set()
        def visit(addon_id):
            if addon_id in visiting:
                conflicts.append("Dependency cycle includes %s." % addon_id)
                return
            if addon_id in visited:
                return
            visiting.add(addon_id)
            for required in desired[addon_id]["manifest"]["requires"]:
                if required in desired:
                    visit(required)
            visiting.remove(addon_id)
            visited.add(addon_id)
        for addon_id in sorted(desired):
            visit(addon_id)
        return sorted(set(conflicts)), sorted(set(warnings))

    def _ordered_ids(self, desired: dict) -> list[str]:
        result, visited = [], set()
        def visit(addon_id):
            if addon_id in visited:
                return
            visited.add(addon_id)
            for required in sorted(desired[addon_id]["manifest"]["requires"]):
                if required in desired:
                    visit(required)
            result.append(addon_id)
        for addon_id in sorted(desired):
            visit(addon_id)
        return result

    def _compose(self, baseline: dict[str, bytes], desired: dict, new_packages: dict[str, Package]) -> tuple[dict[str, bytes], list[str]]:
        result = dict(baseline)
        conflicts = []
        owners: dict[str, str] = {}
        baseline_names = {name.casefold(): name for name in baseline}
        if CONFIG_PATH.casefold() in baseline_names:
            conflicts.append("The original installation already contains m2hub_config.py with unknown ownership. Review the existing integration and its ownership before applying.")
        for addon_id in sorted(desired):
            record = desired[addon_id]
            package = new_packages.get(addon_id)
            for target, digest in sorted(record["file_hashes"].items()):
                target = logical_path(target)
                if not target.startswith("m2hub_addons/"):
                    raise ValueError("Installed file escapes add-on namespace: %s" % target)
                if target == COMMON_INIT:
                    continue  # The manager preserves the common namespace.
                key = target.casefold()
                content = package.files[target] if package else self._read_object(digest)
                if sha256(content) != digest:
                    raise ValueError("Add-on file changed during composition: %s" % target)
                shared_init = target.endswith("/__init__.py")
                if key in baseline_names:
                    if shared_init and baseline[baseline_names[key]] == content:
                        continue
                    conflicts.append("%s would overwrite existing baseline file %s with unknown ownership." % (addon_id, baseline_names[key]))
                    continue
                if key in owners:
                    existing_name = next(name for name in result if name.casefold() == key)
                    if shared_init and result[existing_name] == content:
                        continue
                    conflicts.append("%s and %s both own %s." % (owners[key], addon_id, target))
                    continue
                owners[key] = addon_id
                result[target] = content
        if desired:
            if COMMON_INIT.casefold() not in baseline_names:
                result[COMMON_INIT] = b""
            addons = [{"id": addon_id, "name": desired[addon_id]['manifest']['name'],
                       "version": desired[addon_id]['manifest']['version'],
                       "entry": desired[addon_id]["manifest"]["entry"],
                       "api_version": desired[addon_id]['manifest'].get('api_version', 1),
                       "capabilities": desired[addon_id]['manifest']['capabilities'],
                       "settings": desired[addon_id].get("settings", {})}
                      for addon_id in self._ordered_ids(desired) if desired[addon_id]["enabled"]]
            # ASCII escapes keep configuration compatible with legacy embedded Python.
            text = "# Generated by Metin2 Add-on Hub.\nHUB_VERSION = %r\nADDONS = %s\n" % (VERSION, ascii(addons))
            installed = [{'id': addon_id, 'name': record['manifest']['name'], 'version': record['manifest']['version'],
                          'enabled': record['enabled'], 'capabilities': record['manifest']['capabilities']}
                         for addon_id, record in sorted(desired.items())]
            text += 'INSTALLED_ADDONS = %s\n' % ascii(installed)
            result[CONFIG_PATH] = text.encode("ascii")
        return result, sorted(set(conflicts))

    def _drift(self, stored: dict, logical: dict, physical: dict) -> list[str]:
        conflicts = []
        for label, expected, actual in (("logical pack", stored.get("logical_hashes"), _hashes(logical)),
                                        ("physical installation", stored.get("physical_hashes"), _hashes(physical))):
            if expected is not None and expected != actual:
                changed = sorted(name for name in set(expected) | set(actual) if expected.get(name) != actual.get(name))
                conflicts.append("External changes detected in %s: %s. Resolve these changes before applying add-ons." % (label, ", ".join(changed[:12])))
        return conflicts

    def _game_update(self, stored: dict, logical=None, physical=None):
        backend = self._require()
        clean = getattr(backend, 'is_clean_game_baseline', None)
        if not stored.get('baseline') or not callable(clean):
            return None
        try:
            physical = physical if physical is not None else _snapshot(backend.physical_snapshot(), 'physical_snapshot')
            if _hashes(physical) == stored.get('physical_hashes'):
                return None
            logical = logical if logical is not None else _snapshot(backend.snapshot(), 'snapshot')
            if not clean(logical):
                return None
        except (ValueError, OSError):
            return None
        return {'detected': True, 'reapply_available': bool(stored['installed']),
                'message': 'The client packs were replaced outside Studio, for example by a game update. Current game files take priority. Review reapplying add-ons against this new baseline; old game packs will not be restored.'}

    @staticmethod
    def _repairable(stored: dict, logical: dict) -> bool:
        """Only restore deleted owned files or hooks reverted to their known baseline."""
        expected, baseline = stored.get('logical_hashes'), stored.get('baseline')
        if not expected or baseline is None:
            return False
        actual = _hashes(logical)
        changed = {name for name in set(expected) | set(actual) if expected.get(name) != actual.get(name)}
        return bool(changed) and all(name in expected and expected[name] != baseline.get(name)
                                     and actual.get(name) == baseline.get(name) for name in changed)

    def _integrity(self, stored: dict) -> dict:
        """Inspect current bytes independently of saved enabled/installed preferences."""
        result = {'status': 'healthy', 'message': 'Installed add-on files match the last successful apply.',
                  'repair_available': False, 'repair_action': None, 'addons': {},
                  'missing_files': [], 'changed_files': []}
        installed = stored['installed']
        if not installed:
            result.update(status='empty', message='No add-ons are installed on this client.')
            return result
        expected = stored.get('logical_hashes')
        if not expected or not stored.get('physical_hashes'):
            result.update(status='unverified', message='Installed add-on files have no recorded fingerprints. Review this installation.')
        else:
            try:
                backend = self._require()
                physical = _snapshot(backend.physical_snapshot(), 'physical_snapshot')
                if set(stored['physical_hashes']) - set(physical):
                    raise ValueError('Managed client pack files are missing.')
                if _hashes(physical) != stored['physical_hashes']:
                    logical = _snapshot(backend.snapshot(), 'snapshot')
                    actual = _hashes(logical)
                    result['missing_files'] = sorted(set(expected) - set(actual))
                    result['changed_files'] = sorted(name for name in set(expected) | set(actual)
                                                     if name in actual and expected.get(name) != actual[name])
                    update = self._game_update(stored, logical, physical)
                    repairable = self._repairable(stored, logical)
                    if update:
                        result.update(status='missing', repair_available=True, repair_action='reapply',
                                      message='The game client packs were replaced. Your saved add-ons need reinstalling on the updated client.')
                    elif repairable:
                        result.update(status='missing', repair_available=True, repair_action='repair',
                                      message='Add-on files or loading hooks are missing. Review reinstalling your saved add-ons.')
                    elif actual != expected:
                        result.update(status='changed', message='Client files changed outside Studio. Review the affected files before repairing add-ons.')
                    else:
                        result.update(status='changed', message='The client packs were repacked outside Studio. Review these changes before applying add-ons.')
            except (ValueError, OSError) as error:
                result.update(status='unavailable', message='Client packs could not be verified. Repair or finish updating the game client, then check again.',
                              detail=str(error))
        payloads = {name for record in installed.values() for name in record['file_hashes']}
        shared = {name for name, value in (expected or {}).items()
                  if value != (stored.get('baseline') or {}).get(name) and name not in payloads}
        shared.update(name for name in (COMMON_INIT, CONFIG_PATH) if name in (expected or {}))
        missing, changed = set(result['missing_files']), set(result['changed_files'])
        for addon_id, record in installed.items():
            required = set(record['file_hashes']) | shared
            absent, modified = sorted(required & missing), sorted(required & changed)
            status = result['status'] if result['status'] in ('unavailable', 'unverified') else 'missing' if absent or modified and result['status'] == 'missing' else 'changed' if modified else 'healthy'
            result['addons'][addon_id] = {'status': status, 'missing_files': absent, 'changed_files': modified}
        return result

    def plan_batch(self, addon_ids: list[str]) -> dict:
        if (not isinstance(addon_ids, list) or not 1 <= len(addon_ids) <= 100
                or any(not isinstance(ident, str) or not ident for ident in addon_ids)
                or len(set(addon_ids)) != len(addon_ids)):
            raise ValueError('Select between 1 and 100 distinct add-ons for this batch.')
        return self.plan(addon_ids[0], 'batch', addon_ids=addon_ids)

    def plan(self, addon_id: str, action: str = "install", settings: dict | None = None, *, addon_ids=None) -> dict:
        with self._lock:
            backend = self._require()
            if self._journal_path.exists():
                raise ValueError("Recover the unfinished transaction before planning another change.")
            if action not in ("install", "remove", "enable", "disable", "update", "configure", "refresh-data", "reapply", "repair", "batch"):
                raise ValueError("Unsupported action: %s" % action)
            if not isinstance(addon_id, str):
                raise ValueError("addon_id must be a string.")
            packages, errors = self.catalog_provider()
            stored = self._stored()
            desired = copy.deepcopy(stored["installed"])
            new_packages: dict[str, Package] = {}
            batch = []
            if action == 'batch':
                if (not isinstance(addon_ids, list) or not 1 <= len(addon_ids) <= 100
                        or any(not isinstance(ident, str) or not ident for ident in addon_ids)
                        or len(set(addon_ids)) != len(addon_ids)):
                    raise ValueError('Select between 1 and 100 distinct add-ons for this batch.')
                for ident in addon_ids:
                    if ident not in packages:
                        raise ValueError('Add-on %s is unavailable or invalid. Inspect catalog validation errors.' % ident)
                    package, previous = packages[ident], desired.get(ident)
                    operation = 'install' if previous is None else 'update' if previous.get('package_digest') != package.digest else 'keep'
                    if operation != 'keep':
                        new_packages[ident] = package
                        desired[ident] = self._record(package, previous)
                    batch.append({'addon_id': ident, 'name': package.manifest['name'], 'action': operation,
                                  'before_version': previous['manifest']['version'] if previous else None,
                                  'version': package.manifest['version'], 'enabled': desired[ident]['enabled']})
            elif action in ("install", "update"):
                if addon_id not in packages:
                    raise ValueError("Add-on %s is unavailable or invalid. Inspect catalog validation errors." % addon_id)
                if action == "install" and addon_id in desired:
                    raise ValueError("%s is already installed; choose update, enable or disable." % addon_id)
                if action == "update" and addon_id not in desired:
                    raise ValueError("%s is not installed." % addon_id)
                package = packages[addon_id]
                if action == "update" and desired[addon_id].get("package_digest") == package.digest:
                    raise ValueError("%s already matches this catalog release." % addon_id)
                new_packages[addon_id] = package
                desired[addon_id] = self._record(package, desired.get(addon_id))
            else:
                if addon_id not in desired:
                    raise ValueError("%s is not installed." % addon_id)
                if action == "remove":
                    del desired[addon_id]
                elif action in ("enable", "disable"):
                    enabled = action == "enable"
                    if desired[addon_id]["enabled"] == enabled:
                        raise ValueError("%s is already %s." % (addon_id, "enabled" if enabled else "disabled"))
                    desired[addon_id]["enabled"] = enabled
            if action == "configure" and settings is None:
                raise ValueError("Provide settings to configure this add-on.")
            if settings is not None:
                if action not in ("configure", "install", "update"):
                    raise ValueError("Settings can only be supplied for configure, install or update.")
                if not isinstance(settings, dict):
                    raise ValueError("Settings must be an object.")
                merged = dict(desired[addon_id].get("settings", {}))
                merged.update(settings)
                desired[addon_id]["settings"] = self._validate_settings(desired[addon_id]["manifest"], merged)
            if action == "configure" and desired[addon_id]["settings"] == stored["installed"][addon_id]["settings"]:
                raise ValueError("These settings already match the installed configuration.")
            if action == 'refresh-data' and (not desired[addon_id]['enabled'] or 'knowledge.read' not in desired[addon_id]['manifest']['capabilities']):
                raise ValueError('Reference refresh needs an enabled reference-data add-on.')
            logical = _snapshot(backend.snapshot(), "snapshot")
            physical = _snapshot(backend.physical_snapshot(), "physical_snapshot")
            game_update = self._game_update(stored, logical, physical)
            if action == 'reapply' and not game_update:
                raise ValueError('No clean game-client update is awaiting an add-on review.')
            if action == 'repair' and (game_update or not self._repairable(stored, logical)):
                raise ValueError('This client needs a fresh installation check. Only missing owned add-on files and reverted loading hooks can be repaired here.')
            baseline = dict(logical) if game_update else self._baseline(stored, logical)
            profile = backend.profile()
            conflicts, warnings = self._desired_valid(desired, profile)
            if game_update:
                warnings.append(game_update['message'])
            elif action != 'repair' and not (action == 'batch' and self._repairable(stored, logical)):
                conflicts.extend(self._drift(stored, logical, physical))
            if action == 'repair':
                warnings.append('Reinstall restores the recorded add-on files, loading hooks and settings.')
            blockers = getattr(backend, 'mutation_blockers', None)
            if profile.get('writable') and callable(blockers):
                conflicts.extend(blockers())
            composed, ownership_conflicts = self._compose(baseline, desired, new_packages)
            conflicts.extend(ownership_conflicts)
            preview = getattr(backend, "preview", None)
            reviewed_files = _snapshot(preview(dict(composed)), "snapshot") if callable(preview) else composed
            if callable(preview):
                warnings.append("This logical preview includes generated framework and bootstrap files.")
            if not stored.get("baseline"):
                warnings.append("Existing customizations have unknown provenance. The initial successful apply records this installation as its baseline.")
            if not profile.get("writable"):
                conflicts.append(profile.get('details', {}).get('read_only_reason') or 'This target is read-only. Check its client integration and ownership in Add-on settings.')
            changes = []
            for name in sorted(set(logical) | set(reviewed_files)):
                before, after = logical.get(name), reviewed_files.get(name)
                if before != after:
                    changes.append({"path": name, "action": "add" if before is None else "remove" if after is None else "modify",
                                    "before_sha256": sha256(before) if before is not None else None,
                                    "after_sha256": sha256(after) if after is not None else None,
                                    "bytes_before": len(before) if before is not None else 0,
                                    "bytes_after": len(after) if after is not None else 0,
                                    "generated": after is not None and composed.get(name) != after})
            if action == 'batch' and not changes:
                raise ValueError('The selected add-ons already match this client. There are no installation changes to apply.')
            public = {"id": uuid.uuid4().hex, "action": action, "addon_id": addon_id, "changes": changes,
                      "reference": copy.deepcopy(getattr(backend, 'reference_metadata', None)),
                      "game_update": game_update,
                      "warnings": sorted(set(warnings)), "conflicts": sorted(set(conflicts)),
                      "can_apply": not conflicts, "summary": ('Reinstall add-ons: %d logical file changes' % len(changes)) if action == 'repair' else ('Reapply add-ons to the updated game: %d logical file changes' % len(changes)) if action == 'reapply' else "%s %s: %d logical file changes" % (action.capitalize(), addon_id, len(changes)),
                      "installed": self._installed_public(desired, profile), "desired_state": self._installed_public(desired, profile),
                      "preview_kind": "backend" if callable(preview) else "composition",
                      "created_at": _now(), "physical_changes": "Pack files are built and validated in staging during apply."}
            if action == 'batch':
                public.update(batch=batch, summary='Install/update %d selected add-ons together: %d logical file changes' % (len(batch), len(changes)))
            self._pending = {"public": public, "desired": desired, "new_packages": new_packages,
                             "baseline": baseline, "composed": composed, "generation": self._generation,
                             "reviewed_logical_hashes": _hashes(reviewed_files) if callable(preview) else None,
                             "logical_hashes": _hashes(logical), "physical_hashes": _hashes(physical),
                             "stored_fingerprint": sha256(json.dumps(stored, sort_keys=True).encode("utf-8"))}
            self._pending['compatibility_target'] = self._compatibility_target(profile)
            self._pending['game_rebase'] = bool(game_update)
            return copy.deepcopy(public)

    def _physical_path(self, name: str) -> Path:
        return confined_file(Path(self._require().target_root), name)

    def _write_physical(self, name: str, content: bytes | None) -> None:
        """One journal-covered replacement; deliberately small for fault tests."""
        path = self._physical_path(name)
        if content is None:
            if path.exists():
                if not path.is_file():
                    raise ValueError("Physical output is not a file: %s" % name)
                path.unlink()
        else:
            _atomic_bytes(path, content)

    def _record_history(self, event: dict) -> None:
        path = self._target_dir / "history.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True, ensure_ascii=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def history(self) -> list[dict]:
        with self._lock:
            if self._backend is None:
                return []
            path = self._target_dir / "history.jsonl"
            if not path.exists():
                return []
            events = []
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    events.append(json.loads(line))
                except ValueError:
                    events.append({"action": "diagnostic", "status": "warning", "message": "An incomplete activity-log entry was ignored."})
            return list(reversed(events[-200:]))

    def apply(self, plan_id: str) -> dict:
        with self._lock:
            backend = self._require()
            if self._journal_path.exists():
                raise ValueError("Recover the unfinished transaction before applying another plan.")
            plan = self._pending
            if not plan or plan["public"]["id"] != plan_id or plan["generation"] != self._generation:
                raise ValueError("This plan is no longer current. Review a new plan before applying.")
            if not plan["public"]["can_apply"]:
                raise ValueError("This plan has conflicts: %s" % "; ".join(plan["public"]["conflicts"]))
            backend.check_writable()
            stored = self._stored()
            profile = backend.profile()
            if self._compatibility_target(profile) != plan['compatibility_target']:
                self._invalidate()
                raise ValueError('Game/client version or profile changed since review. Review the current compatibility information again.')
            compatibility_conflicts, _ = self._desired_valid(plan["desired"], profile)
            if compatibility_conflicts:
                self._invalidate()
                raise ValueError("Compatibility changed after review: %s" % "; ".join(compatibility_conflicts))
            if sha256(json.dumps(stored, sort_keys=True).encode("utf-8")) != plan["stored_fingerprint"]:
                self._invalidate()
                raise ValueError("Installation state changed after review. Create a new plan.")
            logical = _snapshot(backend.snapshot(), "snapshot")
            physical = _snapshot(backend.physical_snapshot(), "physical_snapshot")
            if _hashes(logical) != plan["logical_hashes"] or _hashes(physical) != plan["physical_hashes"]:
                self._invalidate()
                raise ValueError("Installation files changed after review. No writes were made; create a new plan.")
            for addon_id, package in plan["new_packages"].items():
                fresh = load_package(package.path)
                if fresh.digest != package.digest or fresh.files != package.files:
                    self._invalidate()
                    raise ValueError("Add-on release changed after review: %s. Create a new plan." % addon_id)
            if plan.get("reviewed_logical_hashes") is not None:
                preview = getattr(backend, "preview", None)
                if not callable(preview) or _hashes(_snapshot(preview(dict(plan["composed"])), "snapshot")) != plan["reviewed_logical_hashes"]:
                    self._invalidate()
                    raise ValueError("Generated framework or source data changed after review. Create a new plan.")
            transaction_id = uuid.uuid4().hex
            transaction_dir = self._target_dir / "transactions" / transaction_id
            staging = transaction_dir / "staging"
            staging.mkdir(parents=True, exist_ok=False)
            baseline_physical = stored.get('baseline_physical')
            if plan['game_rebase'] or stored.get('baseline') is None:
                original_physical = physical
            elif baseline_physical:
                original_physical = {name: self._read_object(digest) for name, digest in baseline_physical.items()}
            else:
                original_physical = None
            if not plan['desired'] and original_physical is not None:
                outputs = dict(original_physical)
            else:
                outputs = _snapshot(backend.prepare(dict(plan["composed"]), staging), "prepare")
            # prepare must not mutate the target or invalidate the reviewed hashes.
            after_prepare = _snapshot(backend.physical_snapshot(), "physical_snapshot")
            if _hashes(after_prepare) != plan["physical_hashes"] or _hashes(_snapshot(backend.snapshot(), "snapshot")) != plan["logical_hashes"]:
                self._invalidate()
                raise ValueError("Installation changed while building staged packs. No Hub writes were performed; review the target.")
            backend.check_writable()
            # Stage immutable content before touching the target. A disk-full
            # error while saving a large baseline must not occur mid-install.
            # These objects become a baseline only at the atomic state commit.
            baseline_hashes = stored.get("baseline")
            if baseline_hashes is None or plan['game_rebase']:
                baseline_hashes = {name: self._put_object(content) for name, content in plan["baseline"].items()}
            if original_physical is not None:
                baseline_physical = {name: self._put_object(content) for name, content in original_physical.items()}
            for package in plan["new_packages"].values():
                for content in package.files.values():
                    self._put_object(content)
            operations = []
            for index, name in enumerate(sorted(set(physical) | set(outputs))):
                before, after = physical.get(name), outputs.get(name)
                self._physical_path(name)
                if before == after:
                    continue
                backup = None
                staged = None
                if before is not None:
                    backup = "backups/%04d.bin" % index
                    _atomic_bytes(transaction_dir / backup, before)
                if after is not None:
                    staged = "outputs/%04d.bin" % index
                    _atomic_bytes(transaction_dir / staged, after)
                operations.append({"path": name, "backup": backup, "staged": staged,
                                   "before_sha256": sha256(before) if before is not None else None,
                                   "after_sha256": sha256(after) if after is not None else None})
            journal = {"schema_version": 1, "id": transaction_id, "phase": "prepared", "created_at": _now(),
                       "action": plan["public"]["action"], "addon_id": plan["public"]["addon_id"],
                       "operations": operations, "old_state": stored, "original_physical_hashes": _hashes(physical),
                       "target_root": str(Path(backend.target_root).resolve())}
            _atomic_json(self._journal_path, journal)
            try:
                journal["phase"] = "applying"
                _atomic_json(self._journal_path, journal)
                for operation in operations:
                    name = operation["path"]
                    current_path = self._physical_path(name)
                    current = current_path.read_bytes() if current_path.exists() else None
                    if (sha256(current) if current is not None else None) != operation["before_sha256"]:
                        raise ValueError("Physical file changed immediately before replacement: %s" % name)
                    content = (transaction_dir / operation["staged"]).read_bytes() if operation["staged"] else None
                    self._write_physical(name, content)
                if _hashes(_snapshot(backend.physical_snapshot(), "physical_snapshot")) != _hashes(outputs):
                    raise ValueError("Physical verification failed after installation.")
                journal["phase"] = "files_verified"
                _atomic_json(self._journal_path, journal)
                observed_logical = _snapshot(backend.snapshot(), "snapshot")
                if plan.get("reviewed_logical_hashes") is not None and _hashes(observed_logical) != plan["reviewed_logical_hashes"]:
                    raise ValueError("Installed logical files do not match the reviewed generated preview.")
                new_state = {"schema_version": 1, "installed": plan["desired"], "baseline": baseline_hashes,
                             "baseline_physical": baseline_physical,
                             "reference": copy.deepcopy(plan['public'].get('reference')),
                             "logical_hashes": _hashes(observed_logical), "physical_hashes": _hashes(outputs),
                             "transaction_id": transaction_id, "updated_at": _now()}
                _atomic_json(self._state_path, new_state)
                journal["phase"] = "state_committed"
                _atomic_json(self._journal_path, journal)
                event = {"id": transaction_id, "time": _now(), "action": journal["action"], "addon_id": journal["addon_id"],
                         "status": "success", "message": plan["public"]["summary"], "physical_files_changed": len(operations),
                         "backup_directory": str(transaction_dir / "backups")}
                self._record_history(event)
                self._journal_path.unlink()
                self._invalidate()
                return {"status": "success", "id": transaction_id, "summary": event["message"], "state": self.state()}
            except Exception as exc:
                self._invalidate()
                try:
                    result = self.recover()
                except Exception as recovery_error:
                    raise ValueError("Installation failed: %s. Recovery is pending: %s" % (exc, recovery_error)) from exc
                if result.get("status") == "committed":
                    return {"status": "success", "id": transaction_id, "summary": "Installation was committed and its journal was recovered.", "state": self.state()}
                raise ValueError("Installation failed and previous files were restored: %s" % exc) from exc

    def recover(self) -> dict:
        with self._lock:
            backend = self._require()
            if not self._journal_path.exists():
                return {"status": "clean", "message": "No unfinished transaction requires recovery."}
            backend.check_writable()
            journal = _json(self._journal_path)
            if journal.get("schema_version") != 1 or journal.get("target_root") != str(Path(backend.target_root).resolve()):
                raise ValueError("Recovery journal does not match this installation. Preserve it for investigation.")
            transaction_id = journal.get("id", "")
            if not isinstance(transaction_id, str) or len(transaction_id) != 32 or any(c not in "0123456789abcdef" for c in transaction_id):
                raise ValueError("Recovery journal has an invalid transaction id.")
            transaction_dir = self._target_dir / "transactions" / transaction_id
            operations = journal["operations"]
            stored = self._stored()
            committed = stored.get("transaction_id") == transaction_id
            if committed:
                actual = _hashes(_snapshot(backend.physical_snapshot(), "physical_snapshot"))
                if actual != stored["physical_hashes"]:
                    raise ValueError("Committed transaction has unexpected external changes. Recovery will not overwrite them.")
                self._record_history({"id": transaction_id, "time": _now(), "action": "recovery", "status": "success",
                                      "message": "Confirmed a committed transaction after interruption."})
                self._journal_path.unlink()
                self._invalidate()
                return {"status": "committed", "message": "The completed installation was verified and its recovery journal cleared."}
            restoration: list[tuple[str, bytes | None]] = []
            # Validate every operation and backup before restoring any file.
            for operation in operations:
                name = logical_path(operation["path"])
                path = self._physical_path(name)
                current = path.read_bytes() if path.exists() else None
                digest = sha256(current) if current is not None else None
                if digest not in (operation["before_sha256"], operation["after_sha256"]):
                    raise ValueError("Recovery found unexpected changes in %s. Preserve your edit and backups before retrying." % name)
                backup = operation["backup"]
                content = None
                if backup:
                    backup_path = confined_file(transaction_dir, backup)
                    content = backup_path.read_bytes()
                    if sha256(content) != operation["before_sha256"]:
                        raise ValueError("Recovery backup is corrupt for %s. No files were restored." % name)
                elif operation["before_sha256"] is not None:
                    raise ValueError("Recovery backup is missing for %s." % name)
                restoration.append((name, content))
            for name, content in reversed(restoration):
                self._write_physical(name, content)
            expected = journal.get("original_physical_hashes", journal["old_state"].get("physical_hashes"))
            if expected is not None and _hashes(_snapshot(backend.physical_snapshot(), "physical_snapshot")) != expected:
                raise ValueError("Recovery restored transaction files but unrelated external changes remain. Review the installation.")
            _atomic_json(self._state_path, journal["old_state"])
            self._record_history({"id": transaction_id, "time": _now(), "action": "recovery", "status": "success",
                                  "message": "Restored the previous installation from physical backups.",
                                  "addon_id": journal.get("addon_id")})
            self._journal_path.unlink()
            self._invalidate()
            return {"status": "restored", "message": "Previous installation files and add-on state were restored.", "state": self.state()}
