# Light L16 same-session stock-path LRI capture

This deliberately narrow Android app tests the Camera2 path recovered from the
production Light Camera application. It uses no root runner, `lcc`, shell
command, service stop, firmware operation, or reboot.

The app first requires the exact production camera characteristics and the
Light-specific output format 48 at its advertised 3840 x 2160 stream size. It
keeps that separate from the 4160 x 3120 sensor active array and then opens one Camera2
session containing preview, JPEG, and format-48 surfaces, performs center AE
and AF, and keeps that session open. A second deliberate tap sends one fixed,
non-stacked `TEMPLATE_STILL_CAPTURE` to the JPEG and format-48 surfaces.

The returned format-48 buffer is retained only if it is at least 1 MiB and
starts with the `LELR` container magic. The LRI, JPEG, and a text report are
written below `/sdcard/DCIM/camera`. Every camera and image resource has a
bounded timeout and is closed on success, refusal, failure, or activity pause.
The preflight also refuses unless at least 512 MiB remain on that filesystem.

This first version fixes:

- camera ID `0`;
- focal length `2.8`, full active-array crop, and stock-equivalent zoom factor
  `1.0` (28 mm equivalent A/B capture intent);
- center-half AE and AF ROI;
- focus trigger type `USER_HW` / ID 6;
- stacked capture disabled;
- automatic ISO and shutter ranges (`0..0` vendor bounds);
- one still request per app run.

The report also attempts to read the stock firmware's stacked-state, total-size,
and transfer-count result keys. Failure to expose one of those diagnostic
values is reported as `unavailable_*` but does not discard an otherwise valid
LRI/JPEG pair.

It does not expose arbitrary keys or parameters. On 2026-08-14 the corrected
APK completed this flow on the identified camera and displayed `result=PASS`,
confirming that a third-party app can configure format 48 and receive both the
LRI and JPEG buffers. The transferred LRI now independently verifies ten A/B
modules at 28 mm, packed RAW10, matching exposure metadata, preserved focus and
mirror state, and non-constant pixels. The JPEG has not yet been transferred;
its size and SHA-256 are present in the successful report.

That live capture used the immediately preceding app revision. It already sent
the fixed 2.8 mm and non-stacked request, but did not yet send an explicit
`co.light.zoom_factor` or read the three stacking result keys. The current APK
adds those diagnostics and is built but not yet live-tested.

The first on-device preflight on 2026-08-14 safely refused before issuing a
still request because the initial implementation incorrectly required the
format-48 stream to equal the 4160 x 3120 active array. The device advertised
exactly one format-48 size, 3840 x 2160. This revision uses that observed stream
size while retaining the independent active-array check.

## Build

```sh
android/stock-lri-capture/build_debug_apk.sh
```

The signed APK is written to
`.build/stock-lri-capture/light-l16-stock-lri-capture-debug.apk`.

## Device procedure

1. Complete a normal Android boot and fully close the stock camera app.
2. Install and open `L16 Stock LRI Capture`.
3. Grant camera and storage permission.
4. Tap **1. PIPELINE PRÜFEN + FOKUS**.
5. Continue only when the report contains `pipeline=ARMED` and
   `focus=PASS`.
6. Within 15 seconds tap **2. FOKUSIERTES LRI AUFNEHMEN** once.
7. Wait for `result=PASS` and the final LRI path. No reboot is expected.

After pulling the three files into one directory, verify the complete bundle:

```sh
.venv/bin/python tools/verify_stock_capture.py \
  RDI_STOCK_YYYYMMDD_HHMMSS_mmm.txt \
  --reference /path/to/L16_00039.lri
```

If format 48 is absent, a vendor key is rejected, session configuration fails,
or AF does not lock, the app closes Camera2 without issuing a still request.
Do not retry an ambiguous camera failure before one normal restart.
