# All-16 dark frame series

## Goal and current status

This profile records a bounded series of dark frames from all 16 Light L16
modules with the lens covered. It is the first repository experiment that
varies `lcc -g` away from 1.0 and the first that issues more than one `lcc`
capture inside a single root session.

The series ran on the identified production camera on 2026-08-18 and completed
all 24 captures. Its results are in the "First physical series" section below.

The series answers four separate questions that the existing captures cannot:

- the per-module black level and fixed pattern noise at gain 1.0;
- the dark current slope across four integration times;
- the read noise, from the difference of repeated identical frames;
- how `lcc -g` is split into `sensor_analog_gain` and `sensor_digital_gain`.

The last question is specific to this camera. `liblight_ccb.so` passes the
`lcc -g` float directly into the CCB sensitivity command, and stock captures
show that the sensor reports a quantized analog gain with a fractional digital
remainder: one stock still recorded analog 3.75 on A1 and 7.5 on nine other
modules, and one failed control run recorded analog 3.75 with digital 1.03125.
The digital remainder therefore moves in 1/32 steps. Whether an arbitrary
requested gain is rounded to an analog step plus a digital remainder, or
refused outright, is unknown.

## Fixed measurement plan

Both axes use mask `FE FF 01`, the factory tuple `11 F1 00`, one 4160 x 3120
RAW10 surface per module, and a single `-e` value applied to every selected
module. The two axes share the gain 1.0 / 1.25 ms point, which is recorded
once as part of the exposure axis.

### Exposure axis, gain 1.0

| Integration time | Repeats |
| --- | ---: |
| 10 us | 3 |
| 1.25 ms | 3 |
| 5 ms | 3 |
| 20 ms | 3 |

### Gain axis, 1.25 ms

| Requested gain | Repeats | Reason |
| --- | ---: | --- |
| 2.0 | 3 | plain factor of two |
| 3.75 | 3 | analog value observed in a stock capture |
| 4.0 | 3 | probes rounding against the neighbouring 3.75 step |
| 7.5 | 3 | analog value observed in a stock capture |

Twenty-four captures in total, at roughly 260 MB each, for about 6.3 GB and an
estimated 25 minutes of wall time.

### Ordering and its justification

The exposure axis runs first, in ascending time, followed by the gain axis in
ascending gain. Three properties follow from that order:

- The exposure axis uses only the already exercised gain 1.0, so a refusal on
  the untested gain axis cannot cost the exposure measurement.
- Ascending order within each axis leaves an interpretable partial curve if
  the series aborts early.
- Ascending integration time makes thermal drift monotonic across the axis
  rather than alternating, so it can be separated from the dark current slope
  instead of aliasing into it.

The gain axis sits at 1.25 ms rather than at the shortest time. At 1.25 ms and
room temperature the dark current contribution stays far below the read noise,
while 1.25 ms is a more conservative choice than the never-exercised 10 us
point. Holding it fixed also keeps the plan fully compiled in and hash-pinned.

## First physical series, 2026-08-18

The complete series ran on the identified production camera with the lens
covered. All 24 captures completed, `supervisor_complete=PASS`, the settle gate
held 23 times without a reboot, cleanup verified, and the single reboot
followed. Every one of the 24 files transferred with the SHA-1 the camera
recorded, and each is 259,999,993 bytes.

### Requested exposure and gain both arrive unchanged

| Requested | Recorded | Deviation |
| --- | ---: | ---: |
| 10 us | 10,443 ns | +4.43 % |
| 1.25 ms | 1,253,260 ns | +0.26 % |
| 5 ms | 5,002,599 ns | +0.05 % |
| 20 ms | 19,999,956 ns | -0.00 % |

Nothing was clamped or substituted. The deviation shrinks with duration, which
is line-time quantization; the 10 us request lands essentially on the sensor
floor that Camera2 reports as 10,449 ns.

The gain question the series was built to answer resolves cleanly: **`lcc -g`
is applied entirely as analog gain.** `sensor_digital_gain` stayed exactly
1.00000 in all 24 captures, and `sensor_analog_gain` reproduced 2.0, 3.75, 4.0,
and 7.5 exactly. The 4.0 point existed specifically to test whether an
arbitrary value is rounded onto the neighbouring 3.75 step with a digital
remainder. It is not. The analog gain is therefore finer-grained than the stock
values 3.75 and 7.5 suggested, and the earlier observation of analog 3.75 with
digital 1.03125 came from the stock application splitting a total gain, not
from a sensor quantization.

