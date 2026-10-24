"""Validation and loading for local, immutable add-on release directories.

Packages contain code and must be trusted by their user. These checks constrain
what the installer can write; they do not sandbox Python running in the client.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

ID_RE = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MODULE_RE = re.compile(r"^m2hub_addons(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_FILES = 2048
COMMON_INIT = "m2hub_addons/__init__.py"
GAME_EXTENSION_FILES = {'server/mounts_legacy.quest.in', 'server/mounts.json'}


class PackageError(ValueError):
    """A release is invalid or unsafe to install."""


def parse_json(raw: bytes | str, limit: int = 256 * 1024) -> Any:
    """Read bounded, unambiguous JSON from an untrusted manifest or index."""
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise PackageError("Duplicate JSON key: %s" % key)
            result[key] = value
        return result

    def constant(value):
        raise PackageError("Non-finite JSON number: %s" % value)

    try:
        if len(raw.encode('utf-8') if isinstance(raw, str) else raw) > limit:
            raise PackageError("JSON exceeds its byte limit.")
        value = json.loads(raw.decode('utf-8-sig') if isinstance(raw, bytes) else raw,
                           object_pairs_hook=pairs, parse_constant=constant)
        pending = [(value, 0)]
        while pending:
            node, depth = pending.pop()
            if depth > 32:
                raise PackageError("JSON nesting exceeds 32 levels.")
            if isinstance(node, dict):
                pending.extend((child, depth + 1) for child in node.values())
                pending.extend((key, depth + 1) for key in node)
            elif isinstance(node, list):
                pending.extend((child, depth + 1) for child in node)
            elif isinstance(node, str):
                node.encode('utf-8')  # Reject unpaired surrogate escapes.
            elif isinstance(node, float) and not math.isfinite(node):
                raise PackageError("Non-finite JSON number.")
        return value
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise PackageError("Invalid UTF-8 JSON: %s" % exc) from exc


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def logical_path(value: Any) -> str:
    """Accept portable relative paths only, including on non-Windows hosts."""
    if not isinstance(value, str) or not value or len(value) > 240:
        raise PackageError("File paths must be nonempty relative paths of at most 240 characters.")
    if "\\" in value or ":" in value or any(ord(c) < 32 for c in value):
        raise PackageError("Unsafe file path: %r" % value)
    parts = value.split("/")
    if any(p in ("", ".", "..") or p.endswith((".", " ")) for p in parts):
        raise PackageError("Unsafe file path: %r" % value)
    reserved = {"CON", "PRN", "AUX", "NUL", *("COM%d" % i for i in range(1, 10)),
                *("LPT%d" % i for i in range(1, 10))}
    if any(p.split(".")[0].upper() in reserved for p in parts):
        raise PackageError("Windows device name is not a file path: %r" % value)
    if any(c in value for c in '<>"|?*') or PurePosixPath(value).is_absolute():
        raise PackageError("Unsafe file path: %r" % value)
    return value


def confined_file(root: Path, relative: str) -> Path:
    relative = logical_path(relative)
    root = root.resolve()
    candidate = root.joinpath(*relative.split("/"))
    try:
        candidate.resolve().relative_to(root)
    except ValueError as exc:
        raise PackageError("File escapes its permitted directory: %s" % relative) from exc
    # Even internal symlinks make package contents mutable through other paths.
    current = root
    for part in relative.split("/"):
        current = current / part
        if current.is_symlink():
            raise PackageError("Symbolic links are not supported in packages or installation outputs: %s" % relative)
    return candidate


def _strings(value: Any, field: str, ids: bool = False) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise PackageError("%s must be a list of strings." % field)
    if len(value) != len(set(value)):
        raise PackageError("%s contains duplicate entries." % field)
    if ids and any(not ID_RE.fullmatch(x) for x in value):
        raise PackageError("%s contains an invalid add-on id." % field)
    return value


def validate_manifest(manifest: Any) -> dict:
    if not isinstance(manifest, dict):
        raise PackageError("addon.json must contain an object.")
    if manifest.get("schema_version") != 1 or isinstance(manifest.get("schema_version"), bool):
        raise PackageError("Only add-on schema_version 1 is supported.")
    for field in ("id", "name", "version", "description", "author", "category", "kind", "entry"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise PackageError("Manifest %s must be a nonempty string." % field)
        if len(manifest[field]) > (4000 if field == "description" else 256):
            raise PackageError("Manifest %s is too long." % field)
    if not ID_RE.fullmatch(manifest["id"]):
        raise PackageError("Add-on id must be lowercase namespace.name (letters, digits, underscores and hyphens).")
    extension = manifest["kind"] == 'game-extension'
    if manifest["kind"] not in ('client-python', 'game-extension'):
        raise PackageError("Only client-python and supported game-extension packages are supported.")
    if extension and (manifest['entry'] != 'legacy-mount-support'
                      or manifest['id'] != 'community.legacy-mount-support'):
        raise PackageError('This game-extension adapter is not supported by this Studio version.')
    if type(manifest.get('api_version', 1)) is not int or manifest.get('api_version', 1) not in (1, 2):
        raise PackageError('This manager supports client add-on API versions 1 and 2 only.')
    if not extension and not MODULE_RE.fullmatch(manifest["entry"]):
        raise PackageError("Entry must be a Python module below m2hub_addons.")
    for field in ("requires", "conflicts", "capabilities"):
        _strings(manifest.get(field), field, ids=field != "capabilities")
    if extension and (manifest['requires'] or manifest['conflicts']):
        raise PackageError('The built-in game-extension does not support package dependencies or declared conflicts.')
    if manifest["id"] in manifest["requires"] or manifest["id"] in manifest["conflicts"]:
        raise PackageError("An add-on cannot require or conflict with itself.")
    if set(manifest["requires"]) & set(manifest["conflicts"]):
        raise PackageError("The same add-on cannot be both required and conflicting.")
    files = manifest.get("files")
    if not isinstance(files, list) or not files or len(files) > MAX_FILES:
        raise PackageError("Manifest files must contain between 1 and %d entries." % MAX_FILES)
    targets: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise PackageError("Every files entry must be an object.")
        logical_path(item.get("source"))
        target = logical_path(item.get("target"))
        if extension and target not in GAME_EXTENSION_FILES:
            raise PackageError('Game-extension payload is not a supported declarative mount resource: ' + target)
        if not extension and not target.startswith("m2hub_addons/"):
            raise PackageError("Add-ons may only write below m2hub_addons/: %s" % target)
        if target.casefold() in targets:
            raise PackageError("Duplicate target path (including Windows case collisions): %s" % target)
        targets.add(target.casefold())
        if not isinstance(item.get("sha256"), str) or not SHA_RE.fullmatch(item["sha256"]):
            raise PackageError("Each file needs a lowercase SHA-256 checksum: %s" % target)
    entry = manifest["entry"].replace(".", "/")
    if not extension and entry + ".py" not in [f["target"] for f in files] and entry + "/__init__.py" not in [f["target"] for f in files]:
        raise PackageError("The entry module must be included in the package files.")
    if extension and not {'server/mounts_legacy.quest.in', 'server/mounts.json'} <= targets:
        raise PackageError('Legacy Mount Support needs its quest template and declared mount mappings.')
    for field in ("settings", "settings_schema", "compatibility"):
        if field in manifest and not isinstance(manifest[field], dict):
            raise PackageError("%s must be an object." % field)
    ranges = manifest.get('dependency_versions', {})
    if not isinstance(ranges, dict) or any(key not in manifest['requires'] for key in ranges):
        raise PackageError('Dependency version constraints must name required add-ons.')
    from ..versions import satisfies
    for expression in ranges.values():
        try:
            satisfies('0.0.0', expression)
        except ValueError as exc:
            raise PackageError('Invalid dependency version constraint.') from exc
    compatibility = manifest.get("compatibility", {})
    for field in ("client_versions", "server_versions", "profile_ids"):
        if field in compatibility:
            _strings(compatibility[field], "compatibility." + field)
    # Reject non-JSON values (including NaN) and detach caller-owned mutable data.
    try:
        return parse_json(json.dumps(manifest, allow_nan=False))
    except (TypeError, ValueError, RecursionError) as exc:
        raise PackageError("Manifest values must be JSON-compatible.") from exc


@dataclass(frozen=True)
class Package:
    path: Path
    manifest: dict
    files: dict[str, bytes]
    digest: str
    distribution: dict | None = None

    def metadata(self) -> dict:
        result = dict(self.manifest, package_digest=self.digest)
        result.pop('distribution', None)
        if self.distribution:
            result['distribution'] = copy.deepcopy(self.distribution)
        return result


def load_package(path: str | Path) -> Package:
    path = Path(path).resolve()
    manifest_path = confined_file(path, "addon.json")
    try:
        if manifest_path.stat().st_size > 256 * 1024:
            raise PackageError("addon.json exceeds 256 KiB.")
        manifest = validate_manifest(parse_json(manifest_path.read_bytes()))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackageError("Cannot read %s: %s" % (manifest_path, exc)) from exc
    payload = path / "payload"
    if payload.is_symlink() or not payload.is_dir():
        raise PackageError("Package payload must be a directory, not a symbolic link.")
    files: dict[str, bytes] = {}
    total = 0
    for item in manifest["files"]:
        source = confined_file(payload, item["source"])
        try:
            if source.stat().st_size > MAX_FILE_BYTES:
                raise PackageError("Payload file exceeds 16 MiB: %s" % item["source"])
            content = source.read_bytes()
        except OSError as exc:
            raise PackageError("Cannot read payload %s: %s" % (item["source"], exc)) from exc
        total += len(content)
        if total > MAX_PACKAGE_BYTES:
            raise PackageError("Payload exceeds 64 MiB.")
        if sha256(content) != item["sha256"]:
            raise PackageError("SHA-256 mismatch for %s; obtain an intact release." % item["source"])
        if item["target"] == COMMON_INIT:
            try:
                tree = ast.parse(content.decode("utf-8-sig"))
            except (SyntaxError, UnicodeError) as exc:
                raise PackageError("Common namespace __init__.py must be empty or documentation only.") from exc
            if any(not (isinstance(n, ast.Pass) or isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                        and isinstance(n.value.value, str)) for n in tree.body):
                raise PackageError("Common namespace __init__.py must be empty or documentation only.")
        files[item["target"]] = content
    digest = sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    return Package(path, manifest, files, digest)


def discover_packages(catalog_dir: str | Path) -> tuple[dict[str, Package], list[dict]]:
    root = Path(catalog_dir)
    packages: dict[str, Package] = {}
    errors: list[dict] = []
    if not root.exists():
        return packages, errors
    for directory in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        try:
            if directory.is_symlink():
                raise PackageError("Catalog package directories cannot be symbolic links.")
            package = load_package(directory)
            addon_id = package.manifest["id"]
            if addon_id in packages:
                raise PackageError("Duplicate catalog id: %s" % addon_id)
            packages[addon_id] = package
        except (PackageError, OSError) as exc:
            errors.append({"id": directory.name, "name": directory.name, "status": "invalid", "error": str(exc), "source": str(directory)})
    return packages, errors
