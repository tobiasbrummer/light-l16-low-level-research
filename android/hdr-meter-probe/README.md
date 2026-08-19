# Light L16 Camera2 adaptive HDR meter

This non-rooting app separates framing and exposure planning from the hostless
LCC capture. It opens a live Camera2 preview, waits for center-half AE to
converge, and leaves the preview running so the operator can compose the image.
A second deliberate tap locks AE/AWB where supported and samples eight frames
from a simultaneous 640 x 480 `YUV_420_888` preview stream for shadows. It then
uses the camera's minimum standard AE compensation (`-2 EV` on the verified
L16), waits for that AE result, locks again, and samples four highlight frames.

It creates no RAW still, LRI, JPEG, or root process. It does not invoke the
temporary-root runner, stop camera services, or reboot the camera.

## First RAW_SENSOR result and current design

The first physical revision reached converged AE at 2,086,773 ns and ISO 100,
but the advertised standard `RAW_SENSOR` request returned neither an image nor
a capture result within 12 seconds. The app closed Camera2 and confirmed that
it had invoked neither root nor LCC. The current revision removes that request
completely and uses only the already active processed preview stream.

The first physical YUV-only revision then completed eight frames at ISO 100
around 2.27 ms. Its 1st--5th percentile shadow band reported a temporal-SNR
proxy of 17.44, but 15.59 percent of the base YUV image was already at white.
That made the generated highlight endpoint underdetermined. The current
two-phase revision preserves that base measurement for shadows and adds the
separate `-2 EV` highlight phase instead of extrapolating from clipped data.

This is deliberately a first measurement proxy, not a claim that gamma-encoded
YUV is linear sensor data. The complete intermediate values and assumptions are
written to the report so the first paired meter/LRI result can calibrate or
replace them.

## Highlight and shadow measurement

Camera2 AE supplies `SENSOR_EXPOSURE_TIME` and `SENSOR_SENSITIVITY`. The app
converts this to an ISO-100-equivalent exposure for a later gain-1 LCC request.
After three settling frames, it samples every second luma pixel in eight frames.

The highlight endpoint comes from the separate negatively compensated phase
and uses its 99.99th percentile rather than one absolute maximum pixel. The
endpoint remains unresolved if that percentile reaches white or if more than
0.1 percent is at the conservative clipping threshold. Because Android 6 does
not expose the YUV dataspace here, the app records whether it inferred
full-range 0--255 or limited-range 16--235 luma and uses an explicitly reported
gamma-2.2 approximation. The highlight target is 70 percent in that approximate
linear domain.

For shadows, pixels between the temporal-mean 1st and 5th luma percentiles are
selected. Their per-pixel temporal mean and sample variance across eight frames
produce a median shadow-SNR proxy. The target is SNR 8. If the original AE used
more than ISO 100, a shot-noise approximation converts the observed SNR to the
longer ISO-100-equivalent exposure. Motion, preview denoising, tone mapping, and
the inferred YUV range remain explicit limitations.

## Adaptive ladder

The shortest endpoint is determined by highlight headroom. The longest endpoint
is the exposure estimated to reach the shadow-SNR target. The four Bayer roles
are logarithmically distributed between those measured endpoints:

```text
A1 = short
A3 = short * (long / short)^(1/3)
A4 = short * (long / short)^(2/3)
A5 = long
```

An ideal sensor-range plan and a pilot plan capped at the physically exercised
20-ms endpoint are reported separately. A2 is provisionally assigned the short
pilot exposure because it is the more sensitive panchromatic module. A numeric
PAN-to-Bayer correction is intentionally not invented; it requires a paired
meter/LRI calibration first.

The app does **not** transfer the reported values to the root runner. The later
LCC session must also autofocus again because a Camera2 lens state does not
survive the close/open boundary.

## Build and install

```sh
android/hdr-meter-probe/build_debug_apk.sh
adb install -r .build/hdr-meter-probe/light-l16-hdr-meter-probe-debug.apk
```

Fully close the stock camera app, then open **L16 HDR Meter**:

1. Tap **1. PREVIEW + BELICHTUNGSMESSUNG STARTEN** and allow camera access.
2. Wait until the second button becomes active, then frame a stationary scene.
3. Tap **2. HIGHLIGHTS + SCHATTEN MESSEN** once and hold the camera still while
   the preview briefly darkens for the second highlight phase.
4. Require `camera_closed=yes`, `raw_still_requested=no`,
   `root_or_lcc_invoked=no`, and preferably `probe=PASS`.
5. Copy the UTF-8 report from:

```text
/sdcard/Android/data/io.github.tobiasbrummer.lightl16.hdrmeterprobe/files/light-l16-hdr-meter-last-display.txt
```

`probe=PASS` means the bounded preview measurement completed with stable AE;
it does not yet validate the YUV-to-LCC radiometric transfer. Do not manually
copy the suggested values into an LCC command before the report is reviewed.