### The gain is applied before the ADC

Read noise against gain, module A1 at 1.25 ms:

| Gain | Read noise (DN) |
| ---: | ---: |
| 1.0 | 0.678 |
| 2.0 | 0.925 |
| 3.75 | 1.447 |
| 4.0 | 1.503 |
| 7.5 | 2.675 |

Noise grows with gain but far less than proportionally. A least-squares fit of
`sigma^2 = (g*a)^2 + b^2` gives **a = 0.348 DN** before the amplifier and
**b = 0.598 DN** after it, and reproduces all five measurements to within 2 %.
Purely digital gain would scale noise exactly with `g`, putting 5.085 DN at
gain 7.5 where 2.675 DN was measured.

The practical consequence is that analog gain buys real sensitivity: the
input-referred noise falls from 0.692 DN at gain 1 to 0.357 DN at gain 7.5, a
factor of 1.90, against a limit of 0.348 DN. That gain is 91 % exhausted at
gain 4 and 98 % at gain 8; beyond that only headroom is lost, since saturation
scales as 1023/g. The stock values 3.75 and 7.5 sit inside that useful range.

### Sensor floor

At 10 us and gain 1.0 all sixteen modules read a black level between 41.81 and
42.20 DN, a spread of **0.39 DN across sixteen physically separate sensors**.
Fixed pattern noise is 0.66 to 0.92 DN, with C2 the only mild outlier. The
black level does not move with gain, so the pedestal is applied after
amplification.

### Dark current is below the noise floor here

At room temperature and 20 ms or less, dark current is not measurable. The cell
means across the exposure axis move non-monotonically within about 0.1 DN,
which is drift over the six minutes of the run rather than an exposure effect.
Resolving it needs second-scale integrations; Camera2 reports an exposure
ceiling of 29.98 s, so a short follow-up series between 100 ms and 20 s would
answer it.

### Two errors in the analysis tool that only this data could expose

The pixel packing was wrong. The tool assumed the byte-aligned MIPI CSI-2
layout; the format is a continuous little-endian bitstream, LSB first. Against
the covered lens the corrected reading gives a flat 42 DN field, while the
previous reading produced four systematically different levels spanning 505 DN
depending on a pixel's position within its five-byte group. This document
previously claimed the ordering could not be determined empirically and did not
affect any reported statistic. Both claims were wrong: a flat field determines
it immediately, and every number would have been corrupted. An ordinary
photograph cannot reveal it, because image content varies anyway.

The dark current slope used only the first frame of each cell, letting
per-frame drift enter as signal: it reported 2.824 DN/s for A1 where the cell
means give 0.073 DN/s. The slope now averages the repeats and the report prints
the scatter between repeats beside it.

## Payload identity

The current 24,542-byte child payload has SHA-1 `3cc7d997768acc0cb6c88de1f9acc8f686e04ffd`. The supervisor, the
Java source, and the build script each refuse a payload that does not match, so
changing the plan requires deliberately updating every pin.

The payload now carries two profiles, selected by invocation path: the 24-capture
series described above, and a 15-capture long-exposure series at
`light_l16_dark_frame_long_series_once.sh` that reaches for the dark current the
short series could not resolve. Its exposure axis is 100 ms, 1 s, 6 s, and a requested 29 s that the
sensor clamps to 19.45 s
at gain 1.0, three repeats each, and its final cell repeats the first: the
difference between them measures the thermal drift over the run, which is the
term that made the short series' apparent slope uninterpretable. The longest point
sits just below the 29.98 s ceiling Camera2 reports, and the per-capture timeout
rises from 60 to 120 seconds.

The packaged async writer shim is the reviewed 9,080-byte object with SHA-1
`0b93dc17a2c4219943293d96b7edda39be61613d`, which is reproducible only with
LLD 20.1.8. A different linker version produces a different byte count, and the
build refuses it rather than shipping an unreviewed object.

## Departures from the existing capture apps

Three properties of the existing one-shot apps do not carry over.

### A capture series inside one root session

Every prior child script issues exactly one `lcc` invocation. This one iterates
a compiled-in list of 24 (integration time, gain) pairs. Each iteration writes
its own `lcc.<index>.txt` log, so the async shim marker check keeps its exact
"each marker exactly once" form per capture rather than per run.

### No reboot between captures

The existing policy reboots Android after every possible camera attempt. That
policy exists because a hostless app cannot pull and verify an artifact before
deciding the camera may stay up. Rebooting 24 times would make the series
impossible, so it is replaced between captures by an explicit settle gate,
reusing the checks the current child already performs after its single
capture:

