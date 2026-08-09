# Light L16 module selection through the factory `lcc` tool

## Result and boundary

The LightOS 1.3.5.1 factory tool can express an arbitrary subset of the 16
camera modules. It accepts a module mask plus common or per-module exposure,
gain, resolution, and frame-rate values. The complete factory capture tuple is
also statically known.

This proves the userspace control interface. It does **not** prove that a manual
single-module capture has completed successfully on the examined production
camera. The repository provides mask tooling, a camera-read-only A1 preflight,
a tightly fixed one-shot execution wrapper, and a conservative host-side log
analyzer. Static analysis now also identifies the HAL's automatic LRI writer;
the execution wrapper has not yet been run on the camera.

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
It remains static evidence until the first live run produces a file.

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
best-supported A1 input is therefore gain 1.0 and exposure 2,609,592 ns.

No capture FPS is stored in this LRI, and `sensor_scan_speed` is absent. A
Camera2 preview rate would describe a different path and is not a justified
substitute. Because `-F` is optional, the first candidate command deliberately
omits it:

```text
<lcc-copy> -m 0 -s 0 -f 1 02 00 00 11 F1 00 -R 4160,3120 -e 2609592 -g 1.0
```

This remains a statically and metadata-derived candidate. It has not been
executed on the camera.

The first execution deliberately omits `-C`: its small CCB-response files add
no pixel evidence and the recovered factory MIPI test does not use it. The HAL
is nevertheless expected to write the timestamped LRI above. The first hardware
test can therefore capture the control-path diagnostics and the generated LRI
in the same bounded attempt. Container framing and transfer integrity still do
not establish that the file contains exactly A1 or plausible raw samples.

## Why the first live call needs a wrapper

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
- the fixed A1 mask, factory tuple, and reference parameters that a later
  wrapper would use.

It prints the concrete plan above. It never copies or invokes `lcc`, never
writes camera sysfs, and has no execution option.

The separately named [`device/a1_capture_once.sh`](../device/a1_capture_once.sh)
is the enabled wrapper. It is intentionally unsuitable for arbitrary commands
or parameters. Before it can reach `lcc`, it requires all of the following:

- the exact one-use arming value
  `A1_CAPTURE_2609592NS_GAIN_1.0_ONCE`, which it immediately deletes;
- UID 0 through the self-clearing `fihop` runner and the exact known build,
  kernel, SELinux, ASIC firmware, `lcc` identity, and camera-HAL identity;
- normal boot with `media` and `lightsvr` running, `ro.light.aos=1`, no special
  LCC mode, stopped `fwupgrade`, and no existing `lcc` process;
- `manual_control=0`, no active CameraService client, UDP port 5000 unused, and
  at least 256 MiB free under `/data`.

It then makes a fresh, hash-verified executable copy of `/system/etc/lcc` in a
PID-specific root-owned directory and runs only the fixed A1 command through
Toybox `timeout`: TERM after 30 seconds, KILL after five more seconds. The
still-running root supervisor immediately writes `manual_control=0` again,
checks that no `lcc` process or CameraService client remains, captures bounded
before/after logs, and deletes the executable copy. It does not run
`prog_app_p2`, reset an ASIC, start `fwupgrade`, touch a block device, or invoke
raw focus, mirror, firmware, or calibration controls.

Before invoking `lcc`, the wrapper snapshots existing HAL-generated
`RDI_*.lri` paths without changing them. After `lcc` returns and immediate
cleanup passes, it requires exactly one new timestamp-shaped path, records its
size and SHA-1, and leaves the device copy intact. The host pulls that file to
the capture bundle before requesting the mandatory reboot and verifies the
same size and SHA-1 locally. An absent or ambiguous new artifact prevents a
`PASS` result.

Because a timeout can kill `lcc` before its own `close_camera`, the wrapper
marks a normal reboot as mandatory after every attempt that reaches `lcc`, even
if `lcc` exits zero and immediate cleanup appears healthy. It does not reboot
itself: logs must be made readable and pulled first.

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
host/run_a1_capture_once.sh --execute-fixed-a1-once-and-reboot
```

The host side requires exactly one authorized ADB device and rejects it unless
build, model, and product identifiers match the examined L16. It then pushes
and hashes the payload, creates the one-use arm file, verifies all six `fihop`
properties before triggering once, and polls for a completed result for at most
90 seconds. Its exit trap clears all six properties. It pulls the result and
diagnostic directory under `output/a1-capture-<UTC>/` and requests a normal
`adb reboot` whenever the device reports `capture_attempted=yes` or no complete
result is available. A preflight failure before `lcc` does not cause an
automatic reboot. When the device reports one new HAL-generated LRI, the host
also pulls it under `pixels/`, verifies its byte count and SHA-1 against the
device result, and deliberately leaves the original file on the camera.

The pulled bundle can then be classified locally without reconnecting to the
camera:

```bash
python3 tools/analyze_a1_capture.py output/a1-capture-<UTC>
```

The analyzer checks the completed wrapper result, immediate cleanup state,
CameraService client list, positive `lcc` lifecycle messages, newly added
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
normal-boot checks below, nor does it decode the LightHeader to prove that only
A1 fired or test whether its raw samples are plausible.

After the camera returns, verify the normal-boot postcondition before opening
the camera application:

```bash
adb shell 'getprop sys.boot_completed; getprop ro.bootmode; getprop init.svc.media; getprop init.svc.lightsvr'
adb shell 'cat /sys/class/light_ccb/common/manual_control; /system/bin/toybox pgrep -x lcc; true'
adb shell 'for p in persist.sys.fihop persist.sys.fihop1 persist.sys.fihop2 persist.sys.fihop3 persist.sys.fihop4 persist.sys.fihop5; do printf "%s=%s\n" "$p" "$(getprop "$p")"; done'
```

Expected: boot completed `1`, boot mode `unknown`, both services `running`,
`manual_control mode is 0x0`, no `lcc` PID, trigger `0`, and five empty argument
properties. If ADB disappears before the host can request its reboot, do not
retrigger `fihop`; perform one normal hardware restart instead.

`final_status=PASS` has a deliberately narrow meaning: the exact `lcc` process
returned zero, exactly one new HAL LRI was found and hashed, and the gate and
process checks passed. The host additionally verifies the copied bytes before
requesting the planned reboot. This is still not proof that A1 delivered valid
pixels: the LRI's decoded module list, exposure metadata, dimensions, raw
format, and sample statistics must be checked separately after the camera has
rebooted normally.

## Confirmed device-side wrapper syntax

The exact 14,338-byte `device/a1_capture_once.sh` from commit `7a10811` was
copied to a uniquely named temporary file on the identified production L16 on
2026-08-09. Its host and device SHA-1 values both were:

```text
4cb888e6470f9c5a052fbc74f4276608c831b1e4
```

The device's `/system/bin/sh -n` returned zero. The temporary file was then
removed and its absence verified. A final read-only state check reported
`persist.sys.fihop=0`, `manual_control mode is 0x0`, and no `lcc` process. This
validated parsing only: the payload itself, the root runner, `lcc`, the camera
HAL, and the capture path were not executed.

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
