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
Moonraker. You should read `All 11 patches applied successfully`.

**3. Assign your spools** in the Mainsail console, with **no space after `=`**:

```
MMU_SET_SPOOL GATE=0 SPOOLID=<spool-id>
MMU_SET_SPOOL GATE=1 SPOOLID=<spool-id>
MMU_SET_SPOOL GATE=2 SPOOLID=<spool-id>
MMU_SET_SPOOL GATE=3 SPOOLID=<spool-id>
```

Replace `<spool-id>` with the spool's ID in Spoolman (a number, no spaces).
Each command answers `Gate N assigned Spoolman ID X`. You do this **once**: the assignments are remembered
(see [Persistence](#persistence)). After a `MMU_LOAD`, the active spool is shown at
`http://<printer-ip>/server/spoolman/status` (`spool_id`).

> `MMU_LOAD` really feeds filament. If another gate is already loaded, it is unloaded first (the nozzle is heated for that).

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

## What it changes (11 small patches)

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
| 9 | Remembers the assignments in a small file, restores them after a restart, forgets them when the spool is removed or replaced |
| 10 | The "forgets after empty" delay (patch 9) is configurable instead of a hardcoded 5 minutes |
| 11 | Optional SKU -> Spoolman ID library, shared across gates, off by default (`spool_library`) |

Only `mmu_ace.py` is modified (plus one small data file, see below). `gklib` and the printer firmware config are not touched.

## Persistence

The assignments are saved in `mmu_ace_spools.json`, in Moonraker's `config` folder (the exact path is written to the
Moonraker log: `grep "assignments file" moonraker.log`; on the tested Kobra S1 it is
`/userdata/app/gk/printer_data/config/mmu_ace_spools.json`). After a Moonraker restart or a reboot:

- an assignment is **restored** once its gate holds the same product again (same RFID SKU; gates without RFID data match
  each other), so you do not have to type `MMU_SET_SPOOL` again;
- it is **forgotten** when a different RFID product is inserted, or when the gate has been empty for a configurable
  delay (`spool_forget_after`, 300 seconds / 5 minutes by default);
- typing `MMU_SET_SPOOL` again replaces it. To forget everything, delete the file and restart Moonraker.

**Limit:** two spools of the same product are indistinguishable for the ACE. If you swap one for another while the
printer is off (or within the delay above), the old ID stays: run `MMU_SET_SPOOL` for that gate after such a swap.

**Configuring the delay.** Add to `moonraker.custom.conf`:

```ini
[mmu_ace]
spool_forget_after: 0
```

`0` (or any negative number) disables the delay entirely: an assignment is never dropped just because its gate is
empty. This is meant for **custom RFID tags with a unique SKU per physical spool** (for example written with an
NFC215 tag and an app like "Ace RFID", or a reader/writer tool such as
[Anycubic-NFC-Tagger-QT5](https://github.com/mrRobot62/Anycubic-NFC-Tagger-QT5)): with a unique SKU, the ACE can already
tell spools apart, so the delay's only job — telling "this is still the same physical spool" from "a different spool of
the same product was swapped in" — is redundant. It still stays off if a gate is emptied and left empty; nothing keeps
assigning a spool that no longer exists, it just never gets *dropped* on its own. On **stock Anycubic tags** (SKU is a
per-product code, shared by every spool of that product), leaving the default in place is safer: it is a heuristic, not
something measured against real swap timing, but it limits how long a stale assignment can be silently reused by a
different, same-product spool.

## SKU library (optional, off by default)

By default, a remembered assignment is tied to one specific gate (see Persistence above): moving a spool to a
different gate needs a fresh `MMU_SET_SPOOL`. The library removes that limit, at the cost of a real safety trade-off —
read the warning below before enabling it.

Enable it in `moonraker.custom.conf`:

```ini
[mmu_ace]
spool_library: True
```

With it on, every `MMU_SET_SPOOL` also records `SKU -> Spoolman ID` in a small library, saved in the same
`mmu_ace_spools.json` file (under a `_library` key). Any gate that has no history of its own but whose SKU is in the
library is auto-linked to that ID — including a spool moved to a gate it was never assigned to before, and including
across restarts. The most recent `MMU_SET_SPOOL` for a given SKU always wins and replaces the library entry.

**⚠️ Only safe with a unique SKU per physical spool** (custom RFID tags — see the "Ace RFID" app / NTAG215 or
[Anycubic-NFC-Tagger-QT5](https://github.com/mrRobot62/Anycubic-NFC-Tagger-QT5) mentioned in the issues below). On
**stock Anycubic tags**, the SKU is a per-*product* code shared by every spool of that product, not a per-spool ID.
If you own two spools of the same product, the library cannot tell them apart: after a spool that was in the library
is removed and a *different* spool of the same product is later inserted anywhere, it can be silently auto-linked to
the first spool's ID. This is not detected or blocked in code — there is nothing in the data the ACE reports that
would let it tell two same-product spools apart. Leave this off unless every SKU you use is genuinely unique per spool.

One conflict *is* caught: if the same SKU is reported present on two gates **at the same time**, the second one is
left unlinked (a warning is logged) rather than guessing which one is the "right" gate for that ID.

Every auto-link is logged (`Gate N: auto-linked to spool <id> via the SKU library (SKU <sku>)`), so it is visible
rather than silent — check the Moonraker log if a gate ends up with an unexpected spool.

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
- [x] Patched file compiles; on the stock `20260716_02` file the result has md5 `17457aca52068a24d4db89d80d519ef9`
- [x] Full printer reboot (RFID detection still fine)
- [x] Applies and compiles on `20260901_01`, `master` and `develop` (source check only, not run on a printer)
- [x] Real 2-color print: the active spool follows the print start (gate 1 -> spool 24) and the color change (gate 2 -> spool 16) (tested on an earlier build)
- [ ] The same print re-run on the current build (the activation code was reorganised since)
- [x] Assignments restored after a Moonraker restart and after a cold boot, without typing `MMU_SET_SPOOL` again (checked in the Moonraker log)
- [x] Unit tests (64, in the upstream test style, `python -m pytest tests/`) cover the override map, several-ACE gate indexing, activation rules, `MMU_SET_SPOOL` errors, persistence and the configurable delay
- [ ] `spool_forget_after` checked on a real printer (unit-tested only so far)
- [ ] `spool_library` checked on a real printer (unit-tested only so far)
- [x] A gate without a loaded filament stays `ready` in the ACE Hub status, so the "empty for 5 minutes" rule does not fire on an unloaded gate
- [ ] Longer prints with several swaps back and forth (e.g. A -> B -> A)
- [ ] Third-party (non-Anycubic) spools
- [ ] Multiple ACE units

## Known limitations

- Assignments are restored after a restart only for the same product in the same gate (see Persistence).
- Name, material and temperature are not pulled from Spoolman.
- Only IDs assigned with `MMU_SET_SPOOL` are sent to Spoolman (never the RFID-derived pseudo-IDs).
- The Happy Hare `spoolman_support` flag stays `off`, so Mainsail's "Choose Spool" button is disabled. Use `MMU_SET_SPOOL`.
- Related upstream work: the maintainers track this as one workstream ([#89](https://github.com/rinkhals-community/Rinkhals/issues/89), [#107](https://github.com/rinkhals-community/Rinkhals/issues/107), [#141](https://github.com/rinkhals-community/Rinkhals/issues/141)). Their design goals include persisting assignments across restarts, which this patch does not do.

## Troubleshooting

|                     Message                     |                         Meaning                             |
|-------------------------------------------------|-------------------------------------------------------------|
| `Already patched - nothing to change.`          | The patch is already in place.                              |
| `Patch NOT applied ... Match N: 0`              | A different Rinkhals version; the file is unchanged.        |
| `Patched with an older version ...`             | Older version of this patch: run with `--undo`, then again. |
| `mmu_ace.py not found`                          | Run it on the printer (SSH), or use `--path`.               |
| Two `moonraker.py` processes running            | Happens after `app.sh stop` then `app.sh start` (the auto-restart wrapper respawns Moonraker). Use `--restart`, or stop the `moonraker.sh` wrappers first. |
| `MMU_SET_SPOOL: requires GATE=<n> SPOOLID=<id> ...` | A value is missing or not a number. Remove any space after `=`.                                 |

## Changelog

- **v1.0.0** - First public release. Ties each ACE gate to a Spoolman spool, follows the gate the ACE Hub reports as loaded (print start, color changes, `MMU_LOAD`), and remembers the assignments across Moonraker restarts and reboots. The "forgets after empty" delay is configurable (`spool_forget_after`), and an optional, off-by-default SKU library (`spool_library`) can auto-link a spool moved to a different gate — see its warning above before enabling it.
  Earlier builds published on 2026-09-21 did not remember assignments, and one of them had a bug in the `MMU_LOAD` hook (it could send an RFID-derived pseudo-ID to Spoolman on a gate without a manual assignment). If the script says you have an earlier build, run `--undo` and apply it again.

## Contributing

Issues and pull requests are welcome, especially results on other Rinkhals versions or setups.
Please include the exact Rinkhals version and the output of the script.

## License

GPL-3.0, see [LICENSE](LICENSE). `mmu_ace.py` carries a GPLv3 notice (Eric Callahan, 2021) and this patch embeds
excerpts of it, so the patch follows the same license. The Rinkhals repository itself is MIT. This is a practical
choice, not legal advice.

Copyright (C) 2026 Edwin Lepere

Patched by Edwin Lepere <Mazerakam>