- `manual_control` forced to 0 and read back as `0x0`;
- no surviving `lcc` process;
- `dumpsys media.camera` reporting an empty active client list;
- `init.svc.media` and `init.svc.lightsvr` both `running`;
- exactly one new LRI in `/sdcard/DCIM/camera` attributable to this capture.

A single normal reboot still runs after the series completes or aborts. The
camera is left in an unknown state after 24 all-16 sessions and the reboot is
cheap relative to the run.

### No autofocus

The lens is covered, so the inline AF gate could never report
`AF_STATE_FOCUSED_LOCKED` and would suppress every capture. The series uses
the AF-free `lcc` path. The async LRI writer shim stays enabled: it exists
because synchronous LRI writing exhausted the metadata pool during all-16
captures, and 24 consecutive all-16 captures make that failure mode more
likely, not less.

## Abort semantics

The series stops at the first capture that fails its settle gate, produces no
new LRI, produces more than one, or returns a nonzero `lcc` status. Frames
already written stay on the device and are listed individually in the
manifest with path, size, and SHA-1. A partial series is a usable result, so
an abort is reported as `PARTIAL` with the completed capture count rather than
as a plain failure. The distinction matters to the reader: `PARTIAL` means the
listed frames passed every per-capture check, while `FAIL` means the run
cannot vouch for what it wrote.

The outer timeout is per capture, not per series: 60 seconds each, with the
supervisor bounding the whole child at 40 minutes. Twenty-four captures at
their full 60-second timeout already consume 24 minutes on their own, so a
30-minute outer bound would abort a slow but otherwise healthy series.

## Preflight

The first button repeats the established read-only checks: exact production
build, normal boot, SELinux state, idle root runner, vendor runner hash, and
all packaged payload hashes. Two checks are added.

Free space on `/data` must be at least 8 GiB. `/sdcard` is a FUSE mount over
`/data` on this build, so the existing `/data` check is the correct proxy for
the 6.3 GB of expected output plus working headroom.

A darkness check confirms the lens is actually covered before the series
starts. It reuses the Camera2 pipeline from `android/hdr-meter-probe` but not
its metering: auto-exposure is switched off rather than allowed to converge,
because AE would adapt to a dark scene and hide the very light leak the check
exists to find. Instead the check forces the worst case, setting the highest
sensitivity the device reports and a 100 ms integration. If the scene is still
dark under maximum amplification, the lens is covered.

It samples eight frames and evaluates both the mean luma and the 99.9th
percentile, since a mean alone would average away a leak confined to one edge.
The two thresholds are starting values on the 8-bit luma scale, not calibrated
constants, and the measured values are reported next to them so the first run
shows how much margin the cover actually has.

Camera2 is released in a `finally` block before the result is reported, and the
app refuses to arm the root runner unless its camera handles are null. The
child re-checks the same condition through `dumpsys media.camera` before it
runs `lcc`, so both sides verify it.

This check covers only the module Camera2 exposes, not all 16, so it catches a
forgotten cover rather than proving every module is dark. It is worth its
complexity because it prevents a 25-minute run from producing 6.3 GB of
unusable frames.

## Validation layers

The plan is constrained at three boundaries, but not in the same way at each.
Unlike `adaptive-a-group-capture`, nothing is measured and submitted at run
time: the plan is a compiled-in constant, the supervisor accepts no arguments,
and the child accepts none either. There is no value for a caller to corrupt,
so the layers guard the payload's identity rather than re-checking its numbers.

The child script validates every entry of its own plan before touching any
device state:

- exactly 24 entries;
- integration times drawn from the four compiled values, within 10 us to 20 ms;
- gains drawn from the five compiled values, within 1.0 to 7.5;
- gain 1.0 on each of the first twelve entries;
- 1.25 ms on each of the last twelve.

The root supervisor verifies the child's size and SHA-1 both as packaged and as
staged, requires the exact mode string back from the child, and requires the
child to report 24 requested captures.

The Java app pins the size and SHA-256 of the supervisor, the child, and the
async shim, and refuses to stage a payload that does not match. It does not
re-enumerate the plan values: pinning the child's hash already fixes them
exactly, and a second copy of the numbers in Java would be a value that can
drift out of step with the payload rather than an independent check.

## Unverified territory

Three parts of this plan have no physical precedent and may fail on first
contact.

