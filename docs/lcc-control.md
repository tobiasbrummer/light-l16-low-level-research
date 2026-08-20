# Light L16 module selection through the factory `lcc` tool

## Result and boundary

The LightOS 1.3.5.1 factory tool can express an arbitrary subset of the 16
camera modules. It accepts a module mask plus common or per-module exposure,
gain, resolution, and frame-rate values. The complete factory capture tuple is
also statically known.

This proves the userspace control interface. Bounded live tests additionally
prove that the fixed wrapper can capture A1 alone on the examined production
camera at 2.61 ms and 20 ms, including through the reversible async probe. A
synchronous and an async test prove that the factory-derived explicit mask
`FE FF 01` can return all 16 module surfaces in one 20 ms capture request. The
repository provides mask tooling, a camera-read-only A1 preflight, seven tightly
fixed execution profiles, and a conservative host-side log analyzer. This is
not yet a claim that every arbitrary subset, direct focus operation, or direct
mirror-control path works safely, nor does a common request prove
nanosecond-level sensor synchronization.

## Relevant factory binary

The workflow implementation is `/system/etc/lcc`, a 501,352-byte, 32-bit ARM
PIE with symbols and DWARF data. Its known identities are recorded in
[`artifacts/known-builds.json`](../artifacts/known-builds.json). The similarly
named `/system/bin/lcc_cli_tool` is a small raw read/write frontend and does not
contain the capture workflow.

For a workflow, `lcc` dynamically loads `/system/lib/hw/camera.msm8996.so` and
resolves `open_camera`, `start_capture`, and `close_camera`. The resulting path
is:

```text
lcc -> camera.msm8996.so -> liblight_ccb.so -> three ASICs -> 16 modules
```

The kernel's `manual_control` attribute is a gate in this sequence. It is not a
module selector.

## Module mask

The CLI reads three hexadecimal bytes as a little-endian 24-bit mask. Bit zero
is a separate global-selection shortcut. Bits 1 through 16 map to the physical
modules:

| Module | Bit | Single-module bytes | ASIC |
| --- | ---: | --- | ---: |
| A1 | 1 | `02 00 00` | 1 |
| A2 | 2 | `04 00 00` | 2 |
| A3 | 3 | `08 00 00` | 2 |
| A4 | 4 | `10 00 00` | 2 |
| A5 | 5 | `20 00 00` | 1 |
| B1 | 6 | `40 00 00` | 2 |
| B2 | 7 | `80 00 00` | 1 |
| B3 | 8 | `00 01 00` | 2 |
| B4 | 9 | `00 02 00` | 1 |
| B5 | 10 | `00 04 00` | 1 |
| C1 | 11 | `00 08 00` | 3 |
| C2 | 12 | `00 10 00` | 2 |
| C3 | 13 | `00 20 00` | 3 |
| C4 | 14 | `00 40 00` | 3 |
| C5 | 15 | `00 80 00` | 1 |
| C6 | 16 | `00 00 01` | 3 |

The ASIC groups are A1/A5/B2/B4/B5/C5, A2/A3/A4/B1/B3/C2, and
C1/C3/C4/C6. Selecting all 16 modules explicitly gives `FE FF 01`; the global
shortcut alone is `01 00 00`.

Use the host-only helper to encode or decode selections:

```bash
python3 tools/lcc_mask.py A1 B3 C6
python3 tools/lcc_mask.py --decode 02 01 01
```

The expected combined mask is `0x010102`. The helper rejects empty, unknown,
out-of-range, and ambiguous global-plus-explicit masks. It does not generate or
execute a capture command.

## Focus, mirror position, and same-family capture

The same factory binary contains a separate autofocus workflow (`flow_id=0`).
Its parser accepts the same three-byte module mask followed by exactly four
decimal ROI values (`x`, `y`, `width`, `height`) per selected module. The run
path constructs a CCB message beginning with `0x5a 0x80`, sends it through the
configured factory bridge, and waits up to 20 seconds for the asynchronous
response. This is a statically confirmed module-selective autofocus operation,
not an absolute lens-Hall-position setter.

The first bounded A1 center-AF attempt on 2026-08-10 established an additional
runtime precondition without moving the actuator. From an otherwise clean idle
normal boot, workflow 0 emitted the expected `0x5a 0x80` request but the kernel
reported `NACK: slave not responding, ensure its powered` and
`I2C block write failed` for slave `0x08`. No interrupt arrived, the wrapper did
not start the planned post-AF capture, and it requested its mandatory normal
reboot. Post-boot checks found `manual_control=0`, the expected ASIC firmware,
both services running, and no active camera client. This is evidence that the
request never reached the autofocus controller, not evidence of an actuator
failure.

The `-m` values are not interchangeable ASIC choices: `0` selects the
factory QUP-I2C bridge, while `1` and `2` select CCI0 and CCI1 sensor-register
paths. The recovered factory actuator utility also uses `-m 0`, but always
first invokes `prog_app_p2 -q`. Decompilation of the exact production binary
shows that this option selects the normal strap state and toggles the reset
GPIOs for all three ASICs, then returns before configuration parsing, SPI,
erase, write, calibration, or firmware-programming paths. The revised bounded
AF profile therefore hash-verifies that binary, executes only `-q`, requires
the stock boot script's ASIC-ready response before AF, and uses only its fixed
`-F` power-off branch during cleanup. This is a reversible all-ASIC reset, not
an A1-only operation, so the normal Android reboot remains mandatory.

The second bounded A1 center-AF attempt on 2026-08-10 exercised that revised
path. `prog_app_p2 -q` returned zero and the stock readiness request returned
`01 00`. The kernel then accepted all 13 bytes of transaction `0x0039` without
the earlier NACK or any later I2C error, but workflow 0 received no interrupt
within its 20-second wait. The wrapper therefore suppressed capture, ran the
verified `-F` cleanup successfully, restored `manual_control=0`, and requested
the mandatory normal reboot. CameraService reported no active client both
immediately before and after the readiness probe. Static inspection shows that
the AF workflow opens its response socket and writes the CCB request but,
unlike capture workflow 1, never loads or opens the camera HAL. The strongest
current hypothesis is therefore that the AF controller needs sensor/preview
state established elsewhere. This is an inference, not proof: `01 00` proves
the bridge/ASIC readiness query, not readiness of the contrast-AF engine.

The current production sensor module sharpens that contract. Its autofocus
handler is sensor event `0x54`; it rejects a zero-sized ROI and any ROI for
which `x + width` or `y + height` exceeds the active sensor dimensions, then
queues the four 16-bit ROI coordinates to the CCB. `ccb_set_focus_mode()` only
stores the selected mode and `ccb_is_afRunning()` reads the controller's busy
bit. `ccb_set_cam_af_mode()` sends CCB opcode `0x56` plus one mode byte. No
absolute lens-Hall-position setter has been identified in this path.

The mirror path is also more constrained than the exported names initially
suggested. `ccb_set_mirror_update(fd, ccb_address)` sends the fixed three-byte
payload `59 80 00`; its second argument is a CCB address, not a requested Hall
position. `ccb_set_zoom_factor(fd, factor, ccb_address)` sends `5c 00` followed
by the four bytes of the floating-point zoom factor. In the production sensor
dispatcher, event `0x53` adjusts the crop from focal-length and zoom data,
event `0x58` queues a mirror-move message with no target position, and event
`0x59` queues only a one-byte mirror trigger. The higher controller explicitly
ignores a zoom request while autofocus is running.

An older recovered FTMSYS sensor library exports both `ccb_set_focus()` and
`ccb_move_mirror()`, but the latter merely wakes its mirror worker through a
condition variable; it is not an absolute-position write either. The strongest
current interpretation is therefore that the normal stack derives mirror
motion internally from bounded zoom/crop/focal-length state and records the
Hall value as feedback. The exact zoom bounds and settling protocol still need
to be recovered before a live mirror test. The embedded geometry labels B1,
B2, B3, B5, C1, C2, C3, and C4 as `MOVABLE`; B4, C5, and C6 are `GLUED`, and
the five A modules have no mirror. Direct mirror actuation remains outside the
execution wrapper. The idle workflow-0 experiment should not simply be
repeated; the next useful focus experiment needs a bounded normal Camera2/HAL
preview state while retaining A1 selection and response logging. Any movable
B/C mirror test remains later and requires separately recovered zoom bounds and
settling semantics.

### Recovered stock AE-then-AF ordering

The production `light_camera.apk` has no `classes.dex`; its application DEX is
embedded in the precompiled arm64 ODEx. Extracting that DEX from the exact
backup and inspecting `AutoExposureManager`, `FocusManager`,
`CaptureRequestManager`, and `ModeReqMgr` confirms the missing runtime context
more precisely:

- metering runs on an existing Camera2 preview session by installing one
  `CONTROL_AE_REGIONS` rectangle in a repeating preview request;
- the application retains per-frame `CaptureResult` objects and reads
  `SENSOR_EXPOSURE_TIME` from them;
- only after the AE stage does it create a separate preview-template request,
  set one `CONTROL_AF_REGIONS` rectangle, set `CONTROL_AF_TRIGGER_START`, and
  submit that request to the same active capture session;
- the focus request also carries the selected focal length. The normal app
  therefore supplies considerably more state than factory workflow 0's
  standalone CCB request.

This confirms that an active Camera2 session is a real stock precondition, not
just an inference from the earlier timeout. It still does not establish that a
third-party Camera2 client can access the same vendor path, nor that lens state
survives closing that client before an `lcc` capture. The non-rooting
`android/meter-focus-probe` APK tests exactly the first question. It must pass
and close CameraService cleanly before AE/AF is coupled to the hostless capture
supervisor.

