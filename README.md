# Rinkhals ACE Pro - Spoolman gate mapping patch

Unofficial community patch for the `mmu_ace.py` component of [Rinkhals](https://github.com/rinkhals-community/Rinkhals)
(Anycubic Kobra S1 + ACE Pro). It ties each ACE gate to a [Spoolman](https://github.com/Donkie/Spoolman) spool and
keeps Spoolman's active spool in sync with the gate being loaded, so filament usage is tracked on the right spool.

> **Use at your own risk. Not affiliated with Rinkhals or Anycubic.**
> Tested on Rinkhals `20260716_02` with **official Anycubic spools** only. See [Tested](#tested).

## Quick start

**1. Declare Spoolman once** in `moonraker.custom.conf` (skip if already done):

```ini
[spoolman]
server: http://<spoolman-ip>:7912
sync_rate: 5
```

**2. Copy the patch to the printer and run it** (`scp` and `ssh` are built into Windows 10/11 PowerShell):

```sh
scp patch_mmu_ace.py root@<printer-ip>:/tmp/
ssh root@<printer-ip>
python3 /tmp/patch_mmu_ace.py --restart
```

It finds the active Rinkhals version by itself, makes a backup (`mmu_ace.py.orig`), applies the patch and restarts
Moonraker. You should read `All 8 patches applied successfully`.

**3. Assign your spools** in the Mainsail console, with **no space after `=`**:

```
MMU_SET_SPOOL GATE=0 SPOOLID=<spool-id>
MMU_SET_SPOOL GATE=1 SPOOLID=<spool-id>
MMU_SET_SPOOL GATE=2 SPOOLID=<spool-id>
MMU_SET_SPOOL GATE=3 SPOOLID=<spool-id>
```

Replace `<spool-id>` with the spool's ID in Spoolman (a number, no spaces).
Each command answers `Gate N assigned Spoolman ID X`. After a `MMU_LOAD`, the active spool is shown at
`http://<printer-ip>/server/spoolman/status` (`spool_id`).

> `MMU_LOAD` really feeds filament. Unload first (`MMU_UNLOAD` or the printer screen) before loading another gate.

## Undo

```sh
python3 /tmp/patch_mmu_ace.py --undo --restart
```

## Options

| Option | Effect |
|--------|--------|
| `--restart` | Restart Moonraker cleanly after patching (or after `--undo`); also works if already patched |
| `--undo` | Restore the original `mmu_ace.py` from `mmu_ace.py.orig` |
| `--path FILE` | Patch a specific `mmu_ace.py` instead of the active Rinkhals one |

## The problem it solves

With the stock `mmu_ace.py`, an ACE gate cannot be tied to a Spoolman spool:

- On RFID gates, `spool_id` is derived from the tag serial and overwritten on every status poll.
- `update_gate()` rejects all writes on RFID-locked gates.
- On gates without RFID, `spool_id` is reset to `0` on every ACE status rebuild (`else: gate.spool_id = 0`).
- `MMU_GATE_MAP MAP={...}` cannot survive the `shlex.split()` parsing in `kobra.py`.
- Moonraker's Spoolman active spool never follows the gate being loaded.
- Print start and firmware-driven tool changes never call `MMU_LOAD`, so nothing tells Spoolman which spool is in use.

## What it changes (8 small patches)

| # |                                           Change                                        |
|---|-----------------------------------------------------------------------------------------|
| 1 | Dictionary remembering manual gate -> Spoolman ID assignments                           |
| 2 | That override takes priority during the RFID resync                                     |
| 3 | The override is recorded before the RFID lock check in `update_gate()`                  |
| 4 | `set_manual_spool_id()` applies an assignment instantly                                 |
| 5 | New command `MMU_SET_SPOOL GATE=<n> SPOOLID=<id>` (flat arguments, works on RFID gates) |
| 6 | Every `MMU_LOAD` activates the assigned spool in Moonraker's Spoolman component         |
| 7 | The manual ID is kept on gates **without** RFID (the `else` branch above)               |
| 8 | Follows the gate the ACE Hub reports as loaded (print start, in-print color changes) and activates its Spoolman spool |

Only `mmu_ace.py` is modified. `gklib` and the printer firmware config are not touched.

## Safety

- All checks run first; the file is written only if every one passes (all or nothing).
- On another Rinkhals version it prints `Patch NOT applied` and changes nothing.
- Already patched: it says so and changes nothing.
- A Rinkhals reinstall or update replaces `mmu_ace.py`: run the script again (and re-add `[spoolman]` if needed).

## Tested

Rinkhals `20260716_02`, firmware `2.7.2.7`, Kobra S1 + ACE Pro (single ACE).

**Filament used for the tests:** official Anycubic spools with RFID tags (gates 0-2), plus one Anycubic spool for which
the ACE reports no RFID data (gate 3, shown as "UNKNOWN"). Third-party spools were **not** tested.

- [x] Manual `MMU_LOAD` switches the Spoolman active spool (official Anycubic spools with RFID)
- [x] Same on a gate **without** RFID data (patch 7)
- [x] Patched file compiles; on the stock `20260716_02` file the result has md5 `c0524685cd2319c79455e5d4da2702d4`
- [x] Full printer reboot (RFID detection still fine)
- [x] Applies and compiles on `20260901_01`, `master` and `develop` (source check only, not run on a printer)
- [x] Real 2-color print: the active spool follows the print start (gate 1 -> spool 24) and the color change (gate 2 -> spool 16)
- [ ] Longer prints with several swaps back and forth (e.g. A -> B -> A)
- [ ] Third-party (non-Anycubic) spools
- [ ] Multiple ACE units

## Known limitations

- Assignments live in memory: re-run `MMU_SET_SPOOL` after each Moonraker restart.
- Name, material and temperature are not pulled from Spoolman.
- Only IDs assigned with `MMU_SET_SPOOL` are sent to Spoolman (never the RFID-derived pseudo-IDs).
- The Happy Hare `spoolman_support` flag stays `off`, so Mainsail's "Choose Spool" button is disabled. Use `MMU_SET_SPOOL`.
- Related upstream work: the maintainers track this as one workstream ([#89](https://github.com/rinkhals-community/Rinkhals/issues/89), [#107](https://github.com/rinkhals-community/Rinkhals/issues/107), [#141](https://github.com/rinkhals-community/Rinkhals/issues/141), PR [#142](https://github.com/rinkhals-community/Rinkhals/pull/142)). Their design goals include persisting assignments across restarts, which this patch does not do.

## Troubleshooting

|                     Message                     |                         Meaning                             |
|-------------------------------------------------|-------------------------------------------------------------|
| `Already patched - nothing to change.`          | The patch is already in place.                              |
| `Patch NOT applied ... Match N: 0`              | A different Rinkhals version; the file is unchanged.        |
| `Patched with an older version ...`             | Older version of this patch: run with `--undo`, then again. |
| `mmu_ace.py not found`                          | Run it on the printer (SSH), or use `--path`.               |
| Two `moonraker.py` processes running            | Happens after `app.sh stop` then `app.sh start` (the auto-restart wrapper respawns Moonraker). Use `--restart`, or stop the `moonraker.sh` wrappers first. |
| `MMU_SET_SPOOL: requires GATE=<n> SPOOLID=<id>` | Remove any space after `=`.                                 |

## Changelog

- **v1.0.1** - Fix: the `MMU_LOAD` hook could send an RFID-derived pseudo-ID to Spoolman on a gate without a manual assignment. It now only uses IDs assigned with `MMU_SET_SPOOL`. If you applied v1.0.0, run `--undo` then apply again.
- **v1.0.0** - First public release.

## Contributing

Issues and pull requests are welcome, especially results on other Rinkhals versions or setups.
Please include the exact Rinkhals version and the output of the script.

## License

GPL-3.0, see [LICENSE](LICENSE). `mmu_ace.py` carries a GPLv3 notice (Eric Callahan, 2021) and this patch embeds
excerpts of it, so the patch follows the same license. The Rinkhals repository itself is MIT. This is a practical
choice, not legal advice.

Copyright (C) 2026 Edwin Lepere

Patched by Edwin Lepere <Mazerakam>
