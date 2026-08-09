# Light L16 module selection through the factory `lcc` tool

## Result and boundary

The LightOS 1.3.5.1 factory tool can express an arbitrary subset of the 16
camera modules. It accepts a module mask plus common or per-module exposure,
gain, resolution, and frame-rate values. The complete factory capture tuple is
also statically known.

This proves the userspace control interface. It does **not** prove that a manual
single-module capture has completed successfully on the examined production
camera. The repository therefore provides mask tooling and a camera-read-only
A1 preflight, but no enabled capture payload.

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

The relevant parameter options are `-e` for exposure, `-g` for gain, `-R` for
resolution, and `-F` for frame rate. Each option accepts either one common
value or one value per selected module. A first live test must reuse values
observed in an immediately preceding normal capture rather than inventing
settings.

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

For that reason, the first checked-in device payload is only
[`device/a1_capture_dry_run.sh`](../device/a1_capture_dry_run.sh). It verifies:

- UID 0 through the bounded `fihop` runner and cleared runner properties;
- the exact production build, completed normal boot, and known `lcc` identity;
- `manual_control=0`, a stopped `fwupgrade` service, and no active camera
  clients;
- the fixed A1 mask and factory tuple that a later wrapper would use.

It prints a plan containing placeholders for reference exposure, gain,
resolution, and FPS. It never copies or invokes `lcc`, never writes camera
sysfs, and has no execution option.

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
does not issue a camera-control request. Before adding an execution mode, the
remaining work is to capture trusted A1 reference parameters, specify timeout
and logging behavior, and define the post-failure normal-restart check.