The first live run on the identified production camera passed this gate on
2026-08-13. Camera ID 0 reported Camera2 hardware level 1 (`FULL`), active array
4160 x 3120, and focal lengths 2.8, 7.0, and 15.0. With the 2.8 mm path and the
center-half ROI 1040,780..3120,2340, AE reached state 2 (`CONVERGED`) at
8,333,333 ns and sensitivity 100. The subsequent AF request over the same ROI
reached state 4 (`FOCUSED_LOCKED`). The probe then closed the capture session
and camera and reported `probe=PASS`. This proves that a separately installed
Camera2 client can establish the missing AE/AF preview state. It does not yet
prove that the locked physical lens position survives closing Camera2 and
entering the separate `lcc` raw-capture path; that is the next transition gate.

The factory masks for the two focal-length families asked about are:

```text
A1-A5: 3E 00 00
C1-C6: 00 F8 01
```

The all-16 captures prove that every surface in either subset can be returned
by one request, although these exact subset masks have not yet been exercised
alone. A1, A3, A4, and A5 are Bayer color modules while A2 is panchromatic.
C1-C5 are Bayer color modules while C6 is panchromatic; C1-C4 additionally
have movable mirrors, whereas C5 and C6 use fixed geometry.

Each Bayer module already contains all three color components after demosaicing;
the modules do not each represent a different RGB channel. A useful fused image
is nevertheless possible: normalize each sensor radiometrically, preserve its
actual CFA layout, select/interpolate the per-focus calibration, compute the
mirror-dependent extrinsics where applicable, estimate scene depth, warp every
view to a reference camera with occlusion handling, and only then fuse color
and detail. The panchromatic A2/C6 view can contribute luminance or structure,
but cannot be treated as a missing RGB channel or multiplied into a Bayer view
by one scene-independent factor because its spectral response differs.

The A family is the sensible first reconstruction target: it has four color
views, no moving mirrors, and a common nominal 28 mm focal length. A C-family
fusion is possible in principle but requires the captured mirror Hall values
and mirror calibration for four of its six views. A simple raw-pixel average
would be physically wrong for either family because the modules have different
viewpoints, CFA phases, distortion, and occlusions.

## Capture grammar and independently confirmed tuple

Workflow 1 parses these six positional values after `-f 1`:

```text
MASK0 MASK1 MASK2 DATA0 VC FLAGS
```

`DATA0` packs the transmitter in its low nibble and stream state in its high
nibble. A recovered factory MIPI test uses all explicit module bits and the
tuple `11 F1 00`. Both an older FTMSYS CCB library and the current
`liblight_ccb.so` independently construct the same three bytes for selected
modules. For A1, the statically derived positional part is therefore:

```text
02 00 00 11 F1 00
```

`wf_parse_capture()` sets `n_burst=1` before parsing this ordinary flow. Only
the separate burst workflow can replace it from an additional positional
argument. The fixed `-f 1` command is therefore expected to generate one LRI,
which is why the wrapper treats zero or multiple new files as a failed or
ambiguous result.

The relevant parameter options are `-e` for exposure, `-g` for gain, `-R` for
resolution, and `-F` for frame rate. Each option accepts either one common
value or one value per selected module. The capture parser also accepts an
empty FPS list, so `-F` can be omitted; the recovered factory MIPI call does so.

### Per-module exposure argument order

The `-e` command-line case consumes consecutive decimal argv elements until it
reaches the next option and stores them, without reordering, in the 16-element
`uint64_t exposure.data` array. `wf_parse_capture()` accepts either zero/one
common value or exactly `n_total_cam` values. A comma-separated list or one
quoted argument containing spaces is therefore not equivalent to 16 values.

`wf_run_capture()` serializes the multi-value array into CCB command `0x32`: the
three-byte selected-module mask is followed by one little-endian eight-byte
value after another. The matching module-attribute handler in the identified
ASIC firmware traverses its module set through an iterator. Its initializer at
`0x361c` scans upward until it finds the next set bit; its increment helper at
`0x61c94` restarts that scan at the current bit plus one. The handler at
`0x6898` advances the input pointer by eight bytes for every selected module
when multiple values are present. The handler and iterator-initializer code
bytes match in all three identified ASIC firmware images; the named increment
helper was decompiled in the analyzed ASIC1 mapping.

For mask `FE FF 01`, bits 1 through 16 are all set and already map to A1 through
C6 in that order. Consequently, the first exposure argv element applies to A1,
the second to A2, and so on through the sixteenth for C6. The later LRI surface
order is grouped by ASIC and is unrelated to this command order. See
[`single-shot-hdr.md`](single-shot-hdr.md) for the fixed first profile. Its
first live LRI must still independently confirm all 16 exposure metadata
values; static command ordering is not a substitute for sensor evidence.

### What `-C` actually does

The binary's built-in help describes `-C` as `--output`, while its actual long
option table calls it `--channel`. Neither name describes an image-output path
accurately. The parser's `C` case sets the global `_Bool pipe_fd` at ELF virtual
address `0x8284`. All of that flag's read references are in
`wait_for_response()`. When enabled, that function writes hexadecimal CCB read
data or a write transaction/status line to
`/data/lcc_output_<transaction-id>.txt`.

`wf_run_capture()` has no reference to `pipe_fd` and does not call
`wait_for_response()`. Consequently, adding `-C` to a capture does not request
an LRI, RAW frame, or other pixel artifact. It only enables response files for
command paths that use `wait_for_response()`.

A separate branch in `wf_run_capture()` does send an additional CCB command
`0x2E` for the selected resolution. That branch is gated by
`capture_cmd.resolution_len` at structure offset `0x98`, which the `-R` parser
fills. It is not gated by `-C`. For the three accepted resolutions, the command
uses scale denominators 1, 2, and 4 respectively. The fixed A1 command already
contains `-R 4160,3120`, so this resolution configuration is present even
though `-C` is absent.

### Automatic LRI output in the HAL

Pixel persistence is real, but it is independent of `-C`. In the identified
`camera.msm8996.so`, the capture interface follows this chain:

```text
lcc wf_run_capture -> exported start_capture
  -> LccInterface::startCapture
  -> request thread submits the special output stream
  -> LccInterface::processCaptureResult
  -> LccInterface::writeFile
```

The special stream has format value `0x30`. When a returned output buffer uses
that stream, `processCaptureResult()` calls `writeFile()`. The writer reads the
file descriptors and lengths supplied in the returned descriptor buffer,
maps each read-only, and appends each complete buffer to one file. Its filename
builder produces:

```text
/sdcard/DCIM/camera/RDI_YYYYMMDD_HHMMSS_mmm.lri
```

`closeCamera()` waits for the result condition before closing the HAL, subject
to its timeout. Thus the fixed `lcc` command is statically expected to create
an LRI automatically; no output option is needed. This is stronger than merely
finding an `.lri` string, because the writer is reached from the capture-result
callback and the factory workflow calls the exported start and close functions.
Multiple bounded live runs have since produced files through exactly this path; see
the confirmed results below.

## Reference values from a normal A1 capture

A normal 28 mm capture made by this camera on 2026-08-08 provides a concrete A1
reference. The source LRI has SHA-256
`04a5589f0ed5e66a866d81e3f2376c2f90411b83ae85279e075122db2566bf12`.
Its A1 module record contains:

| Field | A1 value |
| --- | ---: |
| `sensor_exposure` | 2,609,592 ns |
| `sensor_analog_gain` | 1.0 |
| `sensor_digital_gain` | 1.0 |
| raw format | `RAW_PACKED_10BPP` |
| dimensions | 4160 x 3120 |
| row stride | 5200 bytes |

The global `ViewPreferences` record differs slightly: it reports
`image_integration_time_ns = 2,601,928` and `image_gain = 2.0`. The paired JPEG
(SHA-256
`8f60161a7cbad17a6b62139ad2de6f7002c21355109b881a8f734494833e5fe5`)
independently reports 1/384 s, ISO 200, 28 mm, and 4160 x 3120. This confirms
that the global values describe the rendered exposure, but they should not be
substituted for the direct per-module values: the current `liblight_ccb.so`
passes the `lcc -g` float directly into the CCB sensitivity command. The
best-supported initial A1 input was therefore gain 1.0 and exposure
2,609,592 ns.

No capture FPS is stored in this LRI, and `sensor_scan_speed` is absent. A
Camera2 preview rate would describe a different path and is not a justified
substitute. Because `-F` is optional, the first candidate command deliberately
omits it:

```text
<lcc-copy> -m 0 -s 0 -f 1 02 00 00 11 F1 00 -R 4160,3120 -e 2609592 -g 1.0
```

This command was initially derived statically and from metadata. It has since
completed on the camera; the resulting LightHeader records 2,610,960 ns, gain
1.0, and exactly one A1 module.

The first execution deliberately omitted `-C`: its small CCB-response files add
no pixel evidence and the recovered factory MIPI test does not use it. The HAL
wrote the expected timestamped LRI, allowing the control-path diagnostics and
generated LRI to be captured in the same bounded attempt. Container framing and
transfer integrity alone still do not establish that the file contains exactly
A1 or plausible raw samples; that was checked separately from the decoded
LightHeader and RAW10 data.

## Why live calls need a wrapper

The normal path is stateful:

```text
open HAL -> manual_control=1 -> configure -> manual_control=0
         -> start capture -> close HAL
```

