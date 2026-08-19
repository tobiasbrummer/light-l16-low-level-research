# Stock Camera2 path to a focused LRI

This note records the narrow behavior recovered from the production Light
Camera application. It is a behavioral interoperability description, not a
source-code copy. On 2026-08-14 the corrected third-party app completed the
same-session flow on the identified camera and displayed `result=PASS`. Its
report and LRI have now been inspected on the host; the separately named JPEG
has not yet been transferred.

## Main result

The stock application does not close Camera2 and hand capture ownership to
`lcc`. Metering, autofocus, and the final LRI capture all run in one open
`CameraDevice` and `CameraCaptureSession`.

The application configures three output surfaces:

- a preview surface;
- a normal JPEG `ImageReader` using format 256;
- a Light-specific raw `ImageReader` using format 48, named `LIGHT_RAW10` in
  the application, at the largest size advertised by
  `StreamConfigurationMap.getOutputSizes(48)`.

The first third-party preflight on the identified production camera confirmed
on 2026-08-14 that format 48 is advertised, with the single size 3840 x 2160.
That is the proprietary stream's configured surface size, not the per-module
RAW dimensions: the Camera2 active array and the RAW10 surfaces stored inside
normal LRIs remain 4160 x 3120. The initial test app incorrectly conflated
those two dimensions and safely refused with `still_attempted=no`; no capture
request was issued.

Format 48 is not treated as a single unpacked Bayer plane by the application.
The first plane's `ByteBuffer` already contains the complete Light container.
The saver writes that buffer unchanged, then may append the stock application's
view-preference and GPS blocks. Existing camera LRIs begin with the ASCII magic
`LELR`, so a third-party receiver can validate the returned payload before
retaining it as `.lri`. The live PASS confirms that an ordinary installed app
can configure the three-surface session and receive both output buffers. It
is now also backed by the decoded LRI described below.

## First decoded third-party result

`RDI_STOCK_20260814_092458_282.lri` is 162,625,785 bytes and has SHA-256
`96fb735399657b385bab2376e0425eb406b24360a84da3a518df3f233c76d1e3`, exactly
matching the value written by the app before it reported success. All nine
LELR blocks end exactly at EOF and the reconstructed runtime schema consumes
every protobuf byte without unknown fields.

The two capture headers contain A1-A5 and B1-B5 exactly once, at stored focal
length 28 mm. Every module is enabled and stores one 4160 x 3120
`RAW_PACKED_10BPP` surface. Camera2 reported 32,566,846 ns for the still; the
module values range only from 32,557,206 to 32,571,178 ns. A1 used analog gain
3.75 and the other nine modules gain 7.5; all digital gains are 1.0.

Most importantly for the same-session hypothesis, both headers contain:

- `focus_achieved=true`;
- `af_trigger_src=HW_SHORT_PRESS (6)`;
- non-zero lens positions for all ten modules;
- no lens timeout, and no mirror timeout on the four movable B mirrors.

The file therefore proves that closing Camera2 was the reason the earlier
Camera2-to-`lcc` transition lost focus state. Keeping metering, AF, and capture
inside one session preserves the HAL's per-module lens and mirror solution.

All ten RAW planes decode to non-constant sensor values. At the calibrated
white level 1023, saturation ranges from 1.257 % (B4) to 12.703 % (B1); A2 and
B5 are also near 11 %. This is a valid focused capture, but not an exposure to
use as the quality ceiling for dynamic-range reconstruction. The lower-gain A1
retains more highlight headroom at 1.447 % saturation.

The report also records a 1,573,244-byte JPEG with SHA-256
`3ca840080af5d2ee0860ee7c1e45304f14e15df700dc346f30943cfcd45a60ca` at
`IMG_STOCK_20260814_092458_282.jpg`. Because only the `RDI_STOCK_*` files were
transferred, those JPEG bytes are not yet independently verified.

## Focus-to-capture sequence

The relevant manager chain is:

1. A repeating preview request performs AE metering.
2. A preview-template request carries the AF ROI,
   `CONTROL_AF_TRIGGER_START`, the selected focal length, and the Light vendor
   key `co.light.focus_type`.
3. The preview result callback waits for `CONTROL_AF_STATE=FOCUSED_LOCKED`.
4. The same session remains open. A `TEMPLATE_STILL_CAPTURE` request targets
   both the JPEG and format-48 surfaces.
5. The format-48 `ImageReader` returns the LRI while the JPEG reader returns
   the processed preview image.
6. Only after capture completion does the application restore its repeating
   preview request.

For a hardware shutter focus event the production enum maps
`USER_HW` to focus-type ID 6. This agrees with the
`HW_SHORT_PRESS (6)` autofocus source stored in a normal stock LRI.

## Recovered vendor keys

The stock Light SDK constructs ordinary Camera2 request keys from these names:

| Name | Java value type | Observed purpose |
| --- | --- | --- |
| `co.light.focus_type` | `Integer` | records/selects AF trigger source |
| `co.light.stacked_capture_state` | `Byte` | enables or disables the stock stacked-capture mode |
| `co.light.iso_range_min` | `Integer` | minimum auto ISO bound |
| `co.light.iso_range_max` | `Integer` | maximum auto ISO bound |
| `co.light.shutter_range_min` | `Long` | minimum auto exposure-time bound |
| `co.light.shutter_range_max` | `Long` | maximum auto exposure-time bound |
| `co.light.zoom_factor` | `Float` | Light zoom control |
| `co.light.burst_fps` | `Integer` | burst frame rate |

The SDK obtains the platform `CaptureRequest.Key(String, Class)` constructor
reflectively. A separate SDK dependency is therefore not inherently required
to reproduce these request keys on the production Android build. The bounded
live run now confirms that an ordinary third-party application is accepted for
format 48 and receives an LRI buffer. The LRI is fully decoded; only the
separate JPEG transfer remains pending.

## Why the Camera2-to-`lcc` transition lost focus

The 2026-08-13 transition test first obtained
`CONTROL_AF_STATE=FOCUSED_LOCKED`, closed Camera2, waited 750 ms after the
confirmed close callback, and then ran the fixed A1 `lcc` capture. Its LRI
contains `lens_position=0` and `LEGACY_UNKNOWN (0)` as AF source.

This is meaningful, not a general metadata limitation. A normal stock LRI
(`L16_00039.lri`) records non-zero lens Hall values for all ten fired modules,
including A1 at 12128, and records `HW_SHORT_PRESS (6)`. The normal HAL close
path also tears down the sensor session. Reducing the delay after `onClosed()`
cannot preserve a state that is destroyed by closing the session itself.

The implemented test therefore remains completely inside one Camera2 session.
It refuses unless format 48 at 3840 x 2160 and the independent 4160 x 3120
active array are advertised, then uses a fixed center AE/AF request, a fixed
non-stacked still request, bounded image timeouts, an `LELR` magic/size check,
and clean Camera2 shutdown on every path. The completed live run needed neither
root nor `lcc` and did not intentionally request the recovery reboot used by
the factory wrapper.

The deeper ODEX reconstruction, zoom/module-group evidence, stacking boundary,
and reproducible bundle-verification command are documented in
[`stock-app-control.md`](stock-app-control.md).
