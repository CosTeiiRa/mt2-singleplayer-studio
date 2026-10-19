"""Metin2 Server Studio. Local file editor; Python standard library only."""
from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
from contextvars import ContextVar
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote
from metin2_studio.configuration_policy import editable_path, check_change, READ_ONLY_REASON
from metin2_studio.catalogue import Catalogue, sql_rows
from metin2_studio import deployment_progress
from metin2_studio.item_icons import icon_path
from metin2_studio.item_usage import item_usage, item_drop_summary
from metin2_studio.economy import Economy
from metin2_studio.economy_export import download as economy_download
from metin2_studio.workspace import Workspace, history_category, history_areas
from metin2_studio.protected_updates import ProtectedUpdates
from metin2_studio.studio_features import drop_index, combined_drops, bulk_drop_plan, search as studio_search, table_view, table_plan
from metin2_studio.installation import APPLICATION, default_root, resolve_settings, bind_state, studio_version

from metin2_studio.paths import PROJECT_ROOT

HERE = PROJECT_ROOT
try:
    DEFAULT_ROOT = default_root()
except ValueError:
    DEFAULT_ROOT = None  # main() reports actionable setup errors; --root can repair startup.
ACTIVE_CHANGESET = ContextVar('studio_changeset', default=None)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def number(value, low, high, integer=False):
    text = str(value)
    if not re.fullmatch(r"\d+(?:\.\d+)?", text) or (integer and not text.isdigit()):
        raise ValueError("Enter a positive number using a dot for decimals.")
    n = float(text)
    if not low <= n <= high:
        raise ValueError(f"Value must be between {low} and {high}.")
    return str(int(n)) if integer else text


def text_decode(raw):
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("latin1"), "latin1"