Static control-flow inspection found error branches after the HAL has opened
which do not all converge on the final cleanup. An external timeout can also
terminate the process before `manual_control=0` or `close_camera`. Resetting the
sysfs gate from a supervising shell addresses only the former; closing state
owned by the terminated process may still require a normal device restart.

The camera-read-only payload
[`device/a1_capture_dry_run.sh`](../device/a1_capture_dry_run.sh) verifies:

- UID 0 through the bounded `fihop` runner and cleared runner properties;
- the exact production build, completed normal boot, and known `lcc` identity;
- `manual_control=0`, a stopped `fwupgrade` service, and no active camera
  clients;
- the fixed A1 mask, factory tuple, and reference parameters used for the
  original first-live candidate.

It prints the concrete plan above. It never copies or invokes `lcc`, never
writes camera sysfs, and has no execution option.

The separately named [`device/a1_capture_once.sh`](../device/a1_capture_once.sh)
is the enabled wrapper. Despite the historical filename, it contains exactly
seven fixed profiles selected only by the exact installed path:

| Installed path | Selection | Timeout | Minimum free space | Clean PASS |
| --- | --- | ---: | ---: | --- |
| `/data/local/tmp/light_l16_a1_capture_once.sh` | A1, `02 00 00` | 30 s | 256 MiB | may remain up |
| `/data/local/tmp/light_l16_a1_center_af_capture_once.sh` | all-ASIC normal reset/readiness, A1 center AF, then A1 capture | 30 s per camera operation | 256 MiB | always reboot |
| `/data/local/tmp/light_l16_a1_inline_af_capture_once.sh` | A1 center AF inside the open LCC HAL session, then A1 capture | 45 s | 256 MiB | always reboot |
| `/data/local/tmp/light_l16_a1_async_capture_once.sh` | A1, `02 00 00`, reversible async shim | 30 s | 256 MiB | always reboot |
| `/data/local/tmp/light_l16_all16_capture_once.sh` | all 16, `FE FF 01` | 60 s | 1 GiB | always reboot |
| `/data/local/tmp/light_l16_all16_async_capture_once.sh` | all 16, `FE FF 01`, reversible async shim | 60 s | 1 GiB | always reboot |
| `/data/local/tmp/light_l16_all16_hdr_async_capture_once.sh` | all 16, `FE FF 01`, fixed per-module 1.25/5/20 ms assignment, reversible async shim | 60 s | 1 GiB | always reboot |

All seven use `11 F1 00`, 4160 x 3120, gain 1.0, and one capture frame. The first
six use one common 20,000,000 ns value. The HDR profile supplies 16 fixed
exposure arguments in A1-through-C6 bit order; it does not accept caller input.
The center-AF profile first applies mask `02 00 00` and the fixed
middle-50-percent ROI `1040,780,2080,1560`; no caller-supplied coordinate or
module is accepted. Any other installed path is rejected. The payload is
intentionally unsuitable for arbitrary commands or parameters. Before it can
reach `lcc`, it requires all of the following:

- the exact profile-specific one-use arming value
  (`A1_CAPTURE_20000000NS_GAIN_1.0_ONCE`,
  `A1_CENTER_AF_THEN_CAPTURE_20000000NS_GAIN_1.0_ONCE`,
  `A1_INLINE_AF_CAPTURE_20000000NS_GAIN_1.0_ONCE`,
  `A1_ASYNC_SHIM_CAPTURE_20000000NS_GAIN_1.0_ONCE`,
  `ALL16_CAPTURE_20000000NS_GAIN_1.0_ONCE`,
  `ALL16_ASYNC_SHIM_CAPTURE_20000000NS_GAIN_1.0_ONCE`, or
  `ALL16_HDR_ASYNC_SHIM_CAPTURE_1250000_5000000_20000000NS_GAIN_1.0_ONCE`),
  which it immediately deletes;
- UID 0 through the self-clearing `fihop` runner and the exact known build,
  kernel, SELinux, ASIC firmware, `lcc` identity, and camera-HAL identity; the
  AF profile additionally requires the exact known `prog_app_p2` identity;
- normal boot with `media` and `lightsvr` running, `ro.light.aos=1`, no special
  LCC mode, stopped `fwupgrade`, and no existing `lcc` process;
- `manual_control=0`, no active CameraService client, UDP port 5000 unused, and
  the profile-specific free-space threshold under `/data`.

It then makes a fresh, hash-verified executable copy of `/system/etc/lcc` in a
PID-specific root-owned directory and runs only the selected fixed profile
through Toybox `timeout`: TERM after 30 seconds for the established A1
operations, 45 seconds for inline A1 AF, or 60 seconds for an all-16 capture,
KILL after five more seconds. The still-running root supervisor
immediately writes `manual_control=0` again,
checks that no `lcc` process or CameraService client remains, captures bounded
before/after logs, and deletes the executable copy. The five non-AF profiles do
not run `prog_app_p2`, reset an ASIC, start `fwupgrade`, touch a block device,
or invoke mirror, firmware, or calibration controls. The center-AF profile is
the sole exception: it makes a separate hash-verified copy
of the exact 159,664-byte `prog_app_p2`, invokes only its non-flashing `-q`
normal-reset branch, and requires the known read-only
`lcc -m 0 -s 0 -r -p 12 34 15 02` response beginning with `01`. It then invokes
factory workflow 0 once with its compiled-in A1 mask and ROI. Success requires
the positive interrupt marker, incremented transaction ID, exactly one
status-`0` response header, and a matching status-`0` transaction response
file; `lcc` exit zero alone is insufficient. Its exit trap invokes only the
same verified tool's `-F` ASIC power-off branch, rejects a surviving process or
nonzero cleanup result, and still mandates a normal reboot. No profile starts
`fwupgrade`, touches a block device, or invokes firmware, calibration, EEPROM,
raw sensor-register, or mirror controls.

Before invoking `lcc`, the wrapper snapshots existing HAL-generated
`RDI_*.lri` paths without changing them. After `lcc` returns and immediate
cleanup passes, it requires exactly one new timestamp-shaped path, records its
size and SHA-1, and leaves the device copy intact. The host pulls that file to
the capture bundle and verifies the same size and SHA-1 locally. An absent or
ambiguous new artifact prevents a `PASS` result.

Because a timeout can kill `lcc` before its own `close_camera`, the fail-safe
default after reaching `lcc` remains a normal reboot. Only the unmodified A1
profile may change that decision to `normal_reboot_required=no`, and only when `lcc`
returned zero, exactly one LRI was found, `manual_control=0`, no `lcc`
process remains, CameraService is empty both immediately and after a settle
interval, and `media` plus `lightsvr` are still running. All three all-16 profiles
and the center-AF and experimental async A1 profiles keep
`normal_reboot_required=yes` even on that clean path. The host
additionally requires the complete diagnostic directory and a byte- and
SHA-1-matching LRI before it honors either result. Every timeout, signal,
failure, malformed result, or incomplete pull still requests `adb reboot`.

## Running the camera-read-only A1 preflight

Review both the payload and the root-runner procedure in
[`temporary-root.md`](temporary-root.md). Then stage the payload:

```bash
adb push device/a1_capture_dry_run.sh /data/local/tmp/light_l16_a1_dry_run.sh
adb shell 'chmod 0700 /data/local/tmp/light_l16_a1_dry_run.sh; rm -f /data/local/tmp/light_l16_a1_dry_run.result'
```

Use the same ordered `fihop` setup as the root probe, with the dry-run script as
the second argument. Trigger once, read
`/data/local/tmp/light_l16_a1_dry_run.result`, and perform the mandatory host
property cleanup even if no result appears.

Success ends with:

```text
capture_executed=no
preflight=PASS
```

This is still a camera-read-only inventory step: the bounded root runner clears
its persistent properties and the payload writes temporary result files, but it
does not issue a camera-control request.

## Running the fixed capture wrapper

Do not invoke the device payload directly. From a clean checkout, review both
wrappers and make sure the camera contains no unsaved work. Then use the host
supervisor, whose deliberately long confirmation argument is required:

```bash
host/run_a1_capture_once.sh --execute-fixed-a1-20ms-once-with-failure-reboot
```

The center-AF profile is deliberately separate and always reboots after its
response and diagnostic bundle have been pulled. A post-focus A1 image exists
only when every AF response gate succeeds:

```bash
host/run_a1_capture_once.sh \
  --execute-fixed-a1-center-af-then-20ms-capture-once-and-reboot
```

The explicit all-16 entry point has a separate confirmation and always reboots
after pulling the attempted capture:

```bash
host/run_all16_capture_once.sh --execute-fixed-all16-20ms-once-and-reboot
```

The experimental A1 shim profile also has a separate confirmation, requires
the already reviewed external ARM32 build by exact size and SHA-1, and always
reboots. It does not replace or modify the installed HAL:

```bash
LIGHT_L16_ASYNC_SHIM=/absolute/path/liblcc_async_writer_shim.so \
  host/run_a1_capture_once.sh \
  --execute-fixed-a1-async-shim-20ms-once-and-reboot
```

The all-16 async profile uses the same reviewed library and retains the
separate synchronous baseline profile:

```bash
LIGHT_L16_ASYNC_SHIM=/absolute/path/liblcc_async_writer_shim.so \
  host/run_all16_capture_once.sh \
  --execute-fixed-all16-async-shim-20ms-once-and-reboot
```

The fixed single-request HDR profile has its own local-only description mode.
This does not touch ADB:

```bash
host/run_all16_hdr_capture_once.sh --describe
```

Its deliberately separate execution token submits the fixed A1-through-C6
1.25/5/20 ms assignment through the reviewed async path and always reboots:

```bash
LIGHT_L16_ASYNC_SHIM=/absolute/path/liblcc_async_writer_shim.so \
  host/run_all16_hdr_capture_once.sh \
  --execute-fixed-all16-hdr-async-shim-1p25-5-20ms-once-and-reboot
```

This exact exposure profile has not yet run on a camera. The command above is a
prepared first live test, not a confirmed result.

The host side requires exactly one authorized ADB device and rejects it unless
build, model, and product identifiers match the examined L16. It then pushes
and hashes the payload, creates the one-use arm file, verifies all six `fihop`
properties before triggering once, and polls for a completed result for at most
90 seconds for a non-AF A1 profile, 120 seconds for center AF plus capture, or
150 seconds for all 16. The async profile
additionally pushes the reviewed shim to `/data/local/tmp`, verifies its exact
size and SHA-1 on the device, and requires all eleven runtime lifecycle markers
before accepting `PASS`. The examined Android build uses
the legacy ADB shell protocol and does not propagate remote command failures
to the host, so completion is
recognized only from an exact stdout marker produced after `final_status`
exists. The one-use arm value is likewise read back and compared before the
trigger. Its exit trap clears all six properties; after a trigger may have been
delivered it does not delete the remote arm or payload in the trap, because
that could race a newly started wrapper. It pulls the result and diagnostic
directory under `output/a1-capture-<UTC>/`,
`output/a1-center-af-capture-<UTC>/`, `output/a1-async-capture-<UTC>/`,
`output/all16-capture-<UTC>/`, or
`output/all16-async-capture-<UTC>/`, or
`output/all16-hdr-async-capture-<UTC>/`. A completed clean unmodified A1 result
with the settled
postconditions above remains up only after both the diagnostics and LRI were
copied successfully. A completed async A1 or all-16 result reboots after those
copies have been verified. Otherwise an attempted or uncertain capture requests
`adb reboot`. A preflight failure before `lcc` does not cause an automatic
reboot. The original HAL-generated LRI is deliberately left on the camera.

The pulled bundle can then be classified locally without reconnecting to the
camera:

```bash
python3 tools/analyze_a1_capture.py output/a1-capture-<UTC>
python3 tools/analyze_a1_capture.py output/all16-capture-<UTC>
```

The analyzer checks the completed wrapper result, immediate and settled cleanup
state, CameraService client lists, positive `lcc` lifecycle messages, newly added
dmesg/logcat faults, the host copy's size and SHA-1, and the public 32-byte
`LELR` block framing. It subtracts identical lines from the bounded before
snapshot so an already-existing message is not reported as a new capture
failure. Its verdicts and exit codes are:

| Verdict | Exit | Meaning |
| --- | ---: | --- |
| `CONTROL_PATH_PASS_LRI_FRAMING_ONLY` | 0 | control path and cleanup passed; the copied LRI matches the device hash and has a completely framed LELR block stream |
| `WRAPPER_FAILED` / `CONTROL_PATH_FAILED` | 1 | an explicit wrapper postcondition or diagnostic error failed |
| `INCOMPLETE_EVIDENCE` / `PREFLIGHT_STOPPED` | 2 | no capture was attempted or required evidence is missing |

Even the pass verdict reports
`pixel_validation=lri_transfer_and_container_framing_valid_protobuf_and_pixels_unverified`
and
`post_reboot_validation=not_in_capture_bundle`. It cannot replace the live
normal-boot checks below, nor does it decode the LightHeader to prove which
modules fired or test whether their raw samples are plausible.

After the supervisor returns, independently verify the continued or rebooted
device state before opening the camera application:

```bash
adb shell 'getprop sys.boot_completed; getprop ro.bootmode; getprop init.svc.media; getprop init.svc.lightsvr'
adb shell 'cat /sys/class/light_ccb/common/manual_control; /system/bin/toybox pgrep -x lcc; true'
adb shell 'for p in persist.sys.fihop persist.sys.fihop1 persist.sys.fihop2 persist.sys.fihop3 persist.sys.fihop4 persist.sys.fihop5; do printf "%s=%s\n" "$p" "$(getprop "$p")"; done'
```

Expected: boot completed `1`, boot mode `unknown`, both services `running`,
`manual_control mode is 0x0`, no `lcc` PID, trigger `0`, and five empty argument
properties. On a clean no-reboot result, `/proc/uptime` should continue rather
than reset. If ADB disappears before the host can request a required reboot, do
not retrigger `fihop`; perform one normal hardware restart instead.

`final_status=PASS` has a deliberately narrow meaning: the exact `lcc` process
returned zero, exactly one new HAL LRI was found and hashed, and the gate and
process checks passed. A no-reboot result additionally includes the settled
CameraService and service-state checks, and the host verifies both diagnostic
and pixel copies before leaving the camera up. This is still not by itself proof
that the requested modules delivered valid pixels: the LRI's decoded module
list, exposure metadata, dimensions, raw format, and sample statistics must be
checked separately.

## Same-session A1 focus gate

The fixed source
[`shim/lcc_a1_focus_capture_shim.c`](../shim/lcc_a1_focus_capture_shim.c)
implements the narrow missing transition without replacing Camera2 or the
camera HAL. Static decompilation of the identified HAL shows that
`LccInterface::openCamera()` configures two streams and starts its request
thread. That thread immediately submits preview-template requests in a loop;
`startCapture()` merely changes a flag so that a later request uses the special
LCC output stream. The shim interposes that mangled `startCapture()` method,
not the factory CLI parser.

The ELF relocation table makes the narrower hook possible without replacing
the HAL. Both
`QCamera3HardwareInterface::processCaptureRequest(camera3_capture_request*)`
and `LccInterface::processCaptureResult(camera3_capture_result const*)` have
`R_ARM_JUMP_SLOT` entries. Disassembly of `prepareCaptureRequest(bool)` shows
the frame number at request offset `0`, settings at offset `4`, and the normal
Camera3 request layout; `processCaptureResult()` reads the output count and
buffer pointer at offsets `8` and `12`, fixing the result metadata pointer at
offset `4`. The static result trampoline calls the exported result method
through its PLT entry as well.

When the interposed `startCapture()` arms the gate, the next LCC preview request
is copied and its metadata is cloned with spare capacity. The clone is updated
and read back before use with the standard Android tags
`CONTROL_AF_MODE=AUTO`,
`CONTROL_AF_REGIONS=[1040,780,3120,2340,1000]`, and exactly one
`CONTROL_AF_TRIGGER=START`. Subsequent preview and capture requests retain the
same mode and ROI with `CONTROL_AF_TRIGGER=IDLE`; START is never repeated. The
result hook ignores frames older than the recorded trigger frame and releases
the real `startCapture()` only after an exact byte-valued
`CONTROL_AF_STATE=FOCUSED_LOCKED`. `NOT_FOCUSED_LOCKED`, a five-second wait,
invalid metadata, a HAL request error, or a duplicate start suppresses capture.
The interposed `closeCamera()` then calls the HAL's direct `close()` path so the
request thread and camera object are released without waiting for an image that
was never requested.

This revision issues no raw CCB/I2C AF command and consumes no transaction ID.
The device wrapper requires each essential positive metadata marker exactly
once, rejects every error/suppression marker, and still mandates a normal
reboot. This first profile is deliberately A1-only; it does not yet claim that
all 16 modules can autofocus together.

The host-native mock covers both boundaries. It starts a real preview-request
thread through the same interposed symbols, verifies the exact mode, ROI, one
START and later IDLE values, and sends ACTIVE_SCAN followed by a terminal
result. `FOCUSED_LOCKED` must reach the real start and normal close exactly
once, while `NOT_FOCUSED_LOCKED` must reach neither and must use the direct
cleanup path. This verifies hook ordering and fail-closed behavior, not
physical focus or image sharpness.

The first physical hostless run on 2026-08-16 stopped before loading the camera
HAL. The constructor emitted only `loaded`, `preload_cleared`, and
`real_bind_resolve_error`; Android 6's linker did not resolve the real `bind`
through `RTLD_NEXT`. No AF request or capture release occurred, `lcc` was
terminated by the bounded wrapper, and the recorded cleanup was settled.

A second physical run resolved `bind` from Bionic `libc.so`, loaded the HAL,
captured the response socket, and reached `startCapture()`. The 13-byte raw CCB
AF write for A1 and the center ROI was accepted by the sysfs/I2C path, but LCC's
ongoing preview results continued logging AF reset, full-frame ROI, focus type
zero, and trigger zero. Roughly 6.5 seconds later the HAL reported a SOF freeze;
the camera daemon stopped, `processCaptureRequest` returned `-19` for frame 116,
and the raw response wait eventually timed out. The shim suppressed capture,
the wrapper restored `manual_control=0`, removed the temporary process state,
and the mandatory reboot returned the normal services. This is evidence of a
control-path conflict, not a reason to lengthen the raw CCB timeout.

The current metadata-interposition revision is the response to that result. It
has passed the expanded native tests, APK hash-chain build, and one physical
A1 capture on the identified L16. The resulting 16,566,521-byte LRI has SHA-1
`0c1a2caf98ec8857fa4bdcb57c3a05c28a71b856`, parses without unknown fields,
and records `focus_achieved=true`, center ROI `(0.5,0.5)`,
`lens_position=11376`, disparity focus distance 1691 mm, contrast focus
distance 2439.4873 mm, and `lens_timeout=false`. The two preceding transition
captures recorded `focus_achieved=false`, zero ROI, zero focus distances, and
`lens_position=0`. This proves that the same-session gate physically moved A1
and preserved the resulting position into the RAW capture. The scene itself
was severely underexposed (RAW median 43 at black level 42), so it is not a
controlled optical-resolution comparison.

