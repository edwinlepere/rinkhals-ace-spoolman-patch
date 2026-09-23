#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Edwin Lepere - License: GPL-3.0 (see the LICENSE file of the repository)
#
# +==================================================================+
# |                                                                  |
# |           *   Patched by Edwin Lepere <Mazerakam>   *            |
# |                                                                  |
# |        --------------------------------------------------        |
# |     Rinkhals mmu_ace.py  -  Spoolman + ACE Pro  -  10 patches     |
# |                        Anycubic Kobra S1                         |
# |                                                                  |
# |        Unofficial community patch - use at your own risk         |
# |             Not affiliated with Rinkhals or Anycubic             |
# |                                                                  |
# +==================================================================+
#
# USAGE   (on the printer, over SSH - no need to cd anywhere)
#   python3 patch_mmu_ace.py --restart
#
# OPTIONS
#   --restart    restart Moonraker after patching
#   --undo       restore the original mmu_ace.py from the automatic backup
#   --path FILE  patch a specific mmu_ace.py instead of the active Rinkhals one
#
# TESTED  Rinkhals 20260716_02, Kobra S1 + ACE Pro (single ACE).
#         On any other version the script refuses safely and changes nothing.
# BACKUP  mmu_ace.py.orig is created automatically (only if it does not exist).

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time

BANNER = """
+==================================================================+
|                                                                  |
|           *   Patched by Edwin Lepere <Mazerakam>   *            |
|                                                                  |
|        --------------------------------------------------        |
|     Rinkhals mmu_ace.py  -  Spoolman + ACE Pro  -  10 patches     |
|                        Anycubic Kobra S1                         |
|                                                                  |
|        Unofficial community patch - use at your own risk         |
|             Not affiliated with Rinkhals or Anycubic             |
|                                                                  |
+==================================================================+
"""

# Friendly message instead of a traceback when the patch cannot be applied.
# Nothing is written to disk until every check has passed.
def _fail(exc_type, exc, tb):
    if exc_type is AssertionError:
        print("\n[!] Patch NOT applied - mmu_ace.py is unchanged.")
        print("    " + str(exc))
        print("    This is a different Rinkhals version than the one tested (20260716_02).")
    else:
        sys.__excepthook__(exc_type, exc, tb)
sys.excepthook = _fail