class Studio:
    def __init__(self, root, state=None):
        self.root = Path(root).resolve()
        self.app = HERE
        self.active_context = ACTIVE_CHANGESET
        if not (self.root / "files/items.json").is_file():
            raise ValueError("This is not a supported Metin2 server folder (files/items.json missing).")
        self.game = self.root / "linux-port/docker/game"
        self.locale = self.game / "share/locale/poland"
        self.compose = self.game.parent
        self.state = Path(state or HERE / "data").resolve()
        self.state.mkdir(parents=True, exist_ok=True)
        spec = importlib.util.spec_from_file_location("installed_drop_tables", self.root / "files/drop_tables.py")
        self.dt = importlib.util.module_from_spec(spec)
        # Read installed source without writing bytecode into the game folder.
        drop_parser = (self.root / 'files/drop_tables.py').read_bytes()
        exec(compile(drop_parser, str(self.root / 'files/drop_tables.py'), 'exec'), self.dt.__dict__)
        self.drop_parser_sha = digest(drop_parser)
        self.token = secrets.token_urlsafe(32)
        self.plans = {}
        self.lock = threading.RLock()
        self.job = {"status": "idle", "lines": []}
        self._operation_lock = threading.RLock()
        self._active_mutations = 0
        self._stopping = False
        self._apply_thread = None
        self._health_cache = None
        self.catalogue = Catalogue(self.root, self.state)
        snapshot = self.catalogue.refresh(force=True)
        self.items, self.mobs = snapshot['items'], snapshot['mobs']
        self.icons = snapshot['legacyIcons']
        self._catalogue_revision = snapshot['revision']
        self._catalogue_status = dict(self.catalogue.status)
        self._catalogue_stop = threading.Event()
        self.sources = {
            "mob-base": (self.locale / "mob_drop_item.txt", "mob_drop_item.txt", "Monster & Metin drops"),
            "mob-m3": (self.game / "share-add/mob_drop_item.m3.append.txt", "mob_drop_item.txt", "Additional monster drops"),
            "chest-base": (self.locale / "special_item_group.txt", "special_item_group.txt", "Chest contents"),
            "chest-moonlight": (self.game / "special_item_group.moonlight.custom.txt", "special_item_group.txt", "Moonlight chest"),
            "chest-starter": (self.game / "share-add/special_item_group.starter.txt", "special_item_group.txt", "Starter chests"),
            "chest-hexagonal": (self.game / "share-add/special_item_group.hexagonal.txt", "special_item_group.txt", "Hexagonal event chests"),
        }
        self.settings_schema = self.discover_settings()
        self.workspace = Workspace(self)
        from metin2_studio.save_recovery import SaveRecovery
        self.save_recovery = SaveRecovery(self)
        interrupted = self.workspace.interrupt_deployments()
        if interrupted:
            self.job = interrupted
        self.economy = Economy(self)
        from metin2_studio.native_crafting import NativeCrafting
        self.native_crafting = NativeCrafting(self)
        self.updates = ProtectedUpdates(self)
        self._addons = None

    @contextmanager
    def mutation_request(self):
        with self._operation_lock:
            self.require_running()
            self._active_mutations += 1
        try:
            yield
        finally:
            with self._operation_lock:
                self._active_mutations -= 1

    def require_running(self):
        if self._stopping:
            raise ValueError('Studio is stopping. Start Studio again before making changes.')

    def server_busy(self):
        worker = self._apply_thread
        return self.job.get('status') == 'running' or worker is not None and worker.is_alive() is True

    def public_job(self):
        return {**self.job, 'status': 'running'} if self.server_busy() else self.job

    def request_shutdown(self):
        with self._operation_lock:
            network = self._addons.jobs.latest() if self._addons is not None else None
            if (self._active_mutations or self.server_busy()
                    or self.updates.job.get('status') == 'running'
                    or network and network.get('status') in ('queued', 'running')):
                raise ValueError('Studio is busy saving, applying or updating. Wait for the operation to finish, or cancel its download and wait, before stopping Studio. The game has not been stopped by this request.')
            self._stopping = True

    @property
    def addons(self):
        with self.lock:
            if self._addons is None:
                from metin2_studio.addons.integration import AddonService
                self._addons = AddonService(self)
            return self._addons

    def configuration_editable(self, path):
        return editable_path(self, path)

    def read(self, path):
        if hasattr(self, 'workspace'):
            return self.workspace.read(path, ACTIVE_CHANGESET.get())
        return path.read_bytes() if path.exists() else None

    def safe(self, path):
        p = Path(path).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError("Path must stay inside the selected server folder.")
        return p

    def catalogue_status(self):
        return dict(getattr(self, '_catalogue_status', {}))

    def refresh_catalog(self, force=False):
        snapshot = self.catalogue.refresh(force=force)
        with self.lock:
            # Another refresh may have completed while this thread waited.
            snapshot = self.catalogue.snapshot
            if snapshot['revision'] != self._catalogue_revision:
                self.items, self.mobs = snapshot['items'], snapshot['mobs']
                self.icons = snapshot['legacyIcons']
                self._catalogue_revision = snapshot['revision']
                if hasattr(self, 'economy'):
                    self.economy.cached = None
                self._drop_hover_cache = None
                self._economy_sources = None
            self._catalogue_status = dict(self.catalogue.status)
        return self.catalogue_status()

    def start_catalogue_sync(self):
        def watch():
            while not self._catalogue_stop.wait(15):
                if self._stopping:
                    break
                try:
                    if self.updates.job.get('status') != 'running':
                        self.refresh_catalog()
                except (OSError, ValueError):
                    self._catalogue_status = {**self._catalogue_status, 'refreshPending': True}
        threading.Thread(target=watch, name='studio-catalogue', daemon=True).start()

    def reload_catalog(self):
        with self.lock:
            if self.server_busy():
                raise ValueError('Wait for the current operation before reloading the catalog.')
        self.refresh_catalog(force=True)
        with self.lock:
            parser = (self.root / 'files/drop_tables.py').read_bytes()
            spec = importlib.util.spec_from_file_location('installed_drop_tables', self.root / 'files/drop_tables.py')
            module = importlib.util.module_from_spec(spec)
            exec(compile(parser, str(self.root / 'files/drop_tables.py'), 'exec'), module.__dict__)
            self.dt, self.drop_parser_sha = module, digest(parser)
            self.settings_schema = self.discover_settings()
        return {'reloaded': True, 'catalogue': self.catalogue_status()}

    def source_raw(self, source):
        path, filename, label = self.sources[source]
        raw = self.read(path)
        if source == "chest-moonlight" and raw is None:
            return self.read(self.game / "share-add/special_item_group.moonlight.txt") or b''
        return raw or b''

    def groups(self, raw_sources=None):
        out = []
        parsed = {source: self.dt.logical_groups(filename, raw_sources[source] if raw_sources is not None else self.source_raw(source)) for source, (_, filename, _) in self.sources.items()}
        referenced = {e.item[1:] for groups in parsed.values() for group in groups for e in group.entries if e.item.startswith("s")}
        replaced = set()
        for source in ("chest-moonlight", "chest-starter", "chest-hexagonal"):
            replaced.update(g.key for g in parsed[source])
        for source, (path, filename, label) in self.sources.items():
            for g in parsed[source]:
                if source == "chest-base" and g.key in replaced:
                    continue
                mob = filename == "mob_drop_item.txt"
                ident = g.fields.get("mob" if mob else "vnum", "")
                catalog = self.mobs if mob else self.items
                entity = catalog.get(ident, {})
                display = entity.get("name", (self.mobs[ident]["name"] + " loot pool") if not mob and ident in self.mobs else f"{'Monster' if mob else 'Reward pool'} #{ident}")
                category = entity.get("category", "chest")
                if not mob and ident in referenced:
                    category = "pool"
                    display = self.mobs[ident]["name"] + " loot pool" if ident in self.mobs else f"Shared reward pool #{ident}"
                out.append({"source": source, "key": g.key, "id": ident, "name": display, "category": category, "level": entity.get("level"), "type": g.fields.get("type", "") or "weighted", "count": len(g.entries), "blocks": g.blocks, "file": str(path.relative_to(self.root))})
        return out

    def group(self, source, key):
        if source not in self.sources:
            raise ValueError("Unknown drop source.")
        filename = self.sources[source][1]
        g = next((g for g in self.dt.logical_groups(filename, self.source_raw(source)) if g.key == key), None)
        if g is None:
            raise ValueError("Drop group not found. Refresh the list.")
        data = next((x for x in self.groups() if x["source"] == source and x["key"] == key), {})
        chances = self.dt.chances(g)
        data.update({"fields": {k: v for k, v in g.fields.items() if not k.endswith("comment")}, "entries": [{"item": e.item, "count": e.count, "prob": e.prob, "rare": e.rare, "name": self.items.get(e.item, {}).get("name", e.item), "chance": chances[i]} for i, e in enumerate(g.entries)], "hash": digest(self.source_raw(source)), "skipped": len(g.skipped)})
        return data

    def drop_plan(self, body):
        source = body.get("source", "mob-base")
        if source not in self.sources:
            raise ValueError("Unknown drop source.")
        path, filename, label = self.sources[source]
        raw = self.source_raw(source)
        if body.get("hash") != digest(raw):
            raise ValueError("This drop file changed. Reopen the group before saving.")
        key = str(body.get("key", ""))
        old = next((g for g in self.dt.logical_groups(filename, raw) if g.key == key), None)
        is_new = bool(body.get("new"))
        if is_new:
            if old:
                raise ValueError("A group already exists for that target and type. Edit it from the list.")
            fields = {str(k): str(v) for k, v in body.get("fields", {}).items() if k in ("mob", "vnum", "type", "kill_drop", "level_limit")}
            expected = fields.get("vnum") if filename == "special_item_group.txt" else f"{fields.get('mob')} {fields.get('type')}"
            if key != expected:
                raise ValueError("Invalid group key.")
            old = self.dt.Group(filename, key, f"studio_{key.replace(' ', '_')}".encode("ascii"), fields, [])
        elif old is None:
            raise ValueError("Group no longer exists.")
        g = copy.deepcopy(old)
        for field in ("kill_drop", "level_limit"):
            if field in body.get("fields", {}):
                g.fields[field] = str(body["fields"][field])
        g.entries = [self.dt.Entry(str(e.get("item", "")), str(e.get("count", "")), str(e.get("prob", "")), str(e.get("rare", "")), self.dt.ascii_comment(self.items.get(str(e.get("item")), {}).get("name", ""))) for e in body.get("entries", [])]
        problems = self.dt.check_group(g, lambda n: str(n) in self.items, lambda n: str(n) in self.mobs, {x.key for x in self.dt.logical_groups("special_item_group.txt", self.source_raw("chest-base"))} | {x["key"] for x in self.groups() if x["source"].startswith("chest")}, is_new=is_new)
        if problems:
            raise ValueError("\n".join(self.dt.describe(p, "en") for p in problems))
        if filename == "special_item_group.txt":
            graph = {}
            for src, (_, fn, _) in self.sources.items():
                if fn == filename:
                    for group in self.dt.logical_groups(fn, self.source_raw(src)):
                        graph[group.key] = [e.item[1:] for e in group.entries if e.item.startswith("s")]
            graph[g.key] = [e.item[1:] for e in g.entries if e.item.startswith("s")]
            def visit(node, stack):
                if node in stack:
                    raise ValueError("Reward pools cannot reference themselves or form a loop.")
                if len(stack) > 32:
                    raise ValueError("Reward pool nesting is too deep.")
                for child in graph.get(node, []):
                    visit(child, stack | {node})
            visit(g.key, set())
        override = self.dt.apply_change(filename, None, "add" if is_new else "edit", key, g)
        merged = self.dt.merge(filename, raw, self.dt.render_override(override))
        return self.plan(f"Update {label}: {key}", {path: merged}, "Rebuild the game image and restart the server to load this table. Global rates and level differences can change the final drop chance.")

    def discover_settings(self):
        # Deliberately exclude passwords, network exposure, update controls and internal revision keys.
        allowed = {"M2_DEFAULT_GAME_LANGUAGE", "M2_BRAND", "M2_MAX_LEVEL", "M2_INVENTORY_SLOTS", "M2_MAX_ITEM_COUNT", "M2_PLAYERBOT_KINGDOMS", "M2_PLAYERBOT_WORLD_LAYOUT", "M2_DIFFICULTY", "M2_MONSTER_HP", "M2_STARTER_KIT", "M2_STARTER_CHEST", "M2_SKIP_HORSE_QUESTS", "M2_AUTOHUNT", "M2_SIDEKICK", "M2_AUTOHUNT_ITEM", "M2_FLEA_MARKET", "M2_DRAGON_SOUL", "M2_UNIQUE70_BONUS", "M2_YANG_TO_PURSE", "M2_DROP_BONUS_PCT", "M2_MOVE_SPEED_PCT", "M2_DS_EYES_PER_DAY", "M2_EXTRA_DS_DROP", "M2_EXTRA_COUPON_DROP", "M2_CASUAL_SHOP", "M2_ITEMSHOP_PRICE_PCT", "M2_PLAYERBOT_CH2", "M2_ONLY_CH1", "M2_PLAYERBOT_FRESH_CHANNELS"}
        prefixes = ("M2_RATE_", "M2_EXCHANGE_", "M2_BIOLOGIST_WAIT_", "M2_HORSE_WAIT_", "M2_BOOK_WAIT_", "M2_BOT_BOOK_WAIT_", "M2_MOONLIGHT_CHEST_", "M2_BLESSING_SCROLL_STONE_")
        bot = {"PLAYERBOT_AUTOSPAWN_COUNT", "PLAYERBOT_MEDAL_DROPPERS", "PLAYERBOT_MEDAL_DROPPER_LEVEL", "PLAYERBOT_SPAWN_WINDOW_MINUTES", "PLAYERBOT_LATE_JOINERS", "PLAYERBOT_LATE_JOIN_HOURS", "PLAYERBOT_AUTOSPAWN_PER_KINGDOM", "PLAYERBOT_AUTOSPAWN_SHINSOO", "PLAYERBOT_AUTOSPAWN_CHUNJO", "PLAYERBOT_AUTOSPAWN_JINNO", "PLAYERBOT_CH2_SHARE", "PLAYERBOT_FRESH_COUNT"}
        enums = {"M2_DIFFICULTY": ["easy", "medium", "hard", "custom"], "M2_DEFAULT_GAME_LANGUAGE": ["pl", "en", "de", "fr", "pt", "ro"], "M2_PLAYERBOT_KINGDOMS": ["0", "1"], "M2_PLAYERBOT_WORLD_LAYOUT": ["unified", "split"], "M2_STARTER_KIT": ["default", "medium", "easy"]}
        booleans = {"M2_PLAYERBOT_CH2", "M2_ONLY_CH1", "M2_STARTER_CHEST", "M2_SKIP_HORSE_QUESTS", "M2_AUTOHUNT", "M2_SIDEKICK", "M2_AUTOHUNT_ITEM", "M2_FLEA_MARKET", "M2_DRAGON_SOUL", "M2_UNIQUE70_BONUS", "M2_YANG_TO_PURSE", "M2_CASUAL_SHOP", "PLAYERBOT_AUTOSPAWN_PER_KINGDOM"}
        enums.update({k: ["0", "1"] for k in booleans})
        result, comments = {}, []
        for line in (self.compose / ".env.example").read_text("utf-8").splitlines():
            if line.startswith("#"):
                comments.append(line.lstrip("# "))
                continue
            m = re.match(r"([A-Z][A-Z0-9_]*)=(.*)", line)
            if not m:
                if not line.strip():
                    comments = []
                continue
            key, default = m.groups()
            if key in allowed or key in bot or key.startswith(prefixes):
                group = "Bots & population" if key in bot or "PLAYERBOT" in key else "Drops & economy" if any(x in key for x in ("DROP", "YANG", "COUPON", "MOONLIGHT", "SCROLL", "ITEMSHOP", "EXCHANGE")) else "Progression & difficulty" if any(x in key for x in ("WAIT", "DIFFICULTY", "HP", "RATE", "LEVEL")) else "World & features"
                result[key] = {"key": key, "label": key.removeprefix("M2_").removeprefix("PLAYERBOT_").replace("_", " ").capitalize(), "default": default, "description": "\n".join(comments[-24:]), "group": group, "options": enums.get(key), "fresh": key.startswith("M2_RATE_")}
                schema = result[key]
                schema['dependent'] = any(part in key for part in ('_WAIT_', 'M2_EXCHANGE_'))
                schema['unit'] = 'per mille' if 'PERMILLE' in key else '%' if any(part in key for part in ('_PCT', '_SHARE', 'M2_EXCHANGE_')) else 'hours' if 'HOURS' in key else 'minutes' if 'MINUTES' in key else 'seconds' if 'SECONDS' in key else 'count' if any(part in key for part in ('COUNT', 'SLOTS', 'LEVEL', 'DROPPERS')) else ''
                if re.fullmatch(r"\d+(\.\d+)?", default) and not schema['options']:
                    bounds = {"M2_MAX_LEVEL": (1, 120), "M2_INVENTORY_SLOTS": (45, 180), "M2_MAX_ITEM_COUNT": (1, 255), "M2_DROP_BONUS_PCT": (10, 1000), "M2_MOVE_SPEED_PCT": (50, 200), "M2_PLAYERBOT_FRESH_CHANNELS": (0, 2), "PLAYERBOT_SPAWN_WINDOW_MINUTES": (1, 180), "PLAYERBOT_LATE_JOIN_HOURS": (1, 168)}
                    schema['min'], schema['max'] = bounds.get(key, (0, 1000 if "PERMILLE" in key else 100 if any(part in key for part in ("EXTRA_", "CH2_SHARE", "EXCHANGE_")) else 1000000))
                    schema['step'] = 'any' if 'WAIT' in key else '1'

            comments = []
        return result

    def settings(self):
        raw = self.read(self.compose / ".env")
        current = dict(re.findall(r"(?m)^([A-Z][A-Z0-9_]*)=([^\r\n]*)", raw.decode("utf-8-sig")))
        return {"hash": digest(raw), "settings": [{**s, "value": current.get(k, s["default"])} for k, s in self.settings_schema.items()]}

    def settings_plan(self, body):
        path = self.compose / ".env"
        raw = self.read(path)
        if digest(raw) != body.get("hash"):
            raise ValueError("Settings changed on disk. Refresh before saving.")
        text = raw.decode("utf-8-sig")
        for key, value in body.get("values", {}).items():
            if key not in self.settings_schema:
                raise ValueError("This setting is not editable here.")
            value = str(value)
            schema = self.settings_schema[key]
            if schema["fresh"]:
                raise ValueError("EXP/drop/yang base rates seed new worlds only. Use the existing panel's Rates page for your current world.")
            if schema["options"]:
                if value not in schema["options"]:
                    raise ValueError(f"Unsupported value for {key}.")
            elif key == "M2_BRAND":
                if not re.fullmatch(r"[\w .-]{1,60}", value, re.ASCII):
                    raise ValueError("Brand must use 1–60 letters, numbers, spaces, dots or hyphens.")
            elif key == "M2_MONSTER_HP":
                if value not in ("default", "easy"):
                    number(value, 10, 300, True)
            elif re.fullmatch(r"\d+(\.\d+)?", schema["default"]):
                bounds = {"M2_MAX_LEVEL": (1, 120), "M2_INVENTORY_SLOTS": (45, 180), "M2_MAX_ITEM_COUNT": (1, 255), "M2_DROP_BONUS_PCT": (10, 1000), "M2_MOVE_SPEED_PCT": (50, 200), "M2_PLAYERBOT_FRESH_CHANNELS": (0, 2), "PLAYERBOT_SPAWN_WINDOW_MINUTES": (1, 180), "PLAYERBOT_LATE_JOIN_HOURS": (1, 168)}
                low, high = bounds.get(key, (0, 1000 if "PERMILLE" in key else 100 if any(s in key for s in ("EXTRA_", "CH2_SHARE", "EXCHANGE_")) else 1000000))
                number(value, low, high, "WAIT" not in key)
            else:
                raise ValueError(f"{key} requires a supported value; use the launcher for this option.")
            pattern = r"(?m)^" + re.escape(key) + r"=[^\r\n]*"
            text = re.sub(pattern, lambda m: f"{key}={value}", text) if re.search(pattern, text) else text + f"\r\n{key}={value}\r\n"
        encoded = text.encode("utf-8")
        if raw.startswith(b"\xef\xbb\xbf"):
            encoded = b"\xef\xbb\xbf" + encoded
        return self.plan("Update world settings", {path: encoded}, "Use Apply to server to recreate the services with these settings. Custom waiting times and exchange chances require difficulty = custom. Some starter options affect new characters only.", redact=True)

    def inventory(self):
        result = []
        groups = {"cube.txt": ("Crafting recipes", "Crafting"), "special_spawns.txt": ("Boss spawn schedules", "Spawns & maps"), "shop_table_ex.txt": ("Extended NPC shops", "Shops"), "etc_drop_item.txt": ("Material drop percentages", "Drops"), "common_drop_item.txt": ("Common rank / level drops", "Drops"), "fishing.txt": ("Fishing tables", "Fishing"), "blend.txt": ("Potion bonuses & duration", "Items"), "dragon_soul_table.txt": ("Dragon Soul alchemy", "Items"), "skill_power.txt": ("Skill power scaling", "Skills"), "group.txt": ("Monster spawn groups", "Spawns & maps"), "group_group.txt": ("Spawn group collections", "Spawns & maps"), "settings.lua": ("World Lua settings", "World"), "oxquiz.lua": ("OX quiz questions", "Events")}
        for p in self.locale.rglob("*"):
            rel = p.relative_to(self.locale)
            if not p.is_file() or any(x in rel.parts for x in ("object", "_unused", "libs", "pre_qc")) or p.stat().st_size > 1200000:
                continue
            if p.suffix not in (".txt", ".lua", ".quest") and p.name not in ("regen", "npc", "boss", "stone", "Setting.txt", "index"):
                continue
            if p.name in ("mob_drop_item.txt", "special_item_group.txt"):
                continue
            label, category = groups.get(p.name, (p.stem.replace("_", " "), "Quests" if "quest" in rel.parts else "Spawns & maps" if "map" in rel.parts else "World"))
            result.append({"id": str(p.relative_to(self.root)).replace("\\", "/"), "name": label, "category": category, "size": p.stat().st_size, "mode": "Advanced text"})
        for folder, category in [(self.game / "quest", "Package quests"), (self.game / "custom-quests", "Custom quests"), (self.game / "share-add", "Build overrides")]:
            if folder.exists():
                for p in folder.iterdir():
                    if p.is_file() and p.suffix in (".quest", ".lua", ".txt", ".tsv"):
                        result.append({"id": p.relative_to(self.root).as_posix(), "name": p.stem.replace("_", " "), "category": category, "size": p.stat().st_size, "mode": "Advanced text"})
        crafting = self.locale / 'quest/libs/crafting/crafting_data.lua'
        if crafting.is_file() and not any(row['id'] == crafting.relative_to(self.root).as_posix() for row in result):
            result.append({'id': crafting.relative_to(self.root).as_posix(), 'name': 'NPC crafting window definitions', 'category': 'Crafting', 'size': crafting.stat().st_size, 'mode': 'Advanced Lua'})
        return result

    def recipe_sources(self):
        return {"base": self.locale / "cube.txt", "seon": self.game / "share-add/cube.seon_pyeong.txt"}

    def crafting_access(self):
        from metin2_studio.crafting_access import discover
        return {'npcs': discover(self), 'tables': {source: {'hash': digest(self.read(path)), 'file': path.relative_to(self.root).as_posix()} for source, path in self.recipe_sources().items()},
                'note': 'Only Cube-opening quest routes are listed. Other crafting windows use a separate system; dialogue can still have level or quest requirements.'}

    def recipes(self):
        from collections import Counter
        access = self.crafting_access()
        supported = {row['id'] for row in access['npcs']}
        hashes = {source: info['hash'] for source, info in access['tables'].items()}
        result = []
        for source, path in self.recipe_sources().items():
            raw = self.read(path)
            pattern = rb"(?mi)^[ \t]*section[^\n]*\n.*?^[ \t]*end[^\n]*(?:\n|$)"
            baseline = path.read_bytes() if path.is_file() else b''
            if hasattr(self, 'workspace'):
                record = next((r for r in self.workspace.tracked() if r['path'] == path.relative_to(self.root).as_posix()), None)
                if record:
                    baseline = record['original'] or b''
            def signature(block):
                return tuple(tuple(line.split()) for line in block.splitlines() if line.strip() and not line.lstrip().startswith(b'#'))
            originals = Counter(signature(m.group()) for m in re.finditer(pattern, baseline, re.S))
            # Latin-1 gives an exact mapping between byte offsets and characters.
            for index, match in enumerate(re.finditer(rb"(?mi)^[ \t]*section[^\n]*\n.*?^[ \t]*end[^\n]*(?:\n|$)", raw, re.S)):
                key = signature(match.group())
                custom = originals[key] == 0
                if not custom:
                    originals[key] -= 1
                fields, materials, rewards = {}, [], []
                for line in match.group().splitlines():
                    parts = line.strip().split()
                    if not parts or parts[0].startswith(b"#"):
                        continue
                    if parts[0] in (b"item", b"reward") and len(parts) >= 3:
                        (materials if parts[0] == b"item" else rewards).append({"item": parts[1].decode("ascii"), "count": parts[2].decode("ascii")})
                    elif parts[0] in (b"npc", b"percent", b"gold") and len(parts) >= 2:
                        fields[parts[0].decode()] = parts[1].decode("ascii")
                reward = rewards[0]["item"] if rewards else "0"
                result.append({"source": source, "custom": custom, "index": index, "name": self.items.get(reward, {}).get("name", f"Recipe #{index + 1}"), "npcName": self.mobs.get(fields.get("npc"), {}).get("name", "Unknown NPC"), "fields": fields, "materials": materials, "rewards": rewards, "hash": digest(raw), "file": path.relative_to(self.root).as_posix(), "start": match.start(), "end": match.end(), "npcSupported": fields.get("npc") in supported, "sourceHashes": hashes})
        return result

    def crafting_catalog(self, fresh=False):
        access = self.crafting_access()
        native = self.native_crafting.catalog(fresh)
        recipes = self.recipes()
        for recipe in recipes:
            recipe['system'] = 'cube'
            recipe['npcIds'] = [recipe['fields'].get('npc')]
        return {'recipes': recipes + native['recipes'], 'access': {**access, 'native': native}}

    def recipe_plan(self, body):
        if body.get('system') == 'native' or body.get('source') == 'native':
            return self.native_crafting.plan(body)
        sources = self.recipe_sources()
        source = body.get("source")
        if source not in sources:
            raise ValueError("Unknown recipe source.")
        path = sources[source]
        raw = self.read(path)
        if digest(raw) != body.get("hash"):
            raise ValueError("Recipes changed on disk. Reopen the recipe before saving.")
        original = next((r for r in self.recipes() if r["source"] == source and r["index"] == body.get("index")), None)
        if original is None and not body.get("new"):
            raise ValueError("Recipe not found.")
        fields = body.get("fields", {})
        npc = str(fields.get("npc", ""))
        access = next((row for row in self.crafting_access()['npcs'] if row['id'] == npc), None)
        if access is None:
            raise ValueError("Choose a compatible Cube NPC. No Cube-opening dialogue was identified for this NPC.")
        pct, gold = number(fields.get("percent", 100), 1, 100, True), number(fields.get("gold", 0), 0, 100000000, True)
        materials, rewards = body.get("materials", []), body.get("rewards", [])
        if not 1 <= len(materials) <= 10 or not 1 <= len(rewards) <= 5:
            raise ValueError("A recipe needs 1–10 ingredients and 1–5 rewards.")
        lines = ["section", "npc\t" + npc]
        for key, rows in [("item", materials), ("reward", rewards)]:
            for row in rows:
                ident = str(row.get("item", ""))
                if ident not in self.items or ident == "1":
                    raise ValueError("Choose an item from the installed catalog; Yang uses the cost field.")
                qty = number(row.get("count", 1), 1, 200, True)
                lines.append(f"{key}\t{ident}\t{qty}")
        lines.extend(["percent\t" + pct, "gold\t" + gold])
        if original:
            old = raw[original["start"]:original["end"]]
            for line in old.splitlines():
                words = line.strip().split()
                if words and words[0] not in (b"section", b"npc", b"item", b"reward", b"percent", b"gold", b"end"):
                    lines.append(line.decode("latin1"))
        lines.append("end")
        newline = b"\r\r\n" if b"\r\r\n" in raw else b"\r\n" if b"\r\n" in raw else b"\n"
        block = newline.join(line.encode("latin1") for line in lines) + newline
        destination = access['source']
        if destination == source:
            merged = raw[:original["start"]] + block + raw[original["end"]:] if original else raw + newline + block
            changes = {path: merged}
        else:
            target = sources[destination]
            target_raw = self.read(target)
            if body.get('sourceHashes', {}).get(destination) != digest(target_raw):
                raise ValueError('The destination recipe table changed. Reopen the recipe before moving it.')
            target_newline = b'\r\r\n' if b'\r\r\n' in target_raw else b'\r\n' if b'\r\n' in target_raw else b'\n'
            target_block = target_newline.join(line.encode('latin1') for line in lines) + target_newline
            changes = {target: target_raw + target_newline + target_block}
            if original:
                changes[path] = raw[:original['start']] + raw[original['end']:]
        return self.plan("Update crafting recipe: " + self.items[rewards[0]["item"]]["name"], changes, "The recipe uses a confirmed Cube-opening NPC and its compatible table. Moving to Seon-Pyeong uses his separate table, as required by this package. Review and save, then Apply to load it.")

    def recipe_delete_plan(self, body):
        if body.get('system') == 'native' or body.get('source') == 'native':
            return self.native_crafting.plan(body, remove=True)
        recipe = next((row for row in self.recipes() if row['source'] == body.get('source') and row['index'] == body.get('index')), None)
        if recipe is None or recipe['hash'] != body.get('hash'):
            raise ValueError('The recipe changed. Reopen it before removing it.')
        path = self.recipe_sources()[recipe['source']]
        raw = self.read(path)
        plan = self.plan('Remove recipe: ' + recipe['name'], {path: raw[:recipe['start']] + raw[recipe['end']:]},
                         'Only this recipe section is removed. Other recipes and items already crafted are retained. A backup is saved in Change history; Apply loads the removal.')
        plan['confirmLabel'] = 'Remove recipe'
        return plan

    def quest_delete_plan(self, body):
        path = self.safe(self.root / str(body.get('id', '')))
        if path.parent != self.game / 'custom-quests' or not re.fullmatch(r'studio_[a-z][a-z0-9_]{2,40}\.quest', path.name):
            raise ValueError('Remove is available only for Studio quest sources. Package quests may contain shared systems and are retained.')
        raw = self.read(path)
        if raw is None or digest(raw) != body.get('hash'):
            raise ValueError('The quest changed. Reopen it before removing it.')
        from metin2_studio.quest_support import quest_name
        from metin2_studio.quest_templates import template_values
        if quest_name(raw) != path.stem:
            raise ValueError('The quest identity must match its Studio filename before removal.')
        title = str((template_values(raw) or {}).get('title') or path.stem)
        plan = self.plan('Remove quest: ' + title, {path: None},
                         'The Studio quest source is removed with a backup. Apply rebuilds without its handlers. Character progress and earned rewards are retained; restoring this quest retains its previous progress.')
        plan['confirmLabel'] = 'Remove quest'
        return plan

    def file(self, ident):
        if ident not in {x["id"] for x in self.inventory()}:
            raise ValueError("This file is not in the editable configuration catalog.")
        p = self.safe(self.root / ident)
        raw = self.read(p)
        text, encoding = text_decode(raw)
        newline = "\r\r\n" if b"\r\r\n" in raw else "\r\n" if b"\r\n" in raw else "\n"
        text = text.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
        hint = 'Quest source edits retain the quest identity and character flags. Saving registers the edited source for compilation after package quests; Apply builds and restarts separately.' if ident.endswith('.quest') else 'Build overrides are applied after base tables. Advanced edits require a successful image build before they are active.'
        return {"id": ident, "text": text, "encoding": encoding, "hash": digest(raw), "newline": newline, "hint": hint}

    def file_plan(self, body):
        current = self.file(body["id"])
        if current["hash"] != body.get("hash"):
            raise ValueError("File changed. Reopen it before editing.")
        text = str(body["text"]).replace("\r\n", "\n").replace("\r", "\n")
        if len(text) > 1500000 or "\x00" in text:
            raise ValueError("File is too large or contains NUL bytes.")
        # The inventory's source encoding is authoritative, never supplied by the browser.
        try:
            raw = text.replace("\n", current["newline"]).encode(current["encoding"])
        except UnicodeEncodeError:
            raise ValueError("This legacy file cannot represent those characters. Use plain ASCII for added text.")
        if body['id'].endswith('.quest'):
            from metin2_studio.quest_support import source_plan
            return source_plan(self, self.safe(self.root / body['id']), raw)
        return self.plan("Edit " + body["id"].split("/")[-1], {self.root / body["id"]: raw}, current["hint"])

    def quest_code(self, body):
        from metin2_studio.quest_templates import generate
        return generate(self, body, self.validate_quest_fields)

    def validate_quest_fields(self, body):
        ident = str(body.get("id", ""))
        if not re.fullmatch(r"studio_[a-z][a-z0-9_]{2,40}", ident):
            raise ValueError("Quest ID must start studio_ and use lowercase letters, numbers and underscores.")
        def q(s):
            if any(ord(c) < 32 or ord(c) > 126 for c in str(s)) or len(str(s)) > 200:
                raise ValueError("Quest text supports up to 200 plain English characters per field.")
            if '"' in str(s) or "\\" in str(s):
                raise ValueError("Quest text cannot contain double quotes or backslashes; the installed compiler does not preserve their escapes.")
            return str(s)
        title, intro = q(body.get("title", "A new adventure")), q(body.get("intro", "Help protect our world."))
        npc, target, item = str(body.get("npc", "")), str(body.get("target", "")), str(body.get("reward", ""))
        if npc not in self.mobs or self.mobs[npc]["category"] != "npc":
            raise ValueError("Choose an NPC from the installed catalog.")
        if target not in self.mobs or self.mobs[target]["category"] not in ("monster", "metin", "boss"):
            raise ValueError("Choose a monster or Metin to hunt.")
        if item not in self.items or item == "1":
            raise ValueError("Choose a reward item. Yang has its own field.")
        count = number(body.get("kills", 10), 1, 100000, True)
        level = number(body.get("level", 1), 1, 255, True)
        qty = number(body.get("quantity", 1), 1, 200, True)
        yang = number(body.get("yang", 0), 0, 100000000, True)
        exp = number(body.get("exp", 0), 0, 1000000000, True)
        return dict(id=ident, title=title, intro=intro, npc=npc, target=target, reward=item,
                    kills=count, level=level, quantity=qty, yang=yang, exp=exp)

    def quest_plan(self, body):
        ident, code = self.quest_code(body)
        target = self.game / f"custom-quests/{ident}.quest"
        current = self.read(target)
        if current is not None and body.get("hash") != digest(current):
            raise ValueError("That quest ID exists or changed. Open it from the quest library to edit, or choose a new ID.")
        if current is not None:
            from metin2_studio.quest_templates import library
            previous = next((row['template'] for row in library(self) if row['id'] == target.relative_to(self.root).as_posix()), None)
            if previous and previous.get('template', 'hunt') != body.get('template', 'hunt'):
                raise ValueError('Clone this quest with a new ID to change its template. Existing character states must retain their original state names.')
        from metin2_studio.quest_support import build_changes
        changes = {target: code.encode("ascii"), **build_changes(self)}
        return self.plan(("Update quest: " if current is not None else "Create quest: ") + ident, changes, "Native NPC markers and quest letters guide eligible players to accept and return. Objectives name their targets and show progress. Existing quest states and completion are retained. Apply compiles with the installed qc and loads the quest after a successful build and restart.")

    def plan(self, title, changes, hint, redact=False, from_disk=False, metadata=None):
        with self.lock:
            self.require_running()
            if not (metadata or {}).get('saveRecovery'):
                self.save_recovery.require_clear()
            if self.server_busy():
                raise ValueError("Wait for the current server apply to finish before saving files.")
            files, views = [], []
            tracked = {row['path']: row for row in self.workspace.tracked()} if not from_disk else {}
            deferred = self.workspace.deferred_paths() if not from_disk else set()
            for path, new in changes.items():
                path = self.safe(path)
                old = (path.read_bytes() if path.exists() else None) if from_disk else self.read(path)
                if old == new:
                    continue
                if path.relative_to(self.root).as_posix() in deferred:
                    raise ValueError('Review this file\'s pending custom merge in Update protection before making another edit.')
                check_change(self, path, old, new)
                record = tracked.get(path.relative_to(self.root).as_posix())
                if not ACTIVE_CHANGESET.get() and record and old != record['expected'] and self.workspace.compare(record, old).choices:
                    raise ValueError('An update affected custom changes in ' + path.name + '. Review Update protection before editing this file.')
                files.append((path, old, new))
                a, b = text_decode(old or b"")[0], text_decode(new or b"")[0]
                if redact or path.name == '.env':
                    allowed = set(self.settings_schema)
                    a = "\n".join(x for x in a.splitlines() if x.split("=", 1)[0] in allowed)
                    b = "\n".join(x for x in b.splitlines() if x.split("=", 1)[0] in allowed)
                diff = "\n".join(difflib.unified_diff(a.splitlines(), b.splitlines(), fromfile="before", tofile="after", lineterm=""))
                views.append({"path": path.relative_to(self.root).as_posix(), "diff": diff[:120000]})
            if not files and not metadata:
                raise ValueError("There are no changes to save.")
            key = secrets.token_urlsafe(18)
            self.plans = {k: v for k, v in self.plans.items() if time.time() - v["time"] < 1800}
            changeset = None if from_disk else ACTIVE_CHANGESET.get()
            self.plans[key] = {"title": title, "files": files, "time": time.time(), "hint": hint, "changeset": changeset, "metadata": metadata or {}}
            return {"id": key, "title": title, "files": views, "hint": hint, "changeset": changeset}

    def commit(self, key):
        with self.lock:
            self.require_running()
            if self.server_busy():
                raise ValueError("Wait for the server apply to finish.")
            p = self.plans.get(key)
            if not p or time.time() - p["time"] > 1800:
                raise ValueError("Review expired. Preview the change again.")
            if p.get('metadata', {}).get('saveRecovery'):
                return self.save_recovery.commit(key, p)
            self.save_recovery.require_clear()
            for path, old, new in p['files']:
                check_change(self, path, old, new)
                rel = path.relative_to(self.root).as_posix()
                if rel in self.workspace.deferred_paths() and rel not in p.get('metadata', {}).get('reconciled', {}):
                    raise ValueError('A custom merge is pending for ' + path.name + '. Review it in Update protection first.')
            for rel, original, custom, expected in p.get('metadata', {}).get('adopt', []):
                check_change(self, self.root / rel, original, custom)
            for rel, (original, custom, expected) in p.get('metadata', {}).get('reconciled', {}).items():
                check_change(self, self.root / rel, original, custom)
            if p.get('changeset'):
                result = self.workspace.stage(p)
                del self.plans[key]
                return result
            if 'tracking' in p.get('metadata', {}) and p['metadata']['tracking'] != self.workspace.signature():
                raise ValueError('Customisation tracking changed since review. Scan again.')
            for guarded_path, expected in p.get('metadata', {}).get('guards', []):
                guarded_path = self.safe(guarded_path)
                observed = guarded_path.read_bytes() if guarded_path.exists() else None
                if observed != expected:
                    raise ValueError(guarded_path.name + ' changed since review. Scan again.')
            for path, old, new in p["files"]:
                current = path.read_bytes() if path.exists() else None
                if current != old:
                    raise ValueError(f"{path.name} changed since review. Reopen it and preview again.")
            ident = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(4)
            folder = self.state / "backups" / ident
            folder.mkdir(parents=True)
            from metin2_studio.save_recovery import durable_bytes, manifest_write
            manifest = {"id": ident, "title": p["title"], "time": datetime.now(timezone.utc).isoformat(), "hint": p["hint"], "status": "saving", "files": [],
                        "category": history_category(p['title'], p.get('metadata'))}
            for i, (path, old, new) in enumerate(p["files"]):
                if old is not None:
                    durable_bytes(folder / f"{i}.before", old)
                if new is not None:
                    durable_bytes(folder / f"{i}.after", new)
                manifest["files"].append({"path": path.relative_to(self.root).as_posix(), "existed": old is not None, "before": digest(old) if old is not None else None, "after": digest(new) if new is not None else None})
            mp = folder / "manifest.json"
            manifest_write(mp, manifest)
            done = []
            try:
                for path, old, new in p["files"]:
                    self.write(path, new)
                    done.append((path, old))
                self.workspace.record_commit(p['files'], p['title'], ident, p.get('metadata'))
            except Exception:
                for path, old, new in reversed(p['files']):
                    observed = path.read_bytes() if path.exists() else None
                    if observed == new and observed != old:
                        self.write(path, old)
                unchanged = all((path.read_bytes() if path.exists() else None) == old for path, old, _ in p['files'])
                manifest["status"] = "rolled-back" if unchanged else "saving"
                manifest_write(mp, manifest)
                raise
            manifest["status"] = "saved"
            manifest_write(mp, manifest)
            del self.plans[key]
            return {"id": ident, "title": p["title"], "hint": p["hint"], "publishedSet": p.get('metadata', {}).get('publishSet')}

    @staticmethod
    def write(path, raw):
        if raw is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".studio-" + secrets.token_hex(4))
        try:
            from metin2_studio.save_recovery import durable_bytes
            durable_bytes(temp, raw)
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def history(self):
        result = []
        from metin2_studio.save_recovery import read_receipt
        for p in sorted((self.state / "backups").glob("*/manifest.json"), reverse=True):
            record = read_receipt(p)
            record['category'] = history_category(record['title'], record)
            record['areas'] = history_areas(record['files'])
            if record.get('error'):
                record.update(canRestore=False, restoreReason=record['error'])
                result.append(record)
                continue
            newer = []
            for file in record['files']:
                path = self.safe(self.root / file['path'])
                raw = path.read_bytes() if path.exists() else None
                if (digest(raw) if raw is not None else None) != file['after']:
                    newer.append(file['path'])
            record['canRestore'] = record['status'] == 'saved' and not newer
            record['restoreReason'] = 'Newer edits exist in: ' + ', '.join(newer) + '. Revert the newest related change first.' if newer else 'Reverts the saved files to their exact contents before this change. Review the diff first; Apply loads the rollback.'
            if record['status'] in ('saving', 'recovering'):
                record['restoreReason'] = 'Interrupted save. Open Drafts & changes and Review recovery before saving or applying.'
            elif record['status'] == 'rolled-back':
                record['restoreReason'] = record.get('recovery', 'This save was rolled back; no completed save is available to revert.')
            result.append(record)
        return result[:100]

    def restore_plan(self, ident):
        if not re.fullmatch(r"\d{8}T\d{6}-[a-f0-9]{8}", ident):
            raise ValueError("Invalid backup ID.")
        folder = self.state / "backups" / ident
        record = json.loads((folder / "manifest.json").read_text("utf-8"))
        if record["status"] != "saved":
            raise ValueError("This backup was not completed.")
        changes = {}
        for i, f in enumerate(record["files"]):
            path = self.safe(self.root / f["path"])
            current = path.read_bytes() if path.exists() else None
            if (digest(current) if current is not None else None) != f["after"]:
                raise ValueError(f"{path.name} has newer edits. Restore the newest related change first.")
            changes[path] = (folder / f"{i}.before").read_bytes() if f["existed"] else None
        plan = self.plan("Revert: " + record["title"], changes, "This restores every listed file to its contents before the selected change. Review the diff, then Revert saved changes. A new backup preserves the current files. Apply separately to load the rollback; character data and items are unaffected.", redact=any(p.name == ".env" for p in changes), metadata={'historyCategory': history_category(record['title'], record)})
        plan['confirmLabel'] = 'Revert saved changes'
        return plan

    def docker_status(self):
        try:
            p = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True, timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return {"available": p.returncode == 0, "version": p.stdout.strip() if p.returncode == 0 else None}
        except (OSError, subprocess.TimeoutExpired):
            return {"available": False, "version": None}

    def runtime_health(self, fresh=False):
        if not fresh and self._health_cache and time.time()-self._health_cache['at'] < 15:
            return self._health_cache
        result = {'at': time.time(), 'known': False, 'services': [], 'gameHealthy': False}
        try:
            run = subprocess.run(['docker', 'compose', 'ps', '--format', 'json'], cwd=self.compose, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=8, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if run.returncode:
                raise ValueError('Compose health unavailable.')
            records = json.loads(run.stdout) if run.stdout.lstrip().startswith('[') else [json.loads(line) for line in run.stdout.splitlines() if line.strip()]
            result['services'] = [{'service': str(row.get('Service', 'unknown')), 'state': str(row.get('State', 'unknown')), 'health': str(row.get('Health') or 'not reported')} for row in records]
            result['known'] = True
            result['gameHealthy'] = any(row['service'] == 'game' and row['state'] == 'running' and row['health'] == 'healthy' for row in result['services'])
        except (ValueError, OSError, subprocess.TimeoutExpired):
            result['error'] = 'Runtime health could not be verified. Docker availability alone is not game health.'
        self._health_cache = result
        return result

    def build_fingerprints(self):
        paths = {self.safe(self.root / row['path']) for row in self.workspace.tracked()}
        paths.update(self.safe(self.root / rel) for rel in self.workspace.pending_saved_paths())
        paths.update(path for path, _, _ in self.sources.values())
        paths.update((self.game / 'Dockerfile', self.game / '.dockerignore', self.compose / '.env', self.root / 'VERSION'))
        result = {}
        for path in paths:
            raw = path.read_bytes() if path.is_file() else None
            if path == self.compose / '.env' and raw is not None:
                from metin2_studio.workspace import env_values
                values = env_values(raw)
                raw = b'\n'.join(key.encode() + b'=' + values.get(key.encode(), str(schema['default']).encode()) for key, schema in sorted(self.settings_schema.items()))
            result[path.relative_to(self.root).as_posix()] = digest(raw) if raw is not None else None
        return result

    def native_pending(self):
        stored = self.workspace.preference('nativeUpdatePending', {})
        if stored:
            return stored
        if (self.root / '.m2launcher-rebuild-pending').is_file():
            return {'ready': True, 'external': True}
        return {}

    def apply(self, validate_only=False, acknowledge_interrupted=None):
        context = ACTIVE_CHANGESET.set(None)
        try:
            return self._apply_saved(validate_only, acknowledge_interrupted)
        finally:
            ACTIVE_CHANGESET.reset(context)

    def _apply_saved(self, validate_only=False, acknowledge_interrupted=None):
        with self.lock:
            self.require_running()
            self.save_recovery.require_clear()
            previous = self.workspace.interrupted_deployment()
            if previous:
                from metin2_studio.operation_process import previous_build_running
                if previous_build_running(previous.get('process')):
                    raise ValueError('The previous build command is still running. Wait for it to finish before validating or applying again.')
                if not validate_only and acknowledge_interrupted != previous['id']:
                    raise ValueError('Inspect the game launcher and previous build commands, then acknowledge the interrupted deployment in Apply before retrying.')
            if self.server_busy():
                raise ValueError("An apply is already running.")
            if self.workspace.scan(include_deferred=False)['affectedFiles']:
                raise ValueError('Review the affected custom changes in Update protection before applying.')
            pending = self.native_pending()
            if pending and not pending.get('ready'):
                raise ValueError('Customisation recovery for the installed package is incomplete. Resolve Update protection before applying.')
            if not validate_only and not pending and not self.workspace.summary()['pending'] and not self.native_crafting.pending():
                raise ValueError('There are no saved changes to apply. Drafts must be reviewed and saved first.')
            if not validate_only and not pending:
                self.native_crafting.preflight()
            if not self.docker_status()["available"]:
                raise ValueError("Start Docker Desktop first, wait for Engine running, then apply again.")
            self.job = {"status": "running", "kind": 'validation' if validate_only else 'apply', "lines": ["Building and compiling without a game restart." if validate_only else "Building game files and compiling quests. The game will restart after a successful build."], "started": time.time(), 'id': secrets.token_hex(12), 'files': self.build_fingerprints()}
            self.workspace.deployment(self.job['id'], 'running', {'kind': self.job['kind'], 'files': self.job['files']})
            self._apply_thread = threading.Thread(target=self.run_apply, args=(validate_only,), daemon=False)
            self._apply_thread.start()
        return self.job

    def run_apply(self, validate_only=False):
        job = self.job
        commands = [["docker", "compose", "build", "game"], ["docker", "compose", "up", "-d", "--wait", "--wait-timeout", "120", "mariadb"], ["docker", "compose", "stop", "game"], ["docker", "compose", "up", "-d", "--no-deps", "--force-recreate", "playerbot-migrate"], ["docker", "compose", "wait", "playerbot-migrate"], ["docker", "compose", "up", "-d", "--no-deps", "--force-recreate", "game"]]
        native_pending = {}
        try:
            native_pending = self.native_pending()
            if native_pending and not validate_only:
                commands = [['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(self.root / 'Metin2-Launcher.ps1'), '-Action', 'Start', '-Yes']]
            if validate_only:
                commands = commands[:1]
            elif not native_pending and (self.native_crafting.config()['recipes'] or self.native_crafting.applied()['recipes']):
                native_step = ['studio', 'native-crafting']
                commands.insert(-1, native_step)
            deployment_progress.prepare(job, validation=validate_only, native_update=bool(native_pending),
                                        crafting=['studio', 'native-crafting'] in commands)
            for cmd in commands:
                deployment_progress.enter(job, deployment_progress.command_stage(cmd))
                if cmd == ['studio', 'native-crafting']:
                    if self.build_fingerprints() != job.get('files'):
                        raise ValueError('Saved configuration changed during the build. Native crafting was not written; review and Apply again.')
                    changed = self.native_crafting.apply()
                    job['lines'].append(f'{changed} native crafting definitions verified and applied in a guarded transaction.')
                    continue
                job["lines"].append("> " + " ".join(cmd))
                p = subprocess.Popen(cmd, cwd=self.compose, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    if type(p.pid) is int:
                        from metin2_studio.operation_process import process_identity
                        job['process'] = {'pid': p.pid, 'identity': process_identity(p.pid)}
                        self.workspace.deployment(job['id'], 'running', {'kind': job.get('kind'), 'files': job.get('files', {}), 'lines': job['lines'], 'process': job['process'], 'progress': job.get('progress')})
                    for line in p.stdout:
                        # Do not return credentials accidentally printed by third-party scripts.
                        if re.search(r"password|secret|token", line, re.I):
                            line = "[credential-related log line hidden]\n"
                        job["lines"].append(line.rstrip())
                        job["lines"] = job["lines"][-600:]
                    exit_code = p.wait()
                except BaseException:
                    # Do not declare failure/release guards while the launched
                    # command is still running, even if receipt writing fails.
                    try:
                        p.communicate()
                    finally:
                        p.wait()
                    raise
                if exit_code != 0:
                    raise ValueError("Command failed. Review the output. Saved source files and backups are retained.")
                job.pop('process', None)
                if job.get('id'):
                    self.workspace.deployment(job['id'], 'running', {'kind': job.get('kind'), 'files': job.get('files', {}), 'lines': job['lines'], 'progress': job.get('progress')})
                if cmd[2:4] == ["wait", "playerbot-migrate"]:
                    check = subprocess.run(["docker", "compose", "ps", "-a", "--format", "json", "playerbot-migrate"], cwd=self.compose, capture_output=True, text=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    records = json.loads(check.stdout) if check.stdout.strip().startswith("[") else [json.loads(x) for x in check.stdout.splitlines() if x.strip()]
                    if check.returncode or not records or any(int(x.get("ExitCode", -1)) != 0 or x.get("State") != "exited" for x in records):
                        raise ValueError("Settings migration did not exit successfully. Game was left stopped; inspect it in the launcher before restarting.")
            deployment_progress.enter(job, 'sources')
            if self.build_fingerprints() != job.get('files'):
                raise ValueError('A source file changed during the build. Its deployed configuration cannot be verified; review and build again.')
            if validate_only:
                job['status'] = 'validated'
                job['lines'].append('Build and quest compilation passed. No game restart or settings migration was performed.')
            else:
                deployment_progress.enter(job, 'health')
                health = self.runtime_health(True)
                deadline = time.time() + 60
                while not health['gameHealthy'] and time.time() < deadline:
                    time.sleep(3)
                    health = self.runtime_health(True)
                job['health'] = health
                job['status'] = 'succeeded' if health['gameHealthy'] else 'unverified'
                if health['gameHealthy']:
                    deployment_progress.enter(job, 'content')
                    from metin2_studio.runtime_checks import verify
                    runtime = verify(self)
                    job['runtime'] = runtime
                    if runtime['issues']:
                        job['status'] = 'unverified'
                        job['lines'].append('Runtime content verification needs attention:')
                        job['lines'].extend(runtime['issues'][:80])
                    elif runtime['checkedFields']:
                        job['lines'].append(str(runtime['checkedFields']) + ' customised drop fields verified in runtime files.')
                    if runtime['questAccess']['readable']:
                        job['lines'].append(runtime['questAccess']['detail'])

                job['lines'].append('Game health verified.' if health['gameHealthy'] else 'Commands completed; game health is not verified. Inspect runtime status before considering this deployment complete.')
                if job['status'] == 'succeeded' and native_pending:
                    self.workspace.set_preference('nativeUpdatePending', {})
        except Exception as e:
            job["status"] = "failed"
            job["lines"].append(str(e))
        finally:
            deployment_progress.finish(job)
            if job.get('id'):
                self.workspace.deployment(job['id'], job['status'], {'kind': job.get('kind'), 'files': job.get('files', {}), 'lines': job['lines'][-80:], 'health': job.get('health'), 'runtime': job.get('runtime'), 'progress': job.get('progress')})


class Handler(BaseHTTPRequestHandler):
    studio: Studio

    def log_message(self, fmt, *args):
        pass

    def send(self, data, status=200, mime="application/json; charset=utf-8", filename=None):
        raw = json.dumps(data, ensure_ascii=True).encode() if mime.startswith("application/json") and not isinstance(data, bytes) else data
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        try:
            self.end_headers()
            self.wfile.write(raw)
        except ConnectionError:
            pass  # A browser navigation may cancel an in-flight status request.

    def guard(self, mutate=False):
        port = self.server.server_port
        if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            raise ValueError("Only localhost access is allowed.")
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            raise ValueError("Origin is not allowed.")
        if mutate and self.headers.get("X-Studio-Token") != self.studio.token:
            raise ValueError("Session expired. Reload the page.")

    def do_GET(self):
        ACTIVE_CHANGESET.set(None)
        try:
            self.guard()
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            s = self.studio
            if u.path.startswith('/api/addons/'):
                route = u.path.removeprefix('/api/addons/')
                if route == 'map-image':
                    image = s.addons.world().image_path(int(q.get('map', '64')))
                    if image is None or not image.is_file():
                        return self.send({'error': 'No installed map image is available.'}, 404)
                    return self.send(image.read_bytes(), mime='image/png')
                return self.send({'ok': True, **s.addons.get(route, q)})
            ACTIVE_CHANGESET.set(q.get('changeset') or self.headers.get('X-Studio-Changeset') or None)
            if u.path.startswith('/api/economy') or u.path in ('/api/item-usage', '/api/item-drop-summary', '/api/mob-summary'):
                ACTIVE_CHANGESET.set(None)
            if u.path == '/api/workspace':
                return self.send(s.workspace.summary())
            if u.path == '/api/health':
                return self.send(s.runtime_health(q.get('fresh') == '1'))
            if u.path == '/api/search':
                return self.send(studio_search(s, q.get('q', ''), q.get('content') == '1'))
            if u.path == '/api/drop-index':
                with s.lock:
                    return self.send(drop_index(s))
            if u.path == '/api/drop-combined':
                with s.lock:
                    return self.send(combined_drops(s, q.get('id', ''), q.get('kind', 'mob')))
            if u.path == '/api/table':
                return self.send(table_view(s, s.file(q['id'])))
            if u.path == '/api/drafts':
                return self.send(s.workspace.drafts(q.get('id')))
            if u.path == '/api/changeset':
                return self.send(s.workspace.change_set(q['id']))
            if u.path == '/api/customisations/adopt-sources':
                return self.send(s.workspace.adoption_sources())
            if u.path == '/api/customisations':
                with s.lock:
                    return self.send(s.workspace.scan())
            if u.path == '/api/updates/status':
                return self.send(s.updates.job)
            if u.path == '/api/updates/package':
                return self.send(s.updates.preview(q['id']))
            if u.path == '/api/updates/available':
                return self.send(s.updates.check())
            if u.path == '/api/catalog':
                with s.lock:
                    result = {'catalogue': s.catalogue_status()}
                    if q.get('revision') != result['catalogue'].get('revision'):
                        result.update(items=list(s.items.values()), mobs=list(s.mobs.values()))
                    return self.send(result)
            if u.path == "/api/bootstrap":
                with s.lock:
                    return self.send({"application": APPLICATION, "projectRoot": str(HERE), "modules": ["server", "addons"], "studioVersion": studio_version(), "stateDir": str(s.state), "mode": "configuration-and-quests", "token": s.token, "root": str(s.root), "version": (s.root / "VERSION").read_text().strip(), "counts": {"items": len(s.items), "mobs": len(s.mobs), "settings": len(s.settings_schema), "files": len(s.inventory())}, "catalogue": s.catalogue_status(), "items": list(s.items.values()), "mobs": list(s.mobs.values()), "groups": s.groups()})
            if u.path == "/api/group":
                return self.send(s.group(q["source"], q["key"]))
            if u.path == "/api/drop-source":
                source = q["source"]
                if source not in s.sources:
                    raise ValueError("Unknown source.")
                return self.send({"hash": digest(s.source_raw(source)), "file": s.sources[source][0].relative_to(s.root).as_posix()})
            if u.path == "/api/quests":
                from metin2_studio.quest_templates import library
                return self.send(library(s))
            if u.path == '/api/quest-fields':
                from metin2_studio.quest_fields import analyse
                with s.lock:
                    return self.send(analyse(s, q['id']).public())
            if u.path == '/api/quest-help':
                from metin2_studio.quest_description import describe
                with s.lock:
                    return self.send(describe(s, q['id']))
            if u.path == "/api/settings":
                return self.send(s.settings())
            if u.path == "/api/files":
                return self.send(s.inventory())
            if u.path == "/api/crafting-access":
                return self.send(s.crafting_access())
            if u.path == '/api/crafting':
                with s.lock:
                    return self.send(s.crafting_catalog(q.get('fresh') == '1'))
            if u.path == '/api/crafting/conflicts':
                with s.lock:
                    return self.send(s.native_crafting.review())
            if u.path == "/api/recipes":
                return self.send([{k: v for k, v in r.items() if k not in ("start", "end")} for r in s.recipes()])
            if u.path == "/api/item-usage":
                with s.lock:
                    data = item_usage(s, q["id"], sql_rows, native=True)
                return self.send(data)
            if u.path == "/api/item-drop-summary":
                with s.lock:
                    data = item_drop_summary(s, q["id"])
                return self.send(data)
            if u.path == "/api/economy":
                return self.send(s.economy.report(q, fresh=q.get('fresh') == '1'))
            if u.path == "/api/economy/export":
                format = q.get('format', 'zip')
                if format not in ('zip', 'json'):
                    raise ValueError('Choose a CSV pack (zip) or JSON export.')
                raw, mime, filename = economy_download(s.economy.export(q), format)
                return self.send(raw, mime=mime, filename=filename)
            if u.path == "/api/file":
                return self.send(s.file(q["id"]))
            if u.path == "/api/history":
                return self.send(s.history())
            if u.path == '/api/activity':
                rows = [{'kind': 'server', 'title': row['title'], 'at': row['at'], 'detail': row.get('kind', ''), 'route': 'history'}
                        for row in s.workspace.summary().get('recent', [])]
                try:
                    for row in s.addons.get('history', {})['history']:
                        rows.append({'kind': 'addon', 'title': ('Previous Hub · ' if row.get('legacy') else '') + row.get('action', 'Add-on change') + ' ' + row.get('addon_id', ''),
                                     'at': row.get('time', row.get('at', '')), 'detail': row.get('status', ''), 'route': 'installed'})
                except (ValueError, OSError):
                    pass
                def activity_time(row):
                    if isinstance(row['at'], (int, float)):
                        return row['at']
                    try:
                        return datetime.fromisoformat(str(row['at']).replace('Z', '+00:00')).timestamp()
                    except ValueError:
                        return 0
                return self.send({'items': sorted(rows, key=activity_time, reverse=True)[:100]})
            if u.path == "/api/status":
                return self.send({"docker": s.docker_status(), "health": s.runtime_health(), "job": s.public_job(), "catalogue": s.catalogue_status()})
            if u.path.startswith('/mob-icons/'):
                ident = unquote(u.path.split('/')[-1])
                p = s.catalogue.icon(ident, 'mob')
                return self.send(p.read_bytes() if p else b'', 200 if p else 404, 'image/png')
            if u.path == '/api/mob-summary':
                from metin2_studio.item_usage import mob_summary
                with s.lock:
                    return self.send(mob_summary(s, q.get('id', '')))
            if u.path.startswith("/icons/"):
                ident = unquote(u.path.split("/")[-1])
                p = s.catalogue.icon(ident) if hasattr(s, 'catalogue') else icon_path(s.root, s.icons, ident)
                if p:
                    return self.send(p.read_bytes(), mime="image/png")
                return self.send(b"", 404, "image/png")
            if u.path == '/crafting.js':
                return self.send((HERE / 'web/crafting.js').read_bytes(), mime='application/javascript; charset=utf-8')
            static = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "application/javascript; charset=utf-8"), "/workspace.js": ("workspace.js", "application/javascript; charset=utf-8"), "/editors.js": ("editors.js", "application/javascript; charset=utf-8"), "/quests.js": ("quests.js", "application/javascript; charset=utf-8"), "/economy_tools.js": ("economy_tools.js", "application/javascript; charset=utf-8"), "/economy.js": ("economy.js", "application/javascript; charset=utf-8"), "/navigation.js": ("navigation.js", "application/javascript; charset=utf-8"), "/catalog.js": ("catalog.js", "application/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
            static.update({'/operations.js': ('operations.js', 'application/javascript; charset=utf-8'),
                           '/interface.css': ('interface.css', 'text/css; charset=utf-8')})
            if u.path in static:
                filename, mime = static[u.path]
                return self.send((HERE / "web" / filename).read_bytes(), mime=mime)
            addon_static = {'/addons.mjs': 'addons.mjs', '/addon_helpers.mjs': 'addon_helpers.mjs',
                            '/addon_jobs.mjs': 'addon_jobs.mjs', '/addons.css': 'addons.css'}
            if u.path in addon_static:
                name = addon_static[u.path]
                mime = 'text/css; charset=utf-8' if name.endswith('.css') else 'application/javascript; charset=utf-8'
                return self.send((HERE / 'web' / name).read_bytes(), mime=mime)
            self.send({"error": "Not found"}, 404)
        except (ValueError, KeyError, OSError, zipfile.BadZipFile) as e:
            self.send({"error": str(e)}, 400)

    def do_POST(self):
        try:
            if urlparse(self.path).path == '/api/shutdown':
                return self._post()
            with self.studio.mutation_request():
                return self._post()
        except ValueError as error:
            self.send({'error': str(error)}, 400)

    def _post(self):
        ACTIVE_CHANGESET.set(None)
        try:
            self.guard(True)
            self.connection.settimeout(30)
            length = int(self.headers.get("Content-Length", 0))
            if urlparse(self.path).path == '/api/addons/packages/import':
                if self.headers.get('Content-Type') != 'application/zip' or self.headers.get('Transfer-Encoding'):
                    raise ValueError('Upload an add-on ZIP with a known byte length.')
                self.connection.settimeout(30)
                with self.studio.lock:
                    return self.send({'ok': True, **self.studio.addons.import_archive(
                        self.rfile, length, unquote(self.headers.get('X-Addon-Filename', 'addon.m2addon.zip')))})
            if urlparse(self.path).path == '/api/updates/package':
                if self.headers.get('Content-Type') != 'application/zip':
                    raise ValueError('Upload a ZIP package.')
                with self.studio.lock:
                    return self.send(self.studio.updates.stage(self.rfile, length, self.headers.get('X-Package-SHA256', '')))
            if length < 1 or length > 12000000 or not self.headers.get("Content-Type", "").startswith("application/json"):
                raise ValueError("A JSON request under 12 MB is required.")
            b = json.loads(self.rfile.read(length))
            s, path = self.studio, urlparse(self.path).path
            if path.startswith('/api/addons/'):
                if length > 65536 or not isinstance(b, dict):
                    raise ValueError('Use a JSON object under 64 KB for add-on operations.')
                with s.lock:
                    return self.send({'ok': True, **s.addons.post(path.removeprefix('/api/addons/'), b)},
                                     202 if path == '/api/addons/jobs/start' else 200)
            if path == '/api/shutdown':
                s.request_shutdown()
                self.send({'ok': True, 'message': 'Stopping this Studio only.'})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            ACTIVE_CHANGESET.set(self.headers.get('X-Studio-Changeset') or None)
            if path.startswith("/api/economy"):
                ACTIVE_CHANGESET.set(None)
            if path == "/api/preferences":
                key = str(b.get("key", ""))
                if key not in ("itemFavourites", "itemRecent", "economyWatchlist"):
                    raise ValueError("Unknown preference.")
                if not isinstance(b.get('value'), list) or len(b['value']) > 200 or any(str(ident) not in s.items for ident in b['value']):
                    raise ValueError('Choose at most 200 known catalog items.')
                if len(json.dumps(b.get("value"))) > 20000:
                    raise ValueError("Preference is too large.")
                return self.send(s.workspace.set_preference(key, b.get("value")))
            if path == '/api/drafts/save':
                return self.send(s.workspace.save_draft(b))
            if path == '/api/catalog/reload':
                return self.send(s.reload_catalog())
            if path == '/api/recovery/preview':
                with s.lock:
                    return self.send(s.save_recovery.preview(b['id']))
            if path == '/api/validate':
                return self.send(s.apply(validate_only=True))
            if path == '/api/preview/bulk-drops':
                return self.send(bulk_drop_plan(s, b))
            if path == '/api/preview/table':
                return self.send(table_plan(s, b))
            if path == '/api/drafts/delete':
                return self.send(s.workspace.remove_draft(b['id']))
            if path == '/api/drafts/to-set':
                return self.send(s.workspace.draft_to_set(b['id']))
            if path == '/api/changesets/review-update':
                return self.send(s.workspace.review_set(b['id']))
            if path == '/api/changesets/rebase':
                return self.send(s.workspace.rebase_set(b))
            if path == '/api/changesets/create':
                return self.send(s.workspace.create_set(b))
            if path == '/api/changesets/preview':
                return self.send(s.workspace.publish_plan(b['id']))
            if path == '/api/customisations/adopt':
                return self.send(s.workspace.adopt_plan(b))
            if path == '/api/customisations/preview':
                with s.lock:
                    return self.send(s.workspace.reconcile_plan(b))
            if path == '/api/customisations/defer':
                with s.lock:
                    return self.send(s.workspace.defer_plan(b))
            if path == '/api/updates/recovery':
                pending = s.workspace.preference('nativeUpdatePending', {})
                if not pending or pending.get('ready'):
                    raise ValueError('No incomplete custom recovery is pending.')
                if s.workspace.scan(include_deferred=False)['affectedFiles']:
                    raise ValueError('Resolve all affected custom entries before completing recovery.')
                pending['ready'] = True
                s.workspace.set_preference('nativeUpdatePending', pending)
                return self.send({'ready': True})
            if path == '/api/updates/download':
                return self.send(s.updates.download())
            if path == '/api/updates/install':
                return self.send(s.updates.install(b))
            if path == '/api/economy/schedule':
                return self.send(s.economy.tools.schedule(b))
            if path == '/api/economy/experiment':
                return self.send(s.economy.tools.experiment(b))
            if path == '/api/economy/capture':
                return self.send(s.economy.capture(b))
            if path == '/api/economy/note':
                return self.send(s.economy.note(b))
            if path == '/api/preview/quest-fields':
                from metin2_studio.quest_fields import plan
                with s.lock:
                    return self.send(plan(s, b))
            if path == '/api/preview/crafting-resolve':
                with s.lock:
                    return self.send(s.native_crafting.resolve(b))
            actions = {"/api/preview/drop": s.drop_plan, "/api/preview/settings": s.settings_plan, "/api/preview/file": s.file_plan, "/api/preview/quest": s.quest_plan, "/api/preview/recipe": s.recipe_plan, "/api/preview/recipe-delete": s.recipe_delete_plan, "/api/preview/quest-delete": s.quest_delete_plan, "/api/commit": lambda x: s.commit(x["id"]), "/api/preview/restore": lambda x: s.restore_plan(x["id"]), "/api/apply": lambda x: s.apply(acknowledge_interrupted=x.get('acknowledgeInterrupted')), "/api/quest-code": lambda x: {"code": s.quest_code(x)[1]}}
            if path not in actions:
                return self.send({"error": "Not found"}, 404)
            self.send(actions[path](b))
        except (ValueError, KeyError, OSError, TypeError, zipfile.BadZipFile) as e:
            self.send({"error": str(e)}, 400)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--state", type=Path, default=None, help="Separate Studio data folder for another installation or disposable test world.")
    args = parser.parse_args()
    lock = None
    try:
        selected = resolve_settings(args.root, args.port, args.state)
        from metin2_studio.local_lock import StudioLocks
        lock = StudioLocks(selected['serverRoot'], selected['stateDir']).acquire()
        bind_state(selected)
        Handler.studio = Studio(Path(selected['serverRoot']), Path(selected['stateDir']))
    except (ValueError, OSError) as error:
        if lock:
            lock.close()
        parser.error(str(error))
    if Handler.studio.workspace.preference('economySchedule', None) is None:
        Handler.studio.economy.tools.schedule({'enabled': True, 'minutes': 60, 'retention': 180, 'filters': {}})
    Handler.studio.economy.tools.start()
    Handler.studio.start_catalogue_sync()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", selected['port']), Handler)
        server.daemon_threads = False  # Close waits for in-flight handlers.
    except OSError:
        Handler.studio.economy.tools.stop.set()
        Handler.studio._catalogue_stop.set()
        lock.close()
        parser.error(f"Local port {selected['port']} is unavailable. Close the other Studio instance or choose another --port.")
    print(f"Metin2 Server Studio {studio_version()}: http://127.0.0.1:{selected['port']}", flush=True)
    print("Reading installed files. Changes require Review then Save. Ctrl+C closes Studio.", flush=True)
    run_file = Path(selected['stateDir']) / 'studio-run.json'
    from metin2_studio.installation import atomic_json
    atomic_json(run_file, {'application': APPLICATION, 'projectRoot': str(HERE), 'stateDir': selected['stateDir'],
                           'url': 'http://127.0.0.1:%s' % selected['port']})
    try:
        while True:
            try:
                server.serve_forever()
                break
            except KeyboardInterrupt:
                try:
                    Handler.studio.request_shutdown()
                    break
                except ValueError as error:
                    print(str(error), flush=True)
    finally:
        Handler.studio.economy.tools.stop.set()
        Handler.studio._catalogue_stop.set()
        server.server_close()
        lock.close()
        run_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