The hostless [`android/a1-capture`](../android/a1-capture/README.md) APK now
builds this ARM32 preload into a temporary asset at APK build time, pins it in
the app and root supervisor, and selects only this inline-AF child path. A host
is therefore required for installation, but not for the later two-tap capture.
This packages the same physically exercised gate. The new separate
[`android/a-group-capture`](../android/a-group-capture/README.md) app applies it
to the fixed `A1-A5` mask as the next still-unverified multi-module step.

## Device-side wrapper syntax

The current 57,260-byte thirteen-profile payload has host SHA-1:

```text
ad8c78eed6dbd188682dd8cf273beb31e86abc12
```

Its host shell syntax check and automated tests pass. The ninth and tenth
profiles are timeout probes: all sixteen modules at gain 1.0 with the combined
preload loaded, at 8 s and 6 s respectively. They were written to test whether
raising LCC's completion budget lets an exposure past the roughly six-second
ceiling finish. Both have now been executed and the answer is no; see "Long
exposures fail in `writeFile`, not on the completion timeout" below. They are
kept because they reproduce that negative result.

The 6 s probe is the narrower of the two and was added after the 8 s probe
returned `Closed camera pipeline, 0` despite a confirmed patch. `lcc` derives
its own budget in `wf_run_capture` as

```text
thread_time_out = (uint32)(max_capture_delay + exposure_s
                           + single_burst_delay * (burst_cnt - 1)) + 1
```

which carries no readout term at all, and the HAL turns any value at or below 9
into a flat 15 s. Reading all sixteen modules takes about 14 s, measured from
the 16-18 s spacing of the successful one-second dark frames. So 1 s of
integration completes and 6 s does not, and 6 s is the first exposure the shim
must carry if the 15 s budget is really the binding limit. The 8 s probe sits
far enough past that edge for other limits to interfere. The eighth profile is
the
fixed `A1-A5` same-session AF request described above. Its first physical LRI
has been decoded successfully: exactly A1-A5, one shared image ID/timestamp,
`focus_achieved=true` in both capture blocks, five nonzero lens positions, and
no lens timeout. Its matching supervisor TXT also verifies the expected payload
and shim hashes, focused-lock result, zero LCC exit, complete cleanup, settled
services and camera clients, identical LRI size/SHA-1, and intended normal
reboot. The seventh profile's exact per-module HDR exposure
assignment also remains unexecuted. The thirteenth profile requests 29 s, which the sensor clamps to 19.45 s; it is the firmware's
stated ceiling and the first exposure where the HAL derives T+5 instead of
its flat 15 s. The twelfth profile is the control for both: the same 6 s capture with no
preload at all. The eleventh profile repeats the 6 s capture with the mmap-failure probe in
the extra-preload slot instead of the timeout patch, to recover the errno the
HAL omits. The preceding 50,264-byte ten-profile payload had SHA-1
`caee8d954e44a75ae9ef88ecfcc8f3f3fddbfe05`. The preceding 48,937-byte
nine-profile payload had SHA-1
`51ba0377db913cf4361a34e301935d361011eeb4`; it carried the 8 s probe alone and
completed the physically executed run that motivated the 6 s probe. The
preceding 43,160-byte seven-profile
payload with SHA-1 `293c6f246728ccc457b7ce2f5bb4fdedbc6db8f5`
completed the physical A1 inline-AF capture. The preceding 43,655-byte payload
used the failed raw-CCB same-session approach. The preceding 38,779-byte six-profile
payload had SHA-1 `bb20f8989cc99c4c9bc93b355bc6dabd7596a9d5`. The preceding
36,730-byte five-profile payload had SHA-1
`22d9d184dbf7e7026af047a0ff447cf7dd67a965`; a syntax-only device copy passed
`/system/bin/sh -n`, matched the host, and was removed without arming or
invoking any camera operation. The preceding live-tested 35,706-byte payload had SHA-1
`75acc3355dc9027363557046cdc007dd7bff0e31`; its device copy passed the same
syntax and identity checks before the second bounded center-AF attempt. The
preceding 28,338-byte five-profile payload had SHA-1
`050d9fec5d21f82b5feabf494f72e448bc2a01f1`; host and device syntax checks
passed and the device copy matched before the first bounded center-AF attempt
documented below. The preceding 21,310-byte four-profile payload had SHA-1
`d6f6a4e683272a5c4fa26404240a297d320dc4b3`; both the host syntax check and the
device's `/system/bin/sh -n` returned zero before it completed the fixed all-16
async run documented below. The preceding 20,598-byte three-profile
payload had SHA-1
`105ba4152f0c8c161d48e63ddda7dd87db8a1a3a`; host and device syntax checks
passed before it completed the fixed async A1 run documented below. The
previous 16,998-byte dual-profile payload had SHA-1
`6dd00e850a558ff6ae8fcbfe8896f95022988f9e`; host and device hashes matched,
the device's `/system/bin/sh -n` returned zero, and the syntax-only copy was
removed before that payload completed the fixed A1 live run documented below.
It differs from the exact 16,997-byte
payload used for the 20 ms all-16 live run only by increasing the A1 profile's
bounded diagnostic tail from 500 to 2,000 lines. That preceding payload had
SHA-1 `9162065d787c866096ff064e0c28495d7a29aef5` and also passed the device
syntax check before its capture.

For history, the preceding 15,481-byte A1-only payload had SHA-1
`a8270d08d19aa44c5511117c9646a10cb763f823` and completed the 20 ms A1
run. An earlier 14,338-byte payload from commit `7a10811` was also
syntax-checked on the same device; its SHA-1 was
`4cb888e6470f9c5a052fbc74f4276608c831b1e4`, and that check did not execute
the capture path.

## Confirmed legacy ADB behavior and aborted capture attempts

Two initial live attempts on 2026-08-09 stopped before the wrapper created its
PID-specific work directory. Their retained 95-byte root result ended at:

```text
mode=A1_FIXED_CAPTURE_ONCE
warning=this_payload_executes_lcc_after_preflight
failure=not_armed
```

There was no new `RDI_*.lri`, no completed result, and no evidence that the
fixed `lcc` command, the camera HAL capture path, or a sensor was reached. The
host requested its conservative normal reboot in both cases.

The second attempt exposed a device-specific supervisor bug. On this production
build, `adb shell 'false'` returns status zero to the host. A remote `grep` of
the incomplete result reported status one inside the device shell while the
enclosing host `adb` process still returned zero. The old poll therefore tried
to pull the result immediately and its failure activated the reboot trap. A
post-reboot `console-ramoops` copy ended with a normal host-requested reboot at
uptime 366.797897 seconds and contained no incident-time `lcc` or camera-driver
fault. The updated supervisor uses an exact `COMPLETE`/`PENDING` stdout marker,
verifies the arm file contents before triggering, and has a regression test in
which the first two remote polls are pending while legacy ADB reports success.
No successful live attempt is represented by this subsection.

## First bounded center-AF attempt: request rejected before actuation

On 2026-08-10, a separate 20 ms A1 capture first completed normally and was
retained as the before-AF reference under
`output/a1-capture-20260810T155527Z/`. Its 16,566,521-byte LRI has SHA-1
`31bb537d2f26911b70a648e435bcb3b1f292f026`.

The then-current center-AF profile was subsequently armed once. All preflight
gates passed, including no active CameraService client, `manual_control=0`, and
the expected binary identities. `lcc` constructed the fixed A1/center-ROI
request, but its output was:

```text
Received length -1 does not match expected length 8
Don't recieve interrupt signal
```

The corresponding kernel delta proves the earlier failure point:

```text
asic_i2c_write_store: block_addr = 0x0038
i2c-msm-v2 75b9000.i2c: NACK: slave not responding, ensure its powered
asic_i2c_write_store:2127 I2C block write failed
```

The wrapper correctly treated `lcc`'s misleading zero exit status as failure,
recorded `autofocus_attempted=yes`, left `capture_attempted=no`, restored
`manual_control=0`, found no surviving `lcc` or camera client, and requested a
normal reboot. The evidence bundle is
`output/a1-center-af-capture-20260810T155743Z/`. After reconnect, the camera
reported completed normal boot, ASIC firmware `0076D11B`, running `media` and
`lightsvr`, no active camera client, and `manual_control=0x0`.

This result invalidates the old idle-boot assumption but does not invalidate
workflow 0 or A1 focus control. Static analysis of the recovered factory test
sequence led to the revised, gated normal-reset/readiness path described above.
That revised path subsequently passed host tests, device syntax/hash
verification, and the explicitly acknowledged all-ASIC reset boundary before
the second bounded run described below.

## Second bounded center-AF attempt: transport fixed, AF state still missing

The revised profile was armed once on 2026-08-10. The exact 159,664-byte
`prog_app_p2` copy matched SHA-1
`d6d74641759f2e208beac4318507ea1b71923db4`; its non-flashing `-q` branch
returned zero, and the stock readiness request returned `01 00`. The AF command
then emitted transaction `0x0039` with the fixed A1 mask `02 00 00` and center
ROI `1040,780,2080,1560`. Unlike the first attempt, the kernel logged the full
13-byte write and no NACK or I2C failure:

```text
asic_i2c_write_store: block_addr = 0x0039
asic_i2c_write_store, write_data : 0x5A 0x80 0x02 0x00 0x00 ...
```