def find_target(path_arg):
    if path_arg:
        candidates = [path_arg]
    else:
        candidates = [
            os.path.join(os.getcwd(), "mmu_ace.py"),
            "/useremain/rinkhals/.current/home/rinkhals/apps/40-moonraker/mmu_ace.py",
        ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    sys.exit("mmu_ace.py not found. Run this on the printer (SSH), "
             "or pass --path /full/path/to/mmu_ace.py")


def _pids_matching(needle):
    """PIDs of running processes whose command line contains `needle` (Linux /proc)."""
    pids = []
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == os.getpid():
            continue
        try:
            with open("/proc/" + name + "/cmdline", "rb") as f:
                cmdline = f.read().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if needle in cmdline:
            pids.append(int(name))
    return pids


def restart_moonraker(folder):
    app = os.path.join(folder, "app.sh")
    if not os.path.isfile(app):
        print("app.sh not found - restart Moonraker manually.")
        return
    print("Restarting Moonraker...")
    try:
        # moonraker.sh is an auto-restart wrapper: if only the python process is killed
        # (what `app.sh stop` does), the wrapper respawns it 10 s later and a second
        # Moonraker ends up running next to the one started by `app.sh start`.
        # So stop the wrapper(s) first: SIGTERM makes them stop their python cleanly.
        for pid in _pids_matching("moonraker.sh"):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        deadline = time.time() + 15
        while time.time() < deadline and (_pids_matching("moonraker.sh") or _pids_matching("moonraker.py")):
            time.sleep(0.5)
        for needle in ("moonraker.sh", "moonraker.py"):
            for pid in _pids_matching(needle):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        # app.sh has no shebang on Rinkhals: run it through sh, never directly.
        subprocess.call(["sh", "./app.sh", "start"], cwd=folder)
    except OSError as exc:
        print("Could not restart Moonraker automatically (" + str(exc) + ").")
        print("Do it manually - see the README.")
        return
    print("Moonraker restarted. Wait ~30 s, then re-run your MMU_SET_SPOOL commands.")


parser = argparse.ArgumentParser(description="Spoolman gate mapping patch for Rinkhals mmu_ace.py")
parser.add_argument("--path", help="path to a specific mmu_ace.py")
parser.add_argument("--restart", action="store_true", help="restart Moonraker after patching")
parser.add_argument("--undo", action="store_true", help="restore mmu_ace.py from mmu_ace.py.orig")
args = parser.parse_args()

print(BANNER)

target = find_target(args.path)
folder = os.path.dirname(target)
backup = target + ".orig"
print("Target: " + target)

if args.undo:
    if not os.path.isfile(backup):
        sys.exit("No backup found (" + backup + "). Nothing to restore.")
    shutil.copy2(backup, target)
    print("Restored the original mmu_ace.py.")
    if args.restart:
        restart_moonraker(folder)
    else:
        print("Now restart Moonraker (or re-run with --undo --restart).")
    sys.exit(0)

with open(target, "r", encoding="utf-8") as f:
    content = f.read()

# Already patched? Say so clearly instead of failing on the first check.
if "_activate_spoolman_for_gate" in content:
    if "spool_forget_after" not in content:
        sys.exit("Patched with an earlier build of this patch. "
                 "Run with --undo first, then run the patch again.")
    print("Already patched - nothing to change.")
    if args.restart:
        restart_moonraker(folder)
    sys.exit(0)
if "_manual_spool_overrides" in content:
    sys.exit("Patched with an older version of this patch (fewer patches). "
             "Run with --undo first, then run the patch again.")

# Add 'import inspect' if missing
if "import inspect\n" not in content:
    content = content.replace("import logging\n", "import logging\nimport inspect\n", 1)

# PATCH 1: dictionary remembering manual gate -> Spoolman ID assignments
old1 = '''        self._pending_update = False  # Flag to track if update is needed

        # LRU Cache for filament temperature info (key: "unit_id-gate_index-sku")
        # Limit to 16 entries (2x max gates) to prevent memory leak
        self._filament_temp_cache: OrderedDict = OrderedDict()'''

new1 = '''        self._pending_update = False  # Flag to track if update is needed

        # Manually-assigned Spoolman database IDs (key: gate index, value:
        # spool_id). RFID-tagged gates otherwise have gate.spool_id
        # permanently overwritten by the RFID-serial-derived pseudo-ID on
        # every hardware status poll — this override survives that resync.
        self._manual_spool_overrides: dict[int, int] = {}
        # The assignments are also written to <data_path>/config/mmu_ace_spools.json so they
        # survive a Moonraker restart or a reboot (see MmuAceSpoolStore).
        self._spool_store = MmuAceSpoolStore(self._spool_store_path())

        # LRU Cache for filament temperature info (key: "unit_id-gate_index-sku")
        # Limit to 16 entries (2x max gates) to prevent memory leak
        self._filament_temp_cache: OrderedDict = OrderedDict()'''

assert content.count(old1) == 1, f"Match 1: {content.count(old1)}"
content = content.replace(old1, new1)

# PATCH 2: manual override takes priority during the RFID resync
old2 = '''                    # Use serial number as spool_id if available
                    try:
                        gate.spool_id = int(sku_info["serial"]) if sku_info["serial"] else abs(hash(sku)) % (2**31)
                    except:
                        gate.spool_id = abs(hash(sku)) % (2**31)'''

new2 = '''                    if global_gate_index in self._manual_spool_overrides:
                        gate.spool_id = self._manual_spool_overrides[global_gate_index]
                    else:
                        # Use serial number as spool_id if available
                        try:
                            gate.spool_id = int(sku_info["serial"]) if sku_info["serial"] else abs(hash(sku)) % (2**31)
                        except:
                            gate.spool_id = abs(hash(sku)) % (2**31)'''

assert content.count(old2) == 1, f"Match 2: {content.count(old2)}"
content = content.replace(old2, new2)

# PATCH 3: record the override BEFORE the RFID lock check in update_gate()
old3 = '''        unit, gate = gate_lookup

        logging.debug(f"update gate {gate_index} actual values {json.dumps(gate.__dict__)}")

        if color is None:
            color = [0, 0, 0, 0]

        if gate.rfid == 2:
            logging.warning(f"update gate {gate_index} not allowed, RFID tag is locked")
            return'''

new3 = '''        unit, gate = gate_lookup

        logging.debug(f"update gate {gate_index} actual values {json.dumps(gate.__dict__)}")

        if color is None:
            color = [0, 0, 0, 0]

        if spool_id is not None and spool_id > 0:
            self._manual_spool_overrides[gate_index] = spool_id
            self._spool_store.remember(gate_index, spool_id, gate.sku)
            logging.info(f"Remembered manual spool_id {spool_id} for gate {gate_index}")

        if gate.rfid == 2:
            logging.warning(f"update gate {gate_index} not allowed, RFID tag is locked")
            return'''

assert content.count(old3) == 1, f"Match 3: {content.count(old3)}"
content = content.replace(old3, new3)

# PATCH 4: dedicated set_manual_spool_id method (applies instantly)
old4 = '''class MmuAcePatcher:'''

new4 = '''    def set_manual_spool_id(self, gate_index: int, spool_id: int) -> bool:
        """Manually assign a Spoolman database ID to a gate. Applies instantly
        (unlike the override dict alone, which only takes effect on the next
        RFID resync). Allowed even on RFID-locked gates: the Spoolman ID is
        independent of the RFID payload."""
        gate_lookup = self._get_gate_by_index(gate_index)
        if not gate_lookup:
            logging.warning(f"set_manual_spool_id: gate {gate_index} not found")
            return False

        _, gate = gate_lookup
        self._manual_spool_overrides[gate_index] = spool_id
        self._spool_store.remember(gate_index, spool_id, gate.sku)
        gate.spool_id = spool_id

        self._handle_status_update(force=True)
        logging.info(f"Gate {gate_index}: manual Spoolman ID set to {spool_id}")

        # If this gate is the one currently loaded, make Spoolman follow right away
        if gate_index == self.ace.loaded_gate:
            self.eventloop.create_task(self._activate_spoolman_for_gate(gate_index))
        return True

class MmuAcePatcher:'''

assert content.count(old4) == 1, f"Match 4: {content.count(old4)}"
content = content.replace(old4, new4)

# PATCH 5: MMU_SET_SPOOL command
old5a = '''        self.register_gcode_handler("MMU_GATE_MAP", self._on_gcode_mmu_gate_map)'''
new5a = '''        self.register_gcode_handler("MMU_GATE_MAP", self._on_gcode_mmu_gate_map)
        self.register_gcode_handler("MMU_SET_SPOOL", self._on_gcode_mmu_set_spool)'''
assert content.count(old5a) == 1, f"Match 5a: {content.count(old5a)}"
content = content.replace(old5a, new5a)

old5b = '''    # Triggered on spool edit in ui
    async def _on_gcode_mmu_gate_map(self, args: dict[str, str | None], delegate):'''

new5b = '''    async def _on_gcode_mmu_set_spool(self, args: dict[str, str | None], delegate):
        """Manually assign a Spoolman ID to a gate: MMU_SET_SPOOL GATE=<n> SPOOLID=<id>

        Flat-argument alternative to MMU_GATE_MAP MAP={...}, which cannot
        currently survive kobra.py's shlex.split()-based gcode argument
        parser intact (quotes get stripped or the string gets split on an
        unquoted space). Also works on RFID-tagged gates, where
        update_gate() otherwise rejects all writes.
        """
        try:
            gate_index = self._get_gcode_arg_int("GATE", args)
            spool_id = self._get_gcode_arg_int("SPOOLID", args)
        except ValueError:
            message = "MMU_SET_SPOOL: requires GATE=<n> SPOOLID=<id> (integers, no space after '=')"
            logging.error(message)
            await self._send_gcode_response(message)
            return None

        if spool_id <= 0:
            message = f"MMU_SET_SPOOL: SPOOLID must be a positive integer, got {spool_id}"
            logging.error(message)
            await self._send_gcode_response(message)
            return None

        if self.ace_controller.set_manual_spool_id(gate_index, spool_id):
            message = f"MMU_SET_SPOOL: Gate {gate_index} assigned Spoolman ID {spool_id}"
            logging.info(message)
        else:
            message = f"MMU_SET_SPOOL: Gate {gate_index} not found"
            logging.error(message)

        await self._send_gcode_response(message)
        return None

    # Triggered on spool edit in ui
    async def _on_gcode_mmu_gate_map(self, args: dict[str, str | None], delegate):'''

assert content.count(old5b) == 1, f"Match 5b: {content.count(old5b)}"
content = content.replace(old5b, new5b)

# PATCH 6: auto-activate the Spoolman spool on every MMU_LOAD (with async/sync fix)
old6 = '''            message = f"MMU_LOAD: Loading {length}mm from gate {gate} (index {local_index}) at {speed}mm/s completed, MMU status updated"
            logging.info(message)
            await self._send_gcode_response(message)
        except Exception as e:
            message = f"MMU_LOAD failed: {e}"
            logging.error(message)'''

new6 = '''            # Point Moonraker's [spoolman] active spool at the gate that was just
            # loaded (best-effort, user-assigned IDs only).
            await self.ace_controller._activate_spoolman_for_gate(gate)

            message = f"MMU_LOAD: Loading {length}mm from gate {gate} (index {local_index}) at {speed}mm/s completed, MMU status updated"
            logging.info(message)
            await self._send_gcode_response(message)
        except Exception as e:
            message = f"MMU_LOAD failed: {e}"
            logging.error(message)'''

assert content.count(old6) == 1, f"Match 6: {content.count(old6)}"
content = content.replace(old6, new6)

# PATCH 7: keep the manual Spoolman ID on gates WITHOUT RFID (the "else" branch of the resync)
# Without it, the periodic rebuild of the ACE status resets gate.spool_id = 0
# for every gate without an RFID tag and wipes the assignment made with MMU_SET_SPOOL
# (patch 2 only covers the "if sku:" branch).
old7 = '''                else:
                    gate.spool_id = 0

                unit.gates.append(gate)'''

new7 = '''                else:
                    # No RFID tag: keep the manually assigned Spoolman ID (if any)
                    gate.spool_id = self._manual_spool_overrides.get(global_gate_index, 0)

                unit.gates.append(gate)'''

assert content.count(old7) == 1, f"Match 7: {content.count(old7)}"
content = content.replace(old7, new7)

# PATCH 8: follow the gate reported as loaded by the ACE Hub. Print start and firmware-driven
# tool changes never go through MMU_LOAD, so patch 6 alone does not cover a real print.
old8 = '''        self.ace.filament.pos = FILAMENT_POS_LOADED

    def _set_ace_status(self, filament_hub):'''

new8 = '''        self.ace.filament.pos = FILAMENT_POS_LOADED

        # Print start and firmware-driven tool changes never go through MMU_LOAD:
        # follow the gate the ACE Hub reports as loaded and point Spoolman at it.
        if global_gate != previous_loaded_gate:
            self.eventloop.create_task(self._activate_spoolman_for_gate(global_gate))

    async def _activate_spoolman_for_gate(self, gate_index: int):
        """Make Moonraker's Spoolman active spool follow a loaded gate.
        Only uses IDs assigned with MMU_SET_SPOOL (never the RFID pseudo-IDs)."""
        try:
            spool_id = self._manual_spool_overrides.get(gate_index)
            if not spool_id or spool_id <= 0:
                return
            spoolman = self.server.lookup_component("spoolman", None)
            if spoolman is None:
                return
            result = spoolman.set_active_spool(spool_id)
            if inspect.isawaitable(result):
                await result
            logging.info(f"Gate {gate_index} loaded: active Spoolman spool set to {spool_id}")
        except Exception as e:
            logging.error(f"Error setting active Spoolman spool for gate {gate_index}: {e}")

    def _spool_store_path(self):
        """<data_path>/config/mmu_ace_spools.json, or None (persistence off) if unknown."""
        try:
            data_path = self.server.get_app_args().get("data_path")
            if data_path and os.path.isdir(os.path.join(str(data_path), "config")):
                return os.path.join(str(data_path), "config", "mmu_ace_spools.json")
        except Exception as e:
            logging.warning(f"[mmu_ace] Spool persistence disabled: {e}")
        return None

    def _sync_spool_store(self, gate_index: int, gate_status: int, sku: str):
        """Called for every gate on every status rebuild. Restores an assignment
        remembered before a restart (same RFID SKU in the gate) and forgets it when
        the spool is gone (gate empty for a while, or a different product inserted).
        Never raises: the ACE status rebuild must not depend on it."""
        try:
            store = self._spool_store
            present = gate_status != GATE_EMPTY
            if store.empty_too_long(gate_index, present, time.monotonic()):
                if gate_index in self._manual_spool_overrides or gate_index in store.entries:
                    logging.info(f"Gate {gate_index} empty for a while: forgetting its Spoolman ID")
                self._manual_spool_overrides.pop(gate_index, None)
                store.forget(gate_index)
                return
            if not present:
                return
            saved = store.entries.get(gate_index)
            if gate_index not in self._manual_spool_overrides:
                spool_id = store.restorable(gate_index, sku)
                if spool_id:
                    self._manual_spool_overrides[gate_index] = spool_id
                    logging.info(f"Gate {gate_index}: restored Spoolman ID {spool_id} (same spool as before)")
                    if gate_index == self.ace.loaded_gate:
                        self.eventloop.create_task(self._activate_spoolman_for_gate(gate_index))
            elif saved and saved["sku"] and sku and saved["sku"] != sku:
                logging.info(f"Gate {gate_index}: spool changed ({saved['sku']} -> {sku}), forgetting its Spoolman ID")
                self._manual_spool_overrides.pop(gate_index, None)
                store.forget(gate_index)
        except Exception as e:
            logging.warning(f"[mmu_ace] Spool persistence error on gate {gate_index}: {e}")

    def _set_ace_status(self, filament_hub):'''

assert content.count(old8) == 1, f"Match 8: {content.count(old8)}"
content = content.replace(old8, new8)

# PATCH 9: remember the assignments across restarts (small JSON file, see README)
old9a = '''class MmuAceController:
    ace: MmuAce
'''

new9a = '''class MmuAceSpoolStore:
    """Remembers, across restarts, which Spoolman spool the user assigned to each ACE gate.
    File: {"<gate>": {"spool_id": n, "sku": "<RFID SKU seen in the gate>"}}.
    Never raises: a missing, corrupt or unwritable file only turns persistence off."""

    FORGET_AFTER_EMPTY_S = 300  # a gate empty for this long means the spool was removed

    def __init__(self, path):
        self.path = path
        self.entries = {}       # gate index -> {"spool_id": int, "sku": str}
        self._empty_since = {}  # gate index -> time.monotonic() of the first empty poll
        logging.info(f"[mmu_ace] Spoolman assignments file: {path or 'none (persistence off)'}")
        self._load()

    def _load(self):
        if not self.path or not os.path.isfile(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, value in data.items():
                spool_id = int(value["spool_id"])
                if spool_id > 0:
                    self.entries[int(key)] = {"spool_id": spool_id, "sku": str(value.get("sku", ""))}
            logging.info(f"[mmu_ace] Loaded {len(self.entries)} remembered Spoolman assignment(s) from {self.path}")
        except Exception as e:
            self.entries = {}
            logging.warning(f"[mmu_ace] Could not read {self.path}: {e}")

    def _save(self):
        if not self.path:
            return
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({str(k): v for k, v in sorted(self.entries.items())}, f, indent=2)
            os.replace(tmp, self.path)
        except Exception as e:
            logging.warning(f"[mmu_ace] Could not save {self.path}: {e}")

    def remember(self, gate_index, spool_id, sku):
        entry = {"spool_id": int(spool_id), "sku": sku or ""}
        if self.entries.get(gate_index) != entry:
            self.entries[gate_index] = entry
            self._save()

    def forget(self, gate_index):
        self._empty_since.pop(gate_index, None)
        if self.entries.pop(gate_index, None) is not None:
            self._save()

    def restorable(self, gate_index, sku):
        """Remembered ID for this gate if it still holds the same product (same RFID SKU)."""
        entry = self.entries.get(gate_index)
        if entry and entry["sku"] == (sku or ""):
            return entry["spool_id"]
        return None

    def empty_too_long(self, gate_index, present, now):
        """True once the gate has been reported empty for FORGET_AFTER_EMPTY_S seconds."""
        if present:
            self._empty_since.pop(gate_index, None)
            return False
        return now - self._empty_since.setdefault(gate_index, now) >= self.FORGET_AFTER_EMPTY_S

class MmuAceController:
    ace: MmuAce
'''

assert content.count(old9a) == 1, f"Match 9a: {content.count(old9a)}"
content = content.replace(old9a, new9a)

old9b = '''                # Parse SKU for additional information
                gate.sku = sku
'''

new9b = '''                # Restore / forget the remembered Spoolman ID of this gate
                self._sync_spool_store(global_gate_index, gate.status, sku)

                # Parse SKU for additional information
                gate.sku = sku
'''

assert content.count(old9b) == 1, f"Match 9b: {content.count(old9b)}"
content = content.replace(old9b, new9b)

# PATCH 10: make the "forget after empty" timeout configurable via moonraker.custom.conf
old10a = '''    def __init__(self, server: Server, host: str | None):
        self.server = server
'''

new10a = '''    def __init__(self, server: Server, host: str | None, spool_forget_after: float = 300.0):
        self.server = server
        self._spool_forget_after = spool_forget_after
'''

assert content.count(old10a) == 1, f"Match 10a: {content.count(old10a)}"
content = content.replace(old10a, new10a)

old10b = '''        self._spool_store = MmuAceSpoolStore(self._spool_store_path())
'''

new10b = '''        self._spool_store = MmuAceSpoolStore(self._spool_store_path(), forget_after=self._spool_forget_after)
'''

assert content.count(old10b) == 1, f"Match 10b: {content.count(old10b)}"
content = content.replace(old10b, new10b)

old10c = '''    FORGET_AFTER_EMPTY_S = 300  # a gate empty for this long means the spool was removed

    def __init__(self, path):
        self.path = path
'''

new10c = '''    def __init__(self, path, forget_after: float = 300.0):
        self.path = path
        # 0 (or negative) means "never forget": useful with custom RFID tags that
        # already carry a unique-per-spool SKU (see spool_forget_after in the README).
        self.forget_after = forget_after if forget_after and forget_after > 0 else None
'''

assert content.count(old10c) == 1, f"Match 10c: {content.count(old10c)}"
content = content.replace(old10c, new10c)

old10d = '''        if present:
            self._empty_since.pop(gate_index, None)
            return False
        return now - self._empty_since.setdefault(gate_index, now) >= self.FORGET_AFTER_EMPTY_S
'''

new10d = '''        if present:
            self._empty_since.pop(gate_index, None)
            return False
        if self.forget_after is None:
            return False
        return now - self._empty_since.setdefault(gate_index, now) >= self.forget_after
'''

assert content.count(old10d) == 1, f"Match 10d: {content.count(old10d)}"
content = content.replace(old10d, new10d)

old10e = '''    def __init__(self, config: ConfigHelper):
        self.server = config.get_server()
        self.name = config.get_name()
        self.kobra = self.server.load_component(self.server.config, \'kobra\')

        host = config.get("host", None)
        self.ace_controller = MmuAceController(self.server, host)
'''

new10e = '''    @staticmethod
    def _read_spool_forget_after(config: ConfigHelper) -> float:
        """0 (or a negative number) disables the timeout: a remembered assignment is
        never dropped just because the gate is empty. Useful when every spool carries
        a unique SKU (custom RFID tags), where the ambiguity this timeout guards
        against (two spools of the same product) does not exist. Default: 300s (5 min).
        """
        return config.getfloat("spool_forget_after", 300.0)

    def __init__(self, config: ConfigHelper):
        self.server = config.get_server()
        self.name = config.get_name()
        self.kobra = self.server.load_component(self.server.config, \'kobra\')

        host = config.get("host", None)
        spool_forget_after = self._read_spool_forget_after(config)
        self.ace_controller = MmuAceController(self.server, host, spool_forget_after)
'''

assert content.count(old10e) == 1, f"Match 10e: {content.count(old10e)}"
content = content.replace(old10e, new10e)

# Backup the untouched file (only now that every check has passed)
if not os.path.exists(backup):
    shutil.copy2(target, backup)
    print("Backup created: " + backup)

with open(target, "w", encoding="utf-8") as f:
    f.write(content)

print("All 10 patches applied successfully.")
if args.restart:
    restart_moonraker(folder)
else:
    print("Now restart Moonraker: re-run this script with --restart (recommended),")
    print("or see the README for the manual method.")
