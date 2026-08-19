# Light L16 hostless same-session A1-A5 focus capture

This app is the next bounded step after the physically verified A1 inline-AF
capture. It uses the fixed explicit mask `3E 00 00` to request A1 through A5
in one LCC capture while keeping the Camera3 autofocus gate inside the same
open HAL session.

It is not a general root bridge or camera controller. The profile accepts no
parameters and is fixed to:

- modules `A1,A2,A3,A4,A5` (`3E 00 00`);
- center-half AF ROI `[1040,780,3120,2340,1000]`;
- one `4160 x 3120` RAW10 surface per selected module;
- `20,000,000 ns` and gain `1.0` for every selected module;
- at least 512 MiB free in the LRI data filesystem;
- exactly one attempt per installation and a normal reboot afterward.

The five A modules have no movable mirrors, so this test expands the proven
same-session lens-focus path without yet adding mirror actuation. A1 and A5
are attached to ASIC 1; A2 through A4 are attached to ASIC 2. Thus a valid
result also tests one focused multi-ASIC request.

The focus preload injects `CONTROL_AF_MODE=AUTO`, the fixed ROI and exactly one
`CONTROL_AF_TRIGGER=START` into LCC's preview requests. It releases the real
capture only after an exact `CONTROL_AF_STATE=FOCUSED_LOCKED`. That single HAL
state is a capture gate, not proof that every selected module acquired a good
individual physical focus. The resulting LRI must be decoded afterward.

## Build

```sh
android/a-group-capture/build_debug_apk.sh
```

Output:

```text
.build/a-group-capture/light-l16-a-group-inline-focus-capture-debug.apk
```

The package name is
`io.github.tobiasbrummer.lightl16.agroupcapture`, so the physically verified
A1-only app can remain installed alongside it.

## Install and run

```sh
adb install .build/a-group-capture/light-l16-a-group-inline-focus-capture-debug.apk
```

Then:

1. Complete a normal boot and fully close the stock camera app.
2. Open **L16 A-Gruppe Inline AF**.
3. Tap **1. VORPRÜFUNG & SCHARFSCHALTEN** and require `preflight=PASS` plus
   `camera_not_touched=yes`.
4. Point the camera at a bright, detailed, stationary subject near the image
   center. Within 60 seconds tap
   **2. A1-A5 CENTER-AF + 20 MS AUSLÖSEN** once.
5. Expect one normal reboot. Do not retry an ambiguous result.
6. Copy the new LRI and the text report from:

```text
/sdcard/DCIM/camera/RDI_*.lri
/sdcard/Android/data/io.github.tobiasbrummer.lightl16.agroupcapture/files/light-l16-a-group-inline-af-last-display.txt
```

The app mirrors every displayed report update to that UTF-8 text file without
requesting storage or camera permissions.

## Required post-capture evidence

A wrapper `PASS` proves the fixed process, focus gate, LRI creation and cleanup,
but does not yet prove five useful focused images. Decode the LRI and require:

- exactly `A1,A2,A3,A4,A5`, each enabled and RAW10 at `4160 x 3120`;
- the requested exposure and gains for all five modules;
- top-level `focus_achieved=true`;
- center ROI metadata and `lens_timeout=false` for each recorded AF entry;
- plausible nonzero `lens_position` values, interpreted against each module's
  calibration rather than compared as if their Hall codes shared one scale;
- nonconstant pixel data and scene-appropriate clipping statistics.

## First physical result

The first camera run on 2026-08-16 produced
`RDI_20260816_133303_294.lri`, 81,484,025 bytes, with SHA-1
`22eb827efcd157550ca015e2ad42025530614a50`. The file parses to its exact end
without unknown protobuf fields and contains exactly five enabled packed-RAW10
surfaces: A1 through A5 at 4160 x 3120. Both ASIC capture blocks carry the same
128-bit image ID and timestamp, making this one logical multi-ASIC capture.

Both headers record `focus_achieved=true`. Every module records AUTO mode, a
centered ROI, `lens_timeout=false`, and a distinct nonzero lens Hall code:

| Module | Lens Hall code | Disparity distance | Contrast distance |
| --- | ---: | ---: | ---: |
| A1 | 12016 | 9884 mm | 65535 mm |
| A2 | 11376 | 9884 mm | 65535 mm |
| A3 | 8928 | 9882 mm | 1451.8456 mm |
| A4 | 11008 | 9883 mm | 4376.4736 mm |
| A5 | 10032 | 9883 mm | 12669.521 mm |

The two 65535-mm contrast values are treated as an upper-limit/sentinel-like
result, not precise range measurements. The common disparity estimate and
individual Hall positions are retained separately instead of forcing one
invented focus distance onto all modules.

All five surfaces contain nonconstant pixels and visual detail. This particular
20-ms outdoor scene is strongly overexposed: saturation ranges from 36.57 % to
58.28 %, so it proves the focused multi-module control path but is unsuitable
for judging highlight recovery or maximum image quality.

The matching A-group text report was subsequently retained as well. It records
the pinned 44,185-byte child and 13,764-byte AF shim hashes, the exact A-group
mode, focused-lock response, `lcc_exit_status=0`, `cleanup_ok=yes`, zero manual
control, no remaining LCC process or camera client, running camera services,
the same LRI size/SHA-1, and the intended normal-reboot decision. The physical
A1-A5 result is therefore verified at both artifact and supervisor levels.
