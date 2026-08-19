# Fixed single-request HDR capture

## Goal and current status

This profile asks all 16 Light L16 modules for one frame in one `lcc`
workflow-1 request and writes the result to one untouched HAL-generated LRI.
It assigns three exposure roles across the modules so that a later geometric
fusion can recover highlights, shadows, depth, and repeated-view noise
reduction from the same shutter actuation.

The wrapper and argument construction are host-tested and statically checked.
The exact HDR exposure profile has **not yet been run on a camera**. It is a
bounded first experiment, not a claim of nanosecond-level sensor
synchronization or a finished HDR reconstruction.

## Adaptive metering precursor

The fixed 1.25/5/20-ms profile remains a reproducible baseline, but it cannot
adapt to scene brightness. The separate
[`android/hdr-meter-probe`](../android/hdr-meter-probe/README.md) app now
provides the non-rooting precursor for an adaptive profile: live framing,
center-half Camera2 AE, and a simultaneous low-resolution YUV stream. The first
physical revision's advertised `RAW_SENSOR` request timed out without image or
capture result, so the current app no longer submits a RAW still request.

It samples eight AE-locked preview frames for temporal shadow SNR, then requests
the camera's minimum standard AE compensation (`-2 EV` on this build) and
samples four separately locked highlight frames. The adaptive capture revision
uses p99.9 consistently with an explicit 0.1 % clipping budget; the older
p99.99 gate overreacted to a handful of isolated specular pixels. The app places the four
Bayer roles logarithmically between the measured endpoints and reports a
separate pilot plan capped at the physically exercised 20 ms. A2 remains
provisionally at the short endpoint until its panchromatic response is
calibrated.

The newer
[`android/adaptive-a-group-capture`](../android/adaptive-a-group-capture/README.md)
pilot deliberately performs the first paired experiment rather than treating
the unverified transfer as calibrated. It re-runs the same two measurement
phases, refuses unstable or unresolved endpoints, closes Camera2, and requires
a separate third-button confirmation before submitting the measured five-value
plan to the already exercised A1-A5 path. The plan is independently validated
at the Java, root-supervisor, and child-script boundaries; module mask and gain
remain fixed. This path is host-tested but has not yet produced a physical
adaptive LRI. Its first result must therefore be decoded and compared with the
meter report before the response model is accepted.

The first physical adaptive attempt on 2026-08-16 exposed a separate gate bug.
The scene metered at 42 ms / ISO 3200; its ISO-100-equivalent ideal endpoints
were 460 ms and 1.344 s, so the 20-ms pilot cap collapsed all five submitted
roles to 20 ms. The camera rebooted but no LRI was found, and the external
capture report contained only the pre-trigger progress text. The revised app
refuses a pilot span below 0.5 EV or equal A1/A5 values and can recover the
private supervisor result after an in-place APK update without invoking the
camera again.

A later useful run on the same day passed the revised meter with a 1.653-EV
pilot: requested A1/A2/A3/A4/A5 exposures were 6.360152, 6.360152, 10.099603,
16.037664, and 20.000000 ms. The retained 81,484,025-byte LRI contains exactly
those five modules under one image ID and timestamp. Sensor metadata differs
from the requests by at most 2,918 ns, both gains are 1.0, both capture headers
report `focus_achieved=true`, every lens position is nonzero with no lens
timeout, all five RAW10 surfaces are nonconstant, and the reconstructed schema
finds no unknown field. Raw white-level fractions range from 0 % on A1 to
0.015748 % on A5. This proves the dynamic five-value LCC submission and paired
artifact path; it does not yet calibrate cross-module radiometry or A2's
panchromatic response.

The external capture report still contained only Java's pre-trigger progress
text even though the LRI succeeded. The root supervisor now mirrors its
completed fixed private manifest to the app's already-created external report
before the delayed reboot, without letting report-copy failure affect capture
or reboot policy.

## Fixed exposure assignment

All modules use gain 1.0. The 1.25, 5, and 20 ms levels are separated by two
stops, giving a four-stop span between the shortest and longest integrations.
Keeping analog and digital gain at 1.0 preserves highlight headroom and avoids
introducing a second radiometric variable in the first test.

The shortest role is deliberately within exposure regions already present in
stock LRIs from this camera: A1 records about 1.048 ms in `L16_00035`, while B
and C modules record about 1.44--1.46 ms in `L16_00041`. That makes 1.25 ms a
bounded first request, but the exact manually requested value is not yet live
evidence. The 20 ms endpoint is already proven by the two prior all-16 runs.