The 10 us and 1.25 ms integration times have never been requested. The
shortest physically confirmed value is 6.36 ms, from the adaptive A1-A5 run;
the fixed 1.25 ms HDR profile was built but never triggered. `lcc` may clamp,
refuse, or silently substitute a different value. The LRI metadata records
what the sensor actually used, so a substitution is detectable after the fact
rather than during the run.

Gains above 1.0 have never been requested through `lcc`. The stock app reaches
3.75 and 7.5 through its own path, which is evidence that the sensor supports
them, not that `lcc -g` reaches them the same way.

Twenty-four consecutive all-16 captures in one session have never been
attempted. The longest prior sequence is one. Thermal drift across the run is
expected and is one reason the exposure axis is ordered rather than
interleaved.

## Analysis

Decoding and analysis happen on the host, not on the camera. The frames land
in `/sdcard/DCIM/camera` as ordinary HAL-generated LRIs and are pulled with
`adb pull`, as with every prior capture. `tools/analyze_dark_frame_series.py`
reduces the pulled series to a per-module report.

### Reused and new decoding

The LRI container and protobuf decoding already exist in
`tools/verify_stock_capture.py`, including the per-module `sensor_analog_gain`
and `sensor_digital_gain` fields. The analysis tool imports that decoder rather
than reimplementing it.

What does not exist is pixel access. Every current tool deliberately stops at
the metadata and states that it never interprets the RAW10 pixels. Dark frame
statistics need the pixels, so the tool adds a RAW10 unpacker: four pixels per
five bytes, 5200 bytes per row, 4160 x 3120 per surface.

### Where the pixels sit

Walking a retained all-16 capture established the layout. The pixel surfaces
sit *before* the protobuf message inside a `message_type == 0` block, between
the 32-byte block header and `message_offset`. Each module record carries a
surface submessage whose **field 5 is the surface's byte offset relative to the
start of its block**. `verify_stock_capture.py` does not read that field, which
is the one piece the analysis tool had to add.

The retained 259,999,993-byte capture distributes its 16 surfaces over three
blocks as 6, 6, and 4. Consecutive surface offsets differ by 16,228,352 bytes
while only 16,224,000 of those are pixels, so the surfaces are padded to an
alignment boundary. The tool reads the recorded offset instead of deriving it,
because that padding does not follow from the image geometry.

### The RAW10 bit order is assumed, not measured

The unpacker follows the MIPI CSI-2 packing: the low bits of pixels 0 to 3
occupy bits [1:0], [3:2], [5:4], and [7:6] of the fifth byte. That assignment
could not be confirmed from the retained capture. The alternative ordering
differs by at most 3 DN, and in a high-contrast scene the two low bits vanish
into the image content: the mean absolute difference between neighbouring
same-colour pixels is about 498 DN, so a same-colour-difference variance test
separates the two hypotheses by less than one part in twenty thousand.

This does not affect any statistic the tool reports. The two low bits are
equally distributed across the four quad positions, so mean level, fixed
pattern noise, read noise, and dark current are unchanged by the choice. It
would only change which individual pixel a hot-pixel coordinate names. A dark
frame over a genuinely flat field is what would settle it, which is one more
thing the first physical series can answer.

### Dependency boundary

A full series is 24 files of about 260 MB, or roughly 5 billion samples. That
is not tractable in pure Python, so the analysis tool requires NumPy. The
requirement is confined to this tool: NumPy is declared in a separate
`requirements-analysis.txt`, the tool exits with a clear message when it is
absent, and its tests skip rather than fail. Everything else in the repository
stays dependency-free apart from pytest.

Memory stays bounded by reducing each surface to its statistics as it is read.
Only read noise needs two surfaces resident at once, at 26 MB each as unpacked
16-bit samples.

### Reported quantities

Per module, and per (integration time, gain) cell:

- mean level in DN, the black level or pedestal;
- spatial standard deviation after subtracting the per-cell mean, the fixed
  pattern noise;
- temporal standard deviation from the difference of two repeats, divided by
  the square root of two, the read noise;
- count of samples above a fixed hot-pixel threshold.

Across cells:

- dark current as the slope of mean level against integration time at gain 1.0,
  reported per module in DN per second;
- requested `-g` against the recorded `sensor_analog_gain` and
  `sensor_digital_gain`, which resolves how the CCB sensitivity command
  quantizes a requested gain;
- read noise against gain, which indicates whether the gain is applied before
  or after the ADC.

The tool reports measured quantities and does not convert to electrons. A
conversion gain in electrons per DN cannot be derived from dark frames alone;
it needs illuminated flat fields, which this series does not record.