No response interrupt or status header arrived during the internal 20-second
wait. The wrapper rejected `lcc`'s zero process status, recorded
`failure=autofocus_interrupt_not_received_once`, and did not issue a capture.
Its historical result also retained `autofocus_response=not_run`; that was a
diagnostic-label defect, not evidence that AF was skipped. The current wrapper
sets `autofocus_response=interrupt_not_received` for this exact marker pair.
Its fixed `prog_app_p2 -F` cleanup returned zero, no `lcc` or `prog_app_p2`
process remained, and the host requested a normal reboot. The evidence bundle
is `output/a1-center-af-capture-20260810T161912Z/`.

After reboot, the identified production camera reported
`sys.boot_completed=1`, ASIC firmware `0076D11B`, `manual_control=0x0`, running
`media` and `lightsvr`, cleared `persist.sys.fihop*` arguments, no test process,
and no active CameraService client. This second result proves that the factory
reset/readiness sequence removes the I2C transport failure. It does not prove
lens motion or working direct autofocus. Because CameraService was closed and
`wf_run_auto_focus()` itself has no camera-HAL open path, an active
sensor/preview pipeline is now the leading missing precondition.

## Confirmed dry-run result

The checked-in payload completed successfully on the known production camera
on 2026-08-09. Immediately before the trigger, CameraService reported an empty
active-client list. The result confirmed the expected UID-0 init-shell context,
build, kernel, SELinux state, ASIC firmware, `lcc` identity,
`manual_control=0`, and stopped `fwupgrade` service. It ended with:

```text
camera_clients=none
capture_executed=no
preflight=PASS
```

Independent host cleanup then left the trigger at zero, all five argument
properties empty, `fihop` and `fwupgrade` stopped, the ordinary ADB shell at UID
2000, `manual_control=0`, and no payload, result, or CameraService dump in
`/data/local/tmp`. This confirms the preflight and cleanup path only. No `lcc`
process or camera-control request was executed.

The extended payload was run again on 2026-08-09 after replacing the plan's
placeholders and removing the unjustified guessed FPS argument. It again ended
in `preflight=PASS`, now also confirming `ro.light.aos=1`, empty LCC mode,
running `media` and `lightsvr`, unused UDP port 5000, no `lcc` process, and
233,615,444 KiB free under `/data`. Host cleanup again left all six properties
clear, `fihop` stopped, the normal ADB shell at UID 2000, both services running,
and `manual_control=0`. No capture was executed.

## Confirmed manual A1 captures

Two bounded captures completed on the same identified production device on
2026-08-09. In both cases `lcc` returned zero, logged `Open camera pipeline`,
`Start Capture`, and `Closed camera pipeline, 1`, and produced exactly one new
16,566,521-byte LRI. The host copy matched the device-reported size and SHA-1.

| Requested exposure | LightHeader exposure | Analog / digital gain | LRI SHA-1 |
| ---: | ---: | ---: | --- |
| 2,609,592 ns | 2,610,960 ns | 1.0 / 1.0 | `261939154b0f32319a1b7281aacc6606b9f30660` |
| 20,000,000 ns | 19,999,956 ns | 1.0 / 1.0 | `3838ff0e363942d4940eebf045b717d6dcbf6d67` |

The corresponding SHA-256 values are
`a2ce009944056f865946e141fbc121ef1a87c0c725035054614886b7dd0be99d`
and
`18abe9c46a0a49366374258490fc27b102118ecd9502ce68e4f6ac5f35895fe5`.
The reconstructed runtime schema consumes all protobuf bytes in all eight
blocks with zero unknown fields. Both capture headers contain exactly one
enabled module: A1, reference camera A1, focal length 28, RAW10 at 4160 x 3120,
row stride 5200, lens and mirror position zero, and sensor temperature 27.

The lossless RAW10 unpacker reports the following uncorrected sensor counters;
the calibration block specifies black level 42 and white level 1023:

| Exposure | Min | Mean | Median | 99th percentile | Max | Samples at 1023 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2.61 ms | 33 | 43.3758 | 43 | 46 | 81 | 0 |
| 20.00 ms | 33 | 59.5707 | 59 | 82 | 106 | 0 |

The requested exposure increased by 7.66x and the captured signal increased
strongly without approaching saturation. The black-subtracted mean cannot be
used as a precise linearity measurement because the two desk-scene captures
were not simultaneous and ambient/display light was not controlled.

The first wrapper version conservatively requested a normal reboot after its
successful 2.61 ms capture. The 20 ms version returned
`normal_reboot_required=no`: CameraService was empty immediately and after the
settle interval, `manual_control=0`, no `lcc` remained, and both services were
running. Independent live checks at uptime 2311.37 and 2907.47 seconds confirmed
continued uptime, all six runner properties neutral, `fihop` stopped, no active
camera client, `manual_control=0`, and no remaining payload or arm file. The
camera was not rebooted.

Both bounded log deltas contain recurring Qualcomm HAL lines labelled `ERROR`,
including the missing-HFR-stream message and teardown notifications for pending
requests. They did not coincide with a nonzero `lcc` result, a MIPI/kernel hard
failure, an invalid LRI, or a dirty live state. The analyzer therefore retains
them as `REVIEW` and returns `INCOMPLETE_EVIDENCE` rather than silently treating
them as benign. The separate timeout matcher no longer mistakes the normal
`Stopping SOF timeout thread` teardown line for an actual capture timeout.

## Confirmed explicit all-16 capture

One bounded all-16 capture completed on the same device on 2026-08-09 with:

```text
<lcc-copy> -m 0 -s 0 -f 1 FE FF 01 11 F1 00 -R 4160,3120 -e 20000000 -g 1.0
```

`lcc` returned zero and the wrapper found exactly one new 259,999,993-byte
LRI. The host copy matched the device size and SHA-1
`bbb723bf04388e961ee3d61e2fd01df9833f39e5`; its SHA-256 is
`2fef156da924746ce3e7cf6f71f558c74b3f47f632a4f9d404c75f19cfa85ceb`.
The container has ten completely framed blocks. The runtime schema consumes
every protobuf byte with zero unknown fields.

The three ASIC capture blocks contain the expected 6 + 6 + 4 grouping:

- A1, A5, B2, B4, B5, C5;
- A2, A3, A4, B1, B3, C2;
- C1, C3, C4, C6.

All 16 records are enabled RAW10 surfaces at 4160 x 3120. Every record carries
19,999,956 ns, analog gain 1.0, digital gain 1.0, and sensor temperature 27.
The three block headers also carry the same 128-bit image ID and the same
2026-08-09 21:21:53 +02:00 timestamp. Together with the single HAL request and
mask, this proves one logical multi-ASIC capture. It does not measure the
physical exposure-start skew between sensors.

The lossless unpacker visited all 207,667,200 raw samples. The scene was the
upward-facing camera under the monitors; the counters are therefore a
plausibility check, not a flat-field or linearity measurement:

| Module | Min | Mean | Median | P99 | Max | At/above 1023 | Mirror | Vignetting choice |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A1 | 30 | 50.8375 | 49 | 77 | 98 | 0 | absent | single |
| A2 | 34 | 61.1967 | 57 | 107 | 130 | 0 | absent | single |
| A3 | 33 | 51.8716 | 49 | 79 | 105 | 0 | absent | single |
| A4 | 32 | 51.5906 | 49 | 80 | 105 | 0 | absent | single |
| A5 | 33 | 50.2101 | 48 | 80 | 105 | 0 | absent | single |
| B1 | 30 | 53.3570 | 51 | 88 | 108 | 0 | 519 | exact lower endpoint |
| B2 | 33 | 59.9083 | 60 | 88 | 110 | 0 | 457 | interpolated |
| B3 | 32 | 54.6796 | 55 | 73 | 93 | 0 | 520 | exact lower endpoint |
| B4 | 31 | 53.7295 | 53 | 78 | 107 | 0 | 0 | single |
| B5 | 33 | 52.4132 | 52 | 68 | 88 | 0 | 558 | clamped to 559 |
| C1 | 32 | 50.1512 | 50 | 60 | 75 | 0 | 203 | clamped to 204 |
| C2 | 32 | 46.4036 | 44 | 63 | 85 | 0 | 501 | exact lower endpoint |
| C3 | 32 | 49.0683 | 48 | 64 | 87 | 0 | 388 | exact lower endpoint |
| C4 | 36 | 54.2667 | 55 | 63 | 84 | 0 | 354 | exact lower endpoint |
| C5 | 36 | 54.2364 | 55 | 64 | 85 | 0 | 0 | single |
| C6 | 29 | 63.2718 | 68 | 82 | 101 | 0 | 0 | single |

The complete radiometric normalization also ran on all 16 surfaces. It
retained two previously documented evidence limits instead of silently
inventing calibration:

- the LRI contains no separate monochrome `sensor_data`, so A2 and C6 inherit
  the color-sensor black/white values 42/1023 and carry an explicit warning;
- B5 at Hall 558 and C1 at Hall 203 lie exactly one count below their first
  vignetting support points, 559 and 204. The implementation clamps each to
  that endpoint and marks the choice as not calibration-covered. The numerical
  extrapolation distance is tiny, but it remains unverified without a targeted
  calibration measurement.

