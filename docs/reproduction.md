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