| Module | Exposure | Role | Sensor |
| --- | ---: | --- | --- |
| A1 | 1.25 ms | short/highlight anchor | Bayer color |
| A2 | 20 ms | long/shadow and structure | panchromatic |
| A3 | 5 ms | medium | Bayer color |
| A4 | 5 ms | medium | Bayer color |
| A5 | 20 ms | long/shadow | Bayer color |
| B1 | 20 ms | long/shadow | Bayer color |
| B2 | 5 ms | medium | Bayer color |
| B3 | 5 ms | medium | Bayer color |
| B4 | 1.25 ms | short/highlight anchor | Bayer color |
| B5 | 20 ms | long/shadow | Bayer color |
| C1 | 20 ms | long/shadow | Bayer color |
| C2 | 5 ms | medium | Bayer color |
| C3 | 5 ms | medium | Bayer color |
| C4 | 20 ms | long/shadow | Bayer color |
| C5 | 1.25 ms | short/highlight anchor | Bayer color |
| C6 | 20 ms | long/shadow and structure | panchromatic |

This preserves short, medium, and long color observations in each focal-length
family. It also preserves equal-exposure pairs useful for correspondence:
A3/A4 and B2/B3 at 5 ms, B1/B5 and C1/C4 at 20 ms, plus further cross-exposure
views after radiometric normalization. A2 and C6 are assigned long exposures
because their panchromatic data can contribute low-noise luminance and matching
structure, but they must not be treated as ordinary Bayer color observations.

## Argument ordering

The selected mask is the already exercised all-module mask `FE FF 01`.
Reverse engineering of `lcc` shows that `-e` consumes consecutive numeric
arguments until the next option. It accepts either one common value or exactly
one value per selected module. `lcc` serializes those values in array order as
eight-byte entries in CCB command `0x32`. The ASIC-side module-set iterator
scans the selected mask upward and consumes one entry per set bit. The fixed
profile therefore supplies 16 distinct argv elements, in proven module-bit
order A1 through C6:

```text
-e 1250000 20000000 5000000 5000000 20000000 20000000 5000000 5000000 1250000 20000000 20000000 5000000 5000000 20000000 1250000 20000000
```

This is deliberately not a quoted string and not a comma-separated value.
The LRI later groups surfaces by ASIC (`A1,A5,B2,B4,B5,C5`, then
`A2,A3,A4,B1,B3,C2`, then `C1,C3,C4,C6`); that storage order must not be used
as the `lcc` exposure-argument order.

The device result and pulled pixel manifest record the argument count, module
order, and full module-to-exposure mapping. The host rejects a completed result
if any of those values differ from the compiled-in plan. This validates what
was submitted; the first decoded LRI must independently validate what every
sensor recorded.

## Safe local inspection

The dedicated entry point can print the complete plan without invoking ADB:

```bash
host/run_all16_hdr_capture_once.sh --describe
```

No argument also refuses execution and states that no camera action was
attempted.

## Live test procedure

The live profile uses the reversible async writer shim because the prior
all-16 test showed that synchronous LRI writing exhausted the metadata pool.
It still requires the exact reviewed 8,904-byte ARM32 shim with SHA-1
`150e53a736624010dc7fb741490ea8dca7afbfb8`.

Before a live run:

1. Save any camera work, close the stock camera application completely, and
   connect exactly one authorized L16 over ADB.
2. Inspect `--describe`, the device payload, and the host supervisor.
3. Set `LIGHT_L16_ASYNC_SHIM` to the reviewed shim's absolute path.
4. Use the exact confirmation below once.

```bash
LIGHT_L16_ASYNC_SHIM=/absolute/path/liblcc_async_writer_shim.so \
  host/run_all16_hdr_capture_once.sh \
  --execute-fixed-all16-hdr-async-shim-1p25-5-20ms-once-and-reboot
```

The supervisor verifies the known camera build and all payload/shim hashes,
consumes a profile-specific one-use arming file, submits one capture request,
pulls and hash-verifies one new LRI plus bounded diagnostics, and requests the
mandatory normal reboot. The original LRI remains on the camera. Any timeout,
malformed result, incomplete transfer, or ambiguous post-trigger state also
keeps the conservative reboot requirement.

## What the first live result must prove

A wrapper `PASS` is not enough. Before using the capture for reconstruction,
decode the retained LRI and require:

- exactly 16 enabled RAW10 surfaces with the known 6 + 6 + 4 ASIC grouping;
- one common image identifier and capture timestamp across all headers;
- gain 1.0 and the intended per-module exposure metadata (allowing the small
  sensor quantization already seen in the 20 ms captures);
- plausible black/white statistics, no clipped or empty module, and no new
  fatal control-path diagnostics;
- successful post-reboot identity, services, CameraService, process, and
  `manual_control=0` checks.

Only after those checks should the reconstruction pipeline estimate depth,
warp each view to a reference camera with occlusion handling, normalize each
module radiometrically, and merge unclipped samples with variance-aware
weights.

## Single-shot limitations

One `lcc` request is meaningfully closer to a single shot than a sequential
exposure bracket, but different integration lengths still have different
integration windows. A 1.25 ms and a 20 ms exposure differ by 18.75 ms in
duration; without a measured start/end alignment, their temporal-center offset
is not yet bounded. Moving subjects, moving mirrors, rolling shutter, and
occlusion changes can therefore create local HDR/depth conflicts. Those regions
need motion-aware rejection rather than unconditional averaging.