The new diagnostics are not clean enough to call this an unqualified
control-path pass. The bounded all-16 log contains 19 `RDI SOF` timeout
messages, 49 failures to obtain a metadata buffer paired with 49 failures to
issue SOF to all modules, and two buffer-unmap failures. The two earlier A1
bundles cannot establish whether those diagnostics were absent: each retained
only 501 logcat lines, beginning 1.14--1.18 seconds after the timestamp encoded
in its generated LRI filename and therefore after the transfer/write window.
The capture nevertheless logs `All transfers done` immediately after the
last RDI timeout, writes the LRI, returns zero, stops session 2 successfully,
and closes camera ID 0 with `rc: 0`. There is no MIPI RX error, kernel fault,
process fatality, `light_ccb` transfer failure, or lost module in the decoded
artifact. The public analyzer intentionally reports `CONTROL_PATH_FAILED`
because real timeout/failure diagnostics are fail-closed; the artifact evidence
does not erase those messages.

The profile retained `normal_reboot_required=yes`. The host pulled and
verified the diagnostic directory and LRI before requesting the normal reboot.
At uptime 38.00 seconds after boot, `sys.boot_completed=1`, `media` and
`lightsvr` were running, `fwupgrade` was stopped, `manual_control=0`, no
`lcc` process remained, the trigger was zero, and all five argument
properties were empty. The normal Light camera application had reopened camera
ID 0 after boot; that new application client was not a surviving `lcc`
session. A second check at uptime 854.19 seconds found CameraService empty
again while both services, the zero manual gate, and all runner properties
remained clean.

## Full-window A1 comparison

The 2,000-line A1 profile was then run once on 2026-08-09. The retained bundle
is `output/a1-capture-20260809T201503Z/`. The wrapper returned `PASS` without a
reboot and copied one 16,566,521-byte LRI with matching device/host SHA-1
`6420a3596bffdd211a82bae6e3cd2262792800fd`. Schema decoding found eight
complete blocks with no unknown field or unused message bytes. The only fired
module was A1: 4160 x 3120 packed RAW10, 19,999,956 ns exposure, and analog and
digital gain 1.0.

The lossless raw decode and complete radiometric normalization also succeeded.
No sample was saturated. The initial 21,684-pixel defect mask grew to 48,090
pixels after the documented crosstalk-mask propagation, or 0.371% of the
surface; normalization emitted no calibration warning for A1.

The full capture window contains two `RDI SOF` timeout messages and the same
single synthetic-buffer unmap failure propagated through MCT, the pipeline,
and the HAL. It contains zero `mct_stream_get_metadata_buffer` failures and
zero paired `Failed to issue SOF cmd to all modules` messages. The A1 writer
logged three FDs totalling 16,566,521 bytes; its last FD appeared 96 ms after
`writeFile()` began, and normal metadata processing was visible two
milliseconds later. In the all-16 run, the equivalent 20-FD, 259,999,993-byte
write occupied about 1.144 seconds and its first metadata-buffer failure began
318 ms after `writeFile()` entered. This controlled size comparison supports
the decompiled call-path diagnosis: synchronous storage I/O blocks the result
callback long enough to exhaust the metadata pool only for the large all-16
artifact. It also shows that the unmap bookkeeping fault and RDI timeout
recovery are independent of that exhaustion.

The public analyzer remains deliberately fail-closed and therefore reports
`CONTROL_PATH_FAILED`; that verdict records the real timeout/unmap diagnostics
and is separate from the valid LRI framing and decoded pixels. The final live
health check, without another trigger or reboot, found completed boot, running
`media` and `lightsvr`, stopped `fwupgrade` and `fihop`, `manual_control=0`, no
`lcc` process, neutral runner properties, and an empty CameraService client
list.

The reconstructed buffer lifetime, the reason that smaller synchronous writes
would still block this callback, and an ownership-safe asynchronous patch
contract are documented in
[`async-lri-writer.md`](async-lri-writer.md). Its Python implementation remains
a host-only state-machine model. The narrower reversible preload integration
probe has now been exercised on the identified device; it is neither a modified
installed HAL nor the general producer-lease implementation specified there.

## Reversible asynchronous A1 integration result

The final bounded async A1 run completed on 2026-08-09 and is retained under
`output/a1-async-capture-20260809T220728Z/`. The wrapper returned `PASS`, `lcc`
returned zero, exactly one 16,566,521-byte LRI was copied with matching
device/host SHA-1 `008dc190d2a9a1e38615bcb5a73d4e342a1de3f8`, and every expected shim marker
occurred exactly once. Those markers prove target resolution, a filtered-child
preload self-test, one enqueue and worker, writer completion before the original
close path continued, seven successful factory helper commands, and clean
reporting. The current `lcc` output contains no 32/64-bit loader warning or
repeated interposition marker.

Schema decoding found eight complete blocks with no unknown fields or unused
message bytes. The only fired module was A1: packed RAW10 at 4160 x 3120,
19,999,956 ns exposure, and analog and digital gain 1.0. Complete radiometric
normalization used those exact values, emitted no warning, found no saturated
sample, and propagated the 21,684-pixel calibration defect mask to 48,090 pixels
after crosstalk correction (0.371% of the surface). The low-light result had an
SNR median of 2.1 and p10 of 0.3.

The conservative analyzer still reports `CONTROL_PATH_FAILED`: this A1 window
contains two `RDI SOF` timeouts and one buffer-unmap chain, matching the
independent diagnostics seen in the full-window unmodified A1 comparison. It
contains no metadata-pool failure, no paired `Failed to issue SOF cmd to all
modules` message, and none of the earlier preload/helper failures during the
00:07 capture interval. The retained logcat crash ring still includes one
`page record` line timestamped 23:58:50 from earlier loader testing; it predates
this LRI by more than eight minutes and is not present in the current `lcc`
stream. This is a successful fixed-profile integration and artifact result,
not an unqualified camera control-path pass.

The host removed the payload, arm file, and preload library, then requested the
profile's mandatory normal reboot. The post-boot check found build
`00WW_1_351`, completed boot, running `media` and `lightsvr`, stopped
`fwupgrade`, `manual_control=0`, neutral runner properties, no `lcc` process,
and no active CameraService client. No system or vendor partition file was
changed.

## Reversible asynchronous all-16 result

The bounded all-16 async run completed on 2026-08-10 and is retained under
`output/all16-async-capture-20260810T145618Z/`. The wrapper and all eleven shim
lifecycle gates returned `PASS`, `lcc` returned zero, and exactly one
259,999,993-byte LRI was copied with matching device/host SHA-1
`9fb56c01ad11cb3507bb091c89866f51e3fa0295` and local SHA-256
`05f97264fa505fab7c488ebc0f9ada1d73010e42d45ed0d8c771317d37dc6052`.
The current `lcc` output contains no preload, helper, worker, or close error.

Schema decoding found ten complete blocks with no unknown fields or unused
message bytes. All 16 expected RAW10 surfaces are present at 4160 x 3120; every
module records 19,999,956 ns exposure and analog/digital gain 1.0. The three
capture headers retain a common image ID and timestamp grouping. Complete
radiometric normalization processed all approximately 208 million samples and
found no saturated pixel.

A 2112 x 1732 contact sheet of all 16 normalized surfaces is retained as
`pixels/all16-async-normalized-per-module-stretch.png` (SHA-256
`4f4a804dabacc5d3c4862addb1718512b4df32a5ed20444cfcd288bf6a99e116`). Each
tile uses its own 0.5--99.5 percentile display stretch followed by a square-root
display curve, so it is useful for framing and focus inspection but deliberately
not a module-brightness or color comparison. Several B/C views are visibly soft
and C6 shows the strongest defocus/bokeh. This capture did not run autofocus:
the LRI reports `focus_achieved=false`, zero disparity and contrast focus
distances, and `LEGACY_UNKNOWN` as the AF trigger. Several stored lens positions
are also zero, while A5 is negative. The sheet is therefore a useful before-AF
baseline, not evidence that a lens or mirror actuator failed.

The controlled log comparison is the important result:

| Diagnostic | Synchronous all 16 | Async all 16 |
| --- | ---: | ---: |
| `mct_stream_get_metadata_buffer` failures | 49 | 0 |
| `Failed to issue SOF cmd to all modules` | 49 | 0 |
| `RDI SOF` timeouts | 19 | 19 |
| unmap-chain messages | 2 | 2 |

Moving the 260 MB write off the result callback therefore eliminates the two
metadata-exhaustion series while leaving the independent timeout and synthetic
buffer-unmap behavior unchanged. This is strong device confirmation of the
callback-stall diagnosis, not a complete control-path fix; the conservative
analyzer correctly continues to report `CONTROL_PATH_FAILED` for the remaining
errors.

Normalization identifies A2 and C6 as panchromatic and the other 14 modules as
Bayer color. It warns that A2/C6 lack sensor-type-specific black/white metadata,
which can only be resolved with a controlled dark frame. B3 and C3 also required
vignetting-grid clamping because their captured mirror Hall values (518 and
386) lay just outside the available approximately 520 and 388 support points.
These are calibration boundaries, not malformed pixel data.

The host removed the payload, arm file, and preload library before requesting
the mandatory reboot. Post-boot checks found the expected build, completed boot,
running `media` and `lightsvr`, stopped `fwupgrade`, `manual_control=0`, neutral
runner properties, and no `lcc` process. The only CameraService client observed
immediately afterward was the normal stock package `light.co.lightcamera`, not
a surviving factory session; a later check found no active client. No installed
HAL or partition was modified.

## Long exposures fail in `writeFile`, not on the completion timeout

The roughly six-second exposure ceiling is not a timeout. Raising LCC's
completion budget from 15 s to 180 s changes nothing about it. This section
records both the disproved hypothesis and the measurement that replaced it,
because the disassembly that motivated the hypothesis was correct and still
misled us.

### What `lcc` computes

