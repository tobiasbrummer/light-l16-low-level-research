# Light L16 all-16 dark frame series

This app records 24 dark frames from all 16 modules with the lens covered, in
one root session, and writes them to `/sdcard/DCIM/camera` as ordinary
HAL-generated LRIs.

It is a deliberately narrow experiment, not a general camera controller or root
shell. The compiled-in plan is the only thing it can do; no parameter is
reachable from the user interface.

## The plan

All captures use mask `FE FF 01` (all 16 modules), the factory tuple
`11 F1 00`, one 4160 x 3120 RAW10 surface per module, and a single `-e` value
applied to every selected module.

Exposure axis, at gain 1.0, three repeats each:

| Integration time | Repeats |
| --- | ---: |
| 10 us | 3 |
| 1.25 ms | 3 |
| 5 ms | 3 |
| 20 ms | 3 |

Gain axis, at 1.25 ms, three repeats each:

| Requested gain | Repeats |
| --- | ---: |
| 2.0 | 3 |
| 3.75 | 3 |
| 4.0 | 3 |
| 7.5 | 3 |

Twenty-four captures at roughly 260 MB each: about 6.3 GB and 25 minutes. The
exposure axis runs first because it uses the already exercised gain 1.0, so a
refusal on the untested gain axis cannot cost the exposure measurement.

The reasoning behind the plan is in
[../../docs/dark-frame-series.md](../../docs/dark-frame-series.md).

## Safety and recovery policy

The series does not reboot between captures; 24 reboots would make it
impossible. Instead the child repeats the settle checks the single-capture
wrapper performs once after its capture: `manual_control` forced to zero, no
surviving `lcc` process, no CameraService client, and both `media` and
`lightsvr` running. The first failed gate stops the series.

Every capture must produce exactly one attributable new LRI. Zero means the HAL
wrote nothing and more than one means the attribution is ambiguous; both stop
the series rather than guessing which file belongs to which exposure.

A stopped series that wrote frames is reported as `PARTIAL`, not as a failure:
the listed frames passed every per-capture check. A dirty cleanup still
downgrades the run to `FAIL`, because a camera that did not come back cleanly
makes the whole run untrustworthy.

Exactly one normal reboot follows the series, however it ended. A complete
child preflight failure proving `capture_attempted=no` is the only result that
stays up. No partition is flashed and no persistent root is installed.

## Build

The reviewed async writer shim is produced by **LLD 20.1.8**. A different LLD
produces a different byte count, which the build then refuses. Point the build
at the reviewed linker:

```sh
L16_LLD=/usr/lib/llvm-20/bin/ld.lld android/dark-frame-series/build_debug_apk.sh
```

The script searches `/usr/lib/llvm-20/bin/ld.lld` and `/usr/bin/ld.lld-20`
before any other candidate, so the variable is usually unnecessary on a machine
with `lld-20` installed. The signed APK is written to:

```text
.build/dark-frame-series/light-l16-dark-frame-series-debug.apk
```

## One-time installation

```sh
adb install .build/dark-frame-series/light-l16-dark-frame-series-debug.apk
```

After installation the camera does not need to stay connected to a computer.

## Device test

1. Start from a completed normal boot with a well-charged battery. The series
   runs for about 25 minutes with the camera active.
2. Confirm at least 8 GiB free; the preflight refuses less.
3. Fully close the stock camera app.
4. **Cover the lens completely.** All 16 modules sit behind the front glass, so
   the cover has to span the whole front, not one opening.
5. Open **L16 Dark Frame Series**.
6. Tap **1. VORPRÜFUNG & SCHARFSCHALTEN**. Continue only after
   `preflight=PASS` and `camera_not_touched=yes`.
7. Tap **2. DUNKELHEIT PRÜFEN**. Camera2 opens briefly at maximum sensitivity
   and reports its measured mean and p99.9 luma next to the limits. Continue
   only after `darkness=CONFIRMED`.
8. Within 60 seconds, tap **3. DUNKELBILDSERIE STARTEN (24 AUFNAHMEN)** once.
9. Expect one normal reboot after the series. Do not press the power button
   while the operation is running unless the camera stays unresponsive well
   beyond the documented 41-minute app window.
10. After Android boots, reopen the app. A complete run reports:

```text
supervisor=L16_HOSTLESS_DARK_FRAME_SERIES_V1
captures_requested=24
captures_completed=24
supervisor_complete=PASS
supervisor_decision=normal_reboot_after_dark_frame_series
app_interpretation=PASS_MANIFEST_REBOOT_REQUESTED
```

A stopped run reports `supervisor_complete=PARTIAL`,
`app_interpretation=PARTIAL_MANIFEST_REBOOT_REQUESTED`, and the completed
count with the abort index and reason. Its frames are still usable.

Between `manifest_begin` and `manifest_end` the report lists one line per
capture: index, integration time in ns, requested gain, LRI size, and LRI
SHA-1. The report is also mirrored, without an extra storage permission, to:

```text
/sdcard/Android/data/io.github.tobiasbrummer.lightl16.darkframe/files/light-l16-dark-frame-series-last-display.txt
```

Copy it before preparing another test; it is deleted when the APK is
uninstalled.

## Analysis

Pull the listed LRIs and reduce them with
`tools/analyze_dark_frame_series.py`, which reports per-module black level,
fixed pattern noise, read noise, dark current, and the requested-versus-recorded
gain mapping. That tool needs NumPy; the rest of the repository does not.

## Validation status

The device payloads, the app, the packaging, and the hash chain are host-tested,
and the APK builds and verifies. **The series has not run on a camera.**

Three parts have no physical precedent. The 10 us and 1.25 ms integration times
have never been requested; the shortest physically confirmed value is 6.36 ms.
Gains above 1.0 have never been requested through `lcc`, although the stock app
reaches 3.75 and 7.5 through its own path. And 24 consecutive all-16 captures in
one session have never been attempted; the longest prior sequence is one.

The first result must be decoded before any claim about dark current, read
noise, or gain quantization enters the documentation.

## Payload identity

| Payload | Size | SHA-1 |
| --- | ---: | --- |
| `device/dark_frame_series_once.sh` | 22,189 | `cd3788ce22956b34ec69bb1466e81661b01241dd` |
| `device/dark_frame_series_hostless_supervisor.sh` | 13,596 | `c45220fef42c2ad48b43f8f7bbb75d8f1d0cecdf` |
| `liblcc_async_writer_shim.so` | 8,904 | `150e53a736624010dc7fb741490ea8dca7afbfb8` |
