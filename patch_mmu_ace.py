#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Edwin Lepere - License: GPL-3.0 (see the LICENSE file of the repository)
#
# +==================================================================+
# |                                                                  |
# |           *   Patched by Edwin Lepere <Mazerakam>   *            |
# |                                                                  |
# |        --------------------------------------------------        |
# |     Rinkhals mmu_ace.py  -  Spoolman + ACE Pro  -  8 patches     |
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
|     Rinkhals mmu_ace.py  -  Spoolman + ACE Pro  -  8 patches     |
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
    if "status.gate_spool_id[gate]" in content:
        sys.exit("Patched with v1.0.0 (known issue: the MMU_LOAD hook could send an RFID-derived "
                 "pseudo-ID to Spoolman). Run with --undo first, then run the patch again.")
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

new2 = '''                    if index in self._manual_spool_overrides:
                        gate.spool_id = self._manual_spool_overrides[index]
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

old5b = '''    async def _on_gcode_mmu_gate_map(self, args: dict[str, str | None], delegate):'''

new5b = '''    async def _on_gcode_mmu_set_spool(self, args: dict[str, str | None], delegate):
        """Manually assign a Spoolman ID to a gate: MMU_SET_SPOOL GATE=<n> SPOOLID=<id>

        Flat-argument alternative to MMU_GATE_MAP MAP={...}, which cannot
        currently survive kobra.py's shlex.split()-based gcode argument
        parser intact (quotes get stripped or the string gets split on an
        unquoted space). Also works on RFID-tagged gates, where
        update_gate() otherwise rejects all writes.
        """
        gate_index = self._get_gcode_arg_int("GATE", args)
        spool_id = self._get_gcode_arg_int("SPOOLID", args)

        if gate_index is None or spool_id is None:
            message = "MMU_SET_SPOOL: requires GATE=<n> SPOOLID=<id>"
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

new6 = '''            # Switch Moonraker's [spoolman] component's active spool to match
            # the gate that was just loaded, so per-gate Spoolman usage
            # tracking follows every in-print color change. Best-effort.
            try:
                spoolman = self.ace_controller.server.lookup_component("spoolman", None)
                if spoolman is not None:
                    # Only IDs assigned by the user (MMU_SET_SPOOL): gate.spool_id can be an
                    # RFID-derived pseudo-ID that does not exist in Spoolman.
                    spool_id = self.ace_controller._manual_spool_overrides.get(gate)
                    if spool_id and spool_id > 0:
                        result = spoolman.set_active_spool(spool_id)
                        if inspect.isawaitable(result):
                            await result
                        logging.info(f"MMU_LOAD: Set active spool to {spool_id} for gate {gate}")
            except Exception as e:
                logging.error(f"MMU_LOAD: Error setting active spool: {e}")

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
                    gate.spool_id = self._manual_spool_overrides.get(index, 0)

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

    def _set_ace_status(self, filament_hub):'''

assert content.count(old8) == 1, f"Match 8: {content.count(old8)}"
content = content.replace(old8, new8)

# Backup the untouched file (only now that every check has passed)
if not os.path.exists(backup):
    shutil.copy2(target, backup)
    print("Backup created: " + backup)

with open(target, "w", encoding="utf-8") as f:
    f.write(content)

print("All 8 patches applied successfully.")
if args.restart:
    restart_moonraker(folder)
else:
    print("Now restart Moonraker: re-run this script with --restart (recommended),")
    print("or see the README for the manual method.")