`/system/etc/lcc` is not stripped and carries DWARF debug information, including
the original source path `light/lcc/lcc_cli_tool.c` from the 00WW-1.3.5.1 build.
The budget is derived in `wf_run_capture` at `0x2368`, and the store at `0x2830`
is exactly:

```text
exposure_s      = exposure_ns / 1e9
total_delay     = max_capture_delay + exposure_s
                  + single_burst_delay * (burst_cnt - 1)
thread_time_out = (uint32)total_delay + 1
```

The 1e9 divisor is a verified literal at `0x2a78`, and `lcc` prints its own
inputs one line earlier, so the arithmetic can be checked against any run: a 6 s
request logs `max_capture_delay: 0.100000` and `total_delay: 6.100000`, then
`Thread time out: 7`.

That value carries no readout term. Reading all sixteen modules takes about 14 s
-- measured from the 16-18 s spacing of six consecutive successful one-second
dark frames -- and whether one module or sixteen are read does not enter the
formula. The HAL then turns any value at or below 9 into a flat 15 s. So the
budget stays constant at 15 s across the entire range where the requirement
grows, which predicted the observed edge between 1 s and 6 s exactly.

### The measurement that disproved it

A 6 s all-16 capture was run with the combined preload, which patches the HAL's
timeout field to 180 s. 6 s was chosen deliberately: it is the first exposure
past the known edge, where the requirement is about 20 s and only the 15 s
budget should stand in the way. The patch applied -- the shim verified the field
against the formula before writing, logged `timeout_patched`, and the worker
completed with `worker_done_ok` -- and the capture still failed with
`Closed camera pipeline, 0` and a 32,790,777-byte LRI.

An earlier 8 s run at the stock budget produced 32,452,609 bytes. Twelve times
the completion budget produced no additional data.

### What actually fails

`logcat` from the 6 s run carries an error the earlier runs' logs never
surfaced:

```text
LccInterface::writeFile(): 439: Ion Fd: 98, size: 16228352
LccInterface::writeFile(): 443: mmap failed on ion fd: 98
```

Seventeen of twenty buffers fail to map. The two successful all-16 runs at 20 ms
contain zero such errors. The failure accounts for the file size exactly:

```text
2 x 16,228,352  module buffers that mapped
+      334,073  trailing buffer that mapped
=   32,790,777  bytes, the LRI on disk
```

So the LRI is not a truncated write. It contains, in full, everything that could
be mapped. The 16,228,352-byte buffer size times sixteen modules is 259,653,632,
consistent with the 259,999,993-byte complete frames.

The order matters: the first two buffers map, the next seventeen fail, and the
final 334,073-byte buffer maps again. All twenty log lines share the same one to
two milliseconds, so nothing expires while the file is being written -- the
state already existed. A 4,096-byte mapping failing while a later 334,073-byte
mapping succeeds also rules out address-space exhaustion.

The HAL code at `0x98a60` is unremarkable: `mmap(NULL, length, PROT_READ,
MAP_SHARED, fd, 0)` with a `munmap` earlier in the same loop, the descriptor
read from instance offset 16 and the length from offset 24. The descriptors are
open and the sizes are plausible. The most likely reading is that fourteen of
the sixteen modules never filled their buffers, and `writeFile` reports the
consequence rather than the cause.

`errno` would separate the remaining possibilities and the HAL does not print
it. That is the next measurement.

### The errno, and what it showed

The HAL prints the failing descriptor but not the reason, so the same preload
was rebuilt with an `mmap` interposer that forwards every call unchanged and
adds the errno. Eighteen failures, one answer:

```text
L16_ASYNC_SHIM mmap_failed fd=94 length=16228352 errno=9
```

`errno` 9 is `EBADF`. The descriptors are not merely unmappable, they are
closed. Not memory, not size, not permissions.

The marker order says who closed them. A successful all-16 run at 20 ms:

```text
enqueue_ok -> worker_start -> worker_done_ok -> close_wait -> close_continue
Closed camera pipeline, 1
```

The failing 6 s run:

```text
close_continue -> enqueue_ok -> worker_start
Closed camera pipeline, 0 -> dtor -> mmap_failed x18 -> worker_done_ok
```

In the failing run `closeCamera` is reached *before* `writeFile` starts. That
is why `close_wait` is absent: the preload joins the writer thread in
`closeCamera`, and at that moment no thread exists yet. `writeFile` then runs
on a worker alongside the teardown and maps descriptors the teardown has just
closed. The two or three buffers that get through are the ones that win the
race.

The ordering itself comes from `lcc`: `thread_time_out` is 7 s for a 6 s
exposure, and `lcc` proceeds to `closeCamera` on that schedule while
integration and readout are still running. The HAL's own budget, which the
timeout shim patches, is a different clock and does not govern this.

### The ceiling is ours

The control run settles it. Same capture, same 6 s, all sixteen modules, no
preload of any kind:

```text
Closed camera pipeline, 1
lri_output_size=259999993
```

A complete frame. Decoding it yields sixteen module surfaces at 4160x3120 with
real pixel data, A1 through C6.

There is no six-second exposure ceiling in the camera. Without a preload
`writeFile` stays on the callback and finishes before anything is torn down,
which is precisely what it did for every stock capture. The ceiling appears
only when the async writer moves that work onto a thread nobody waits for.

Every run that has ever shown the ceiling had the async writer loaded,
including the long dark series, whose payload sets `USE_ASYNC_SHIM=yes`
globally. That series aborted on capture 7 of 15 -- its first 6 s frame. Its
6 s and 29 s exposures were never attempted by the hardware. (The 29 s
request, when it was finally made, ran at a clamped 19.45 s.)

The 24-capture dark frame series is unaffected: every exposure in it is 20 ms
or shorter, far below where the ordering changes.

### Status

Explained. The exposure ceiling was an artefact of the async writer, not a
property of the camera.

The async writer is still worth having -- it was written against metadata
buffer exhaustion during the 1.1 s synchronous write of a 260 MB all-16
result, and it removes that failure class completely (49 `Invalid argument!!!`
to 0), at the cost of more `Bad fd for extra data` (184 to 227). Both counts
come from otherwise identical 20 ms all-16 runs. What it lacks is a case for
`writeFile` arriving after `closeCamera`, where going asynchronous is exactly
wrong and running on the callback is exactly right.

### The repair, and the measurement that confirms it

The writer now recognises the order. `closeCamera` records that it has been
entered, and a `writeFile` arriving afterwards runs inline on the callback
instead of on a worker -- which is what happens with no preload at all, and
what completes. The log says which path was taken: `write_after_close_inline`
instead of `enqueue_ok`.

A second fault only surfaced on hardware. `closeCamera` read the writer's
result *before* calling the real function, but with the order reversed the
inline write happens during that call. The seed value is 1, meaning "no write
happened", so a completed capture was reported as a failure: the first
repaired run logged `write_after_close_inline` correctly and still ended in
`Closed camera pipeline, 0`. The result is now read after the real call.

Confirmed at 6 s with all sixteen modules and the writer active:

```text
L16_ASYNC_SHIM write_after_close_inline
L16_ASYNC_SHIM close_reports_ok
Closed camera pipeline, 1
lri_output_size=259999993
```

The mock had to be sharpened before it could test any of this. It returned
from `closeCamera` before `writeFile` was ever called, so both paths wrote
after teardown and the distinction was invisible. It now fires the result
callback from inside `closeCamera` and completes the teardown afterwards, as
the HAL does, which separates the cases: an inline write lands before
teardown, a worker after it. Disabling the fix makes that test fail, which is
the only evidence that it tests anything.

### A 29 s request completes -- at 19.45 s

Correction. This section previously reported that 29 s captures work. The
capture completes, but not at 29 s. The exposure recorded in the file is
19,450,064,896 ns, and the request is clamped to it without any error: `lcc`
exits 0, the LRI is complete, and every log line looks like success.

The mistake was not reading the recorded exposure back. It was checked for the
6 s capture (6,000,159,744 ns, quantised as expected) and then assumed to hold
at 29 s. It does not, and nothing in the capture path says so. The three
shorter steps are accurate to better than 0.01%; only the longest is clamped:

```text
requested         recorded
100,000,000       99,999,776
1,000,000,000     999,927,744
6,000,000,000     6,000,159,744
29,000,000,000    19,450,064,896   <- clamped
```

Read the recorded exposure. It is in every file for exactly this reason.

What the run does establish, at 19.45 s, with all sixteen modules and the
writer active:

```text
max_exposure_f: 29.000000, single_burst_delay: 29.000000, total_delay: 29.100000
Thread time out: 30
Thread Timeout: 35
L16_ASYNC_SHIM write_after_close_inline
Closed camera pipeline, 1
lri_output_size=259999993
```

`Thread Timeout: 35` is the first observation of the HAL's other branch. Every
earlier capture kept `thread_time_out` at or below 9, where the formula yields
a constant 15; at 30 it yields `T + 5`. Both halves of
`(T > 9) ? T + 5 : 15` are now confirmed on hardware rather than read off a
disassembly.

Decoding the frame gives sixteen module surfaces with real data. The means
range from 44 to 372 DN, which is collected light rather than dark current --
the camera was not covered.

Where 19.45 s comes from is now the open question. It is not the 29 s the
firmware admits as a request, so those are two different limits, and this
project has been treating them as one.

Also established, independently of all this: the timeout field at instance
offset `0x24` is real, the formula predicting it holds on hardware, and it can
be patched safely. The shim verifies the field against the predicted value
before writing and refuses otherwise. It simply does not lift the ceiling,
because the ceiling was never its clock.
