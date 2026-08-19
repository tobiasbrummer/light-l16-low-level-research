# Stock application: zoom, stacking, and module groups

This note records behavioral interoperability facts recovered from the
production Light Camera APK/ODEX and cross-checked against real LRIs. It does
not contain vendor bytecode or decompiler output.

## Reproducible input boundary

The APK contains no `classes.dex`; its application code is compiled into an
Android 6 ART ODEX. Baksmali 2.5.2 can deodex it only when given the matching
`boot.oat` from the same system image.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `system/priv-app/light_camera/light_camera.apk` | 5,400,447 | `199b99ac0c38dede3195428ccd1f6a84bef526b10532e27e68fa4312b685be8d` |
| `system/priv-app/light_camera/oat/arm64/light_camera.odex` | 13,726,464 | `e6620d3eaaff7cf142af69647895b58b21f41741a94157cdd16850f5d910e517` |
| `system/framework/arm64/boot.oat` | 65,974,752 | `5529908556dfa8fc0fd37f16781bc8e88fbd729649b4e3d186d0cc5d130a3c27` |

The successful local run used Baksmali/Dexlib 2.5.2, JCommander 1.64, Guava
32.1.3-jre, and Failureaccess 1.0.1:

```sh
java -cp "$BAKSMALI:$DEXLIB2:$UTIL:$JCOMMANDER:$GUAVA:$FAILUREACCESS" \
  org.jf.baksmali.Main deodex -a 23 -j 8 \
  -b system/framework/arm64/boot.oat \
  -o stock-camera-smali \
  system/priv-app/light_camera/oat/arm64/light_camera.odex
```

It produced 3,923 Smali files. The result is an analysis intermediate and is
not included in this repository.

## Zoom request

The stock application represents the displayed focal length as 35 mm
equivalent and converts it to an absolute zoom factor:

```text
zoom_factor = displayed_focal_length_mm / 28
```

For every preview zoom update it writes three fields into the request:

- standard `LENS_FOCAL_LENGTH`, using a physical 2.8 or 7.0 mm lens;
- standard `SCALER_CROP_REGION`, for the digital crop relative to that lens;
- vendor `co.light.zoom_factor` as a `Float`, for the Light pipeline.

The UI defines stops at 28, 35, 50, 70, 85, 105, 135, and 150 mm. A separate
simulated-prime list contains 28, 35, 75, and 150 mm. Although the camera
characteristics also advertise a physical 15.0 mm focal length, the recovered
preview-selection loop deliberately never makes the last physical lens the
reference lens. This is consistent with the C modules contributing to a B/C
fusion capture while a B module remains the preview/reference path.

Setting only `LENS_FOCAL_LENGTH` is therefore not a faithful zoom request. A
future variable-zoom test app must set all three values in the same open
session, and must derive the crop from the active array rather than copying a
fixed rectangle.

## Actual module groups

The static zoom path is confirmed by seven archived LRIs. Each listed module
has an enabled 4160 x 3120 packed-RAW10 surface.

| LRI | Stored focal length | Capture headers | Fired module set |
| --- | ---: | ---: | --- |
| `L16_00035.lri`, `L16_00039.lri` | 28 mm | 2 | A1-A5 + B1-B5 |
| `L16_00033.lri` | 35 mm | 2 | A1-A5 + B1-B5 |
| `sample.lri` | 69 mm | 2 | A1-A5 + B1-B5 |
| `L16_00040.lri`, `L16_00041.lri` | 70 mm | 3 | B1-B5 + C1-C6 |
| `L16_00037.lri` | 149 mm | 3 | B1-B5 + C1-C6 |
| `RDI_STOCK_20260814_092458_282.lri` | 28 mm | 2 | A1-A5 + B1-B5 |

The effective archived boundary is therefore A/B below 70 mm and B/C from
70 mm. The A/B headers contain 5 + 5 modules; B/C contains 4 + 3 + 4. Those
headers are transfer batches. Their count alone does not show that a temporal
stack was taken.

The normal stock path does not select all 16 modules at once. Its two capture
sets overlap on the five B modules. The separately documented fixed factory
request remains the confirmed route for a single-request all-16 LRI.

## Stacked capture

Auto mode reads the preference `stacked_capture_state`; its declared default
is `on`. The settings entry is guarded by feature flag
`stacked.capture.selector`, whose fallback is false, which explains why the
control is normally hidden. Manual, ISO-priority, and shutter-priority modes
all explicitly disable stacked capture.

The request key is:

| Name | Type |
| --- | --- |
| `co.light.stacked_capture_state` | `Byte` |

The SDK also defines these result keys:

| Name | Type | Meaning exposed by SDK |
| --- | --- | --- |
| `co.light.stacked_capture_fw` | `Byte` | whether firmware selected stacking |
| `co.light.stacked_capture_total_size` | `Integer` | total stacked RAW size |
| `co.light.stacked_capture_num_transfers` | `Integer` | number of transfers |

The stock preview reads `stacked_capture_fw` for its low-light-assist state.
Neither the recovered Java code nor the archived LRI metadata is enough to
state the temporal exposure policy used by firmware. The no-root test app
therefore keeps stacking off until these result values are logged and a paired
on/off capture establishes the actual payload difference.

## Focus and mirror control boundary

The stock app sends an AF ROI, `CONTROL_AF_TRIGGER_START`, and
`co.light.focus_type`; the HAL then records individual lens and mirror Hall
positions in each module's LRI metadata. The archived hardware-shutter files
record non-zero lens positions for every fired module and `HW_SHORT_PRESS (6)`
as their AF source.

No stock Java request key for assigning an individual module's lens or mirror
position was found. Camera2 exposes the focus event and zoom intent; the HAL
selects per-module actuator positions. Direct per-module actuator movement is
therefore still part of the lower factory/CCB control path, not a demonstrated
Camera2 API.

## Bundle verification

The dependency-free verifier checks the app report, both SHA-256 values, LELR
framing, JPEG framing and dimensions, module set, AF source, lens positions,
per-module exposure/gains, and 4160 x 3120 packed-RAW10 surface metadata:

```sh
.venv/bin/python tools/verify_stock_capture.py \
  RDI_STOCK_YYYYMMDD_HHMMSS_mmm.txt \
  --reference /path/to/L16_00039.lri
```

The fixed 2.8 mm app expects the A/B group by default. Use
`--expect-group BC`, `all16`, `A1`, or `any` only for an intentionally different
profile. The verifier explicitly reports `pixel_validation=NOT_PERFORMED`;
RAW sample quality remains a separate reconstruction-stage check.

The first third-party LRI now passes all LRI-side checks. The whole bundle
still reports failure only because the JPEG, whose filename starts with
`IMG_STOCK_` rather than `RDI_STOCK_`, was not copied into the same directory.
