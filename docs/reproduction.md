# Reproducing the offline analysis

## Inputs and identity

Use only images and libraries obtained from a device or backup you are entitled
to examine. Place them in an ignored `inputs/` directory. The exact known hashes
and GNU build IDs are recorded in
[`artifacts/known-builds.json`](../artifacts/known-builds.json).

```bash
sha256sum inputs/kernel.raw \
  inputs/liblight_ccb.so \
  inputs/libmmcamera2_sensor_modules.so

readelf -n inputs/liblight_ccb.so
readelf -n inputs/libmmcamera2_sensor_modules.so
```

Do not continue a binary comparison after a hash mismatch. A different build is
new research evidence, not an interchangeable input.

## Recovering kernel symbols

The examined kernel contains a classic absolute ARM64 `kallsyms` address table.
The read-only candidate finder should return one validated long run:

```bash
python3 tools/kallsyms_probe.py inputs/kernel.raw \
  --base 0xffffffc000080000 \
  --span 0x4000000 \
  --minimum 1000 \
  --validated-only
```

Expected identity for the known kernel:

```text
offset=0x0116df00 count=134528 ... num_syms=match
```

[`vmlinux-to-elf`](https://github.com/marin-m/vmlinux-to-elf) can then recover
the full symbol list and create an ELF suitable for Ghidra:

```bash
kallsyms-finder inputs/kernel.raw > output/kernel.kallsyms
vmlinux-to-elf inputs/kernel.raw output/vmlinux.kallsyms.elf
```

The known result contains 134,528 symbols. Cross-checking addresses from an
independently saved `last_kmsg` against `dump_backtrace`, `dump_stack`, and
`do_one_initcall` provided a separate validation of the address mapping.

## Finding a global's ARM64 references

The narrow scanner recognizes common ADRP plus ADD/load/store patterns. For the
known `manual_control` address:

```bash
python3 tools/arm64_page_refs.py inputs/kernel.raw \
  --base 0xffffffc000080000 \
  --target 0xffffffc001e39428 \
  --kallsyms output/kernel.kallsyms
```

It should report the sysfs store, show, and two reads in
`msm_sensor_config32`. This scanner is intentionally not a general ARM64
disassembler; inspect the resulting functions in Ghidra.

## Ghidra workflow

The original analysis used Ghidra 12.1.2 and OpenJDK 21. Import the generated
ELF and allow normal ARM64 analysis. The scripts under `tools/ghidra/` support
targeted, reviewable reports:

```text
-postScript DumpFunctions.java msm_sensor_config msm_sensor_config32
-postScript DumpInstructions.java msm_sensor_config32 240 0x0
-postScript DumpReferences.java manual_control
-postScript DumpCallers.java @00011fe8
```

The last example uses the local `ioctl` PLT-thunk address in the known ARM32
`liblight_ccb.so`; addresses will differ in another binary. The `@address` form
matters because Ghidra's external import symbol may not own the code references,
while the local thunk does.

For the known 32-bit `/system/etc/lcc`, the following targeted reports
reproduce the distinction between `-C` response logging and `-R` resolution
configuration:

```text
-postScript DumpReferences.java pipe_fd
-postScript DumpFunctions.java wait_for_response wf_parse_capture wf_run_capture
-postScript DumpInstructions.java parse_commandline 330 0xa80
-postScript DumpInstructions.java wf_run_capture 56 0xa88
```

With Ghidra's `0x10000` image base, `pipe_fd` appears at `0x18284`; the ELF
symbol value is `0x8284`. The expected references are one parser write and
reads only inside `wait_for_response()`. The capture listing separately reads
`capture_cmd.resolution_len` at offset `0x98` before constructing command
`0x2E`. This cross-check prevents the similarly worded `--output` help and
`--channel` long option from being mistaken for a pixel-output control.
`wf_parse_capture()` also shows that ordinary workflow 1 fixes `n_burst` to one;
only the separate burst workflow parses a replacement value.

### Reproducing the per-module exposure order

In the same `lcc` import, inspect the `0x65` (`-e`) case in
`parse_commandline()`, the exposure-length checks in `wf_parse_capture()`, and
the `0x32` command construction in `wf_run_capture()`. The expected chain is:

```text
successive argv values -> exposure.data[0..15] as uint64_t
  -> one value or exactly selected-module count
  -> command 0x32, three-byte mask, successive eight-byte values
```

For the firmware-side cross-check, first require these exact identities:

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `system/etc/ASIC1.bin` | 489,444 | `a2ac9017b6f2b655a6c0988ae79fb7561dbde5b8d62d2c6b2e8abedf1da42f60` |
| `system/etc/ASIC2.bin` | 416,048 | `bfadf9080187d3da62fe92417adb72b04d3dbb915eb3d16cefdd16ae8cbc1ff6` |
| `system/etc/ASIC3.bin` | 416,048 | `76ae3e5d903c72fc360c764c541b1ffbe73274d6f687dd151f77577807e385c3` |

The raw images contain Thumb code and need the code/rodata mappings appropriate
to this firmware rather than an automatic file-type guess. In the analyzed
mapping, dump the module-set iterator initializer, module-attribute handler,
and iterator increment helper:

```text
-postScript DumpFunctions.java @0x361c @0x6898 @0x61c94
```

The expected result is that `0x361c` scans upward from the supplied bit until
the mask contains it, `0x61c94` invokes that scan at current bit plus one, and
the multi-value branch of `0x6898` advances its payload offset by eight bytes
for every selected module. The handler and initializer code bytes match in all
three identified images; the increment helper address above is from the
analyzed ASIC1 mapping. Together with the `lcc` serializer, this establishes
ascending selected-module-bit order. For `FE FF 01`, that is A1 through C6;
the 6 + 6 + 4 ASIC grouping seen later in an LRI is not the command order.

For the exact production `/system/etc/prog_app_p2`, first require the identity
recorded in `artifacts/known-builds.json`: 159,664 bytes, SHA-256
`0ccbf4f9ac820e49ff99293d06279cc36889ca1f9cc3f733fd50317265ed133a`, and
SHA-1 `d6d74641759f2e208beac4318507ea1b71923db4`. It is an unstripped ARM32 EABI5
binary, so the relevant symbols can be inspected directly:

```text
-postScript DumpFunctions.java main config_strappin reset_asics power_off_asics
```

The expected control-flow check is that option `-q` calls
`config_strappin(normal)` followed by `reset_asics()` and returns before
configuration parsing, SPI, erase, write, calibration, or firmware-programming
paths. Option `-F` calls only `power_off_asics()`. These observations justify
the wrapper's narrow reset and cleanup calls; they do not make other options of
the vendor flashing utility safe.

For the matching 32-bit `/system/lib/hw/camera.msm8996.so`, verify its identity
against `artifacts/known-builds.json`, import it as ARM little-endian, and use:

```text
-postScript DumpFunctions.java @0x96880 @0x9697c @0x9721c
-postScript DumpFunctions.java @0x97724 @0x97af0 @0x97d1c
-postScript DumpFunctions.java @0x98290 @0x98644 @0x98ce4
```

Those ELF virtual addresses identify `startCapture`, `prepareCaptureRequest`,
`generateFileName`, the constructor, `closeCamera`, `openCamera`,
`reqThreadRun`, `writeFile`, and `processCaptureResult` respectively. In this
HAL import Ghidra preserves those ELF addresses; do not add the `0x10000` base
used by the separate PIE `lcc` project.

The expected cross-check is: `startCapture` sets the request-thread flag;
`reqThreadRun` submits the special request; `processCaptureResult` recognizes
stream format `0x30` and calls `writeFile`; and the writer maps every returned
file descriptor read-only and writes its declared length. The filename pieces
in `.rodata` resolve to `/sdcard/DCIM/camera/`, `RDI_`,
`%Y%m%d_%H%M%S`, `_%03ld`, and `.lri`. `closeCamera` waits on the result
condition before closing, bounded by its configured timeout.

The ownership analysis behind the asynchronous-writer design can be reproduced
from the same HAL import with these narrower groups:

```text
-postScript DumpFunctions.java @0x92128 @0x92260 @0x9231c @0x92370
-postScript DumpFunctions.java @0x92a7c @0x92bf4 @0x9337c @0x933cc @0x93554
-postScript DumpFunctions.java @0x946a8 @0x95730
-postScript DumpFunctions.java @0x965f8 @0x96830 @0x96a90 @0x98644 @0x98ce4
-postScript DumpCallers.java @0x95730 @0x92bf4
```

The expected relationships are ownership transfers rather than copies:
`releaseBufferList()` splices the channel lists, `checkStartTransfer()` builds
the FD/length descriptor and calls the result path synchronously, and only
after that callback returns does it move the owning list into a
`MultiBufferAllocation`. `checkBuffersFreed()` requires `isFree()` before
moving those buffers into its reuse cache. `isFree()` compares the mapped first
eight bytes with `0x89abcdef` followed by `0x01234567`; the matching exported
object is named `MultiBufferAllocation::FREE_MARKER` in the symbol table.

Finally, verify the negative observation at the narrowest justified scope:
`writeFile()` maps the listed payload FDs read-only, and neither it nor
`processCaptureResult()` stores the release marker. This establishes the
identified LCC persistence path only. It does not prove that every other HAL
consumer or future build follows the same release protocol. See
[`async-lri-writer.md`](async-lri-writer.md) for the resulting lease boundary.

## Reproducing the ARM32 preload probe

The repository contains only the clean-room C source and build script, not the
generated shared object. Use Clang plus LLD and place the output outside the
repository:

```bash
L16_LLD=/absolute/path/to/ld.lld \
  host/build_lcc_async_shim.sh \
  /absolute/output/liblcc_async_writer_shim.so
```

The reviewed build used Ubuntu Clang and LLD 20.1.8. With those versions, the
expected output is 8,904 bytes, SHA-1
`150e53a736624010dc7fb741490ea8dca7afbfb8`, and SHA-256
`bbc6865374dfd7beb72d4a1cc30fad81414c6915052eb22e35c5205574ae9cb5`.
The device supervisor accepts only that exact size and SHA-1. Different
toolchain output must be audited and deliberately updated rather than accepted
through an override.

Static inspection should show an ELF32 ARM EABI5 DSO, only the two intended
mangled method exports plus the bounded `system` wrapper, the documented
Bionic imports, SysV hashing, RELRO/NOW, and a non-executable stack. The native
host mock exercises symbol preemption,
callback return, worker execution, and the close/join ordering:

```bash
.venv/bin/python -m pytest -q tests/test_lcc_async_shim.py
```

The separate fixed A1 same-session focus gate is built the same way:

```bash
L16_LLD=/absolute/path/to/ld.lld \
  host/build_lcc_a1_focus_capture_shim.sh \
  /absolute/output/liblcc_a1_focus_capture_shim.so
```

The pinned Clang/LLD build is 13,764 bytes, SHA-1
`67647b71767ab2b68a214fae87578e24eb3433b2`, and SHA-256
`72d1d05a6966cafbf92b7b5b45b82243d24da1a35a18b734097196357dc59ad6`.
It exports the start/close gate plus the Camera3 request/result interposers and
the bounded `system` wrapper. Its native focused-lock and fail-closed tests are:

```bash
.venv/bin/python -m pytest -q tests/test_lcc_a1_focus_capture_shim.py
```

## Qualcomm comparison

Use the public sources from commit
`e1e85fa160463d8c5e55c58c1806668e9740a117`:

- [`msm_sensor_driver.c`](https://android.googlesource.com/kernel/msm/+/e1e85fa160463d8c5e55c58c1806668e9740a117/drivers/media/platform/msm/camera_v2/sensor/msm_sensor_driver.c)
- [`msm_sensor.c`](https://android.googlesource.com/kernel/msm/+/e1e85fa160463d8c5e55c58c1806668e9740a117/drivers/media/platform/msm/camera_v2/sensor/msm_sensor.c)
- [`msm_cam_sensor.h`](https://android.googlesource.com/kernel/msm/+/e1e85fa160463d8c5e55c58c1806668e9740a117/include/uapi/media/msm_cam_sensor.h)
- [`msm_cam_sensor_compat.h`](https://android.googlesource.com/kernel/msm/+/e1e85fa160463d8c5e55c58c1806668e9740a117/drivers/media/platform/msm/camera_v2/sensor/msm_cam_sensor_compat.h)

Do not copy those GPL-2.0-only source files into an MIT-only clean-room bundle.
They are reference inputs and remain available under their upstream license.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

The suite uses synthetic inputs. It neither needs nor reads proprietary files.
