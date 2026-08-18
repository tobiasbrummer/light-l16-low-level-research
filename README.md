# Light L16 low-level research

Clean-room documentation and reproducible host tools for the Light L16 camera,
focused on the LightOS 1.3.5.1 kernel camera extensions and the vendor-provided
temporary root runner.

## Status

The following results are confirmed for one production Light L16 running build
`00WW_1_351` / LightOS 1.3.5.1:

- Light extends Qualcomm's MSM8996 sensor driver with private 32-bit compat
  commands 30 and 31 for sequential CCB I2C transfers.
- The exact private transfer layout is 12 bytes, and the compat ioctl value is
  `0xc0a856c1`.
- The examined `liblight_ccb.so` uses command 30 for normal CCB writes. Its
  replies arrive through ASIC interrupts, a V4L2 event, and localhost UDP.
- `manual_control` suppresses automatic HAL CCB transfers; it is not a camera
  module selector.
- A vendor init service named `fihop` was used to run a fixed-purpose script as
  UID 0 in the normal Android boot. This was verified without flashing,
  changing a partition, or installing persistent root.
- The checked-in A1 dry-run passed its live identity, service-state, binary,
  and cleanup checks without invoking `lcc` or issuing a capture request.
- A separately armed wrapper exposes only two compiled-in 20 ms, gain-1.0
  profiles: A1 and the factory-derived explicit all-module mask `FE FF 01`.
  It bounds `lcc` with an outer timeout, repeats `manual_control` cleanup,
  collects logs, removes its temporary executable, and identifies the
  HAL-generated timestamped LRI without touching older files. Only a verified
  clean A1 return may remain up. Every all-16 run, timeout, or failure,
  and every ambiguous or incomplete artifact transfer requests a normal reboot.
- Two manual A1-only captures have completed on the identified device: first at
  2.61 ms and then at 20 ms, both at analog and digital gain 1.0. Both LRIs
  decode as exactly one A1 RAW10 surface at 4160 x 3120 with no unknown protobuf
  fields. The 20 ms run also verified the clean no-reboot path and continued
  normal camera-service state.
- One explicit all-16 capture completed at 20 ms and gain 1.0. A single HAL
  request produced one 259,999,993-byte LRI containing 16 enabled RAW10
  surfaces in the expected 6 + 6 + 4 ASIC grouping. All three capture headers
  have the same image ID and timestamp, every module records 19,999,956 ns,
  and all approximately 208 million decoded samples are below saturation.
  New HAL timeout and metadata-buffer errors mean that the conservative public
  log analyzer still reports `CONTROL_PATH_FAILED`; the decoded artifact,
  clean teardown, mandatory reboot, and normal post-boot state are reported
  separately rather than hidden by that verdict.
- A host-only analyzer conservatively separates wrapper failure, new camera or
  kernel diagnostics, incomplete evidence, and a control-path pass. It verifies
  the LRI transfer hash and public LELR framing but never upgrades that result
  to decoded, plausible pixels or a verified post-reboot state.

This repository claims the documented A1 captures and one explicit all-16
capture only for the exact production build and fixed profiles documented
here. It does not yet claim that every arbitrary subset has been exercised,
nanosecond-level inter-sensor synchronization, direct focus or mirror control,
or a general safe camera-control API.
- A 24-capture all-16 dark frame series completed on 2026-08-18. It is the
  first profile here to issue more than one `lcc` capture per root session:
  a settle gate between captures replaced the reboot-after-every-attempt
  policy and held 23 times, cleanup verified, and a single reboot followed.
  All four requested integration times arrive unchanged, with 10 us landing on
  the sensor floor at 10,443 ns.
- `lcc -g` is applied entirely as analog gain. `sensor_digital_gain` stayed
  exactly 1.0 across all 24 captures while `sensor_analog_gain` reproduced
  2.0, 3.75, 4.0, and 7.5 exactly, so an arbitrary request is not rounded onto
  a neighbouring step with a digital remainder. Read noise against gain fits
  `sigma^2 = (g*0.348 DN)^2 + (0.598 DN)^2` to within 2 %, placing the
  amplifier before the ADC: input-referred noise falls from 0.692 DN at gain 1
  to 0.357 DN at gain 7.5, which is 91 % of the achievable gain already at 4.
- At 10 us and gain 1.0 all sixteen modules read a black level between 41.81
  and 42.20 DN, a spread of 0.39 DN, with 0.66 to 0.92 DN of fixed pattern
  noise. Dark current stays below the noise floor at 20 ms and room
  temperature; resolving it needs second-scale integrations.
- The same series disproved this repository's assumption about the RAW10 pixel
  packing. It is a continuous little-endian bitstream, LSB first, not the
  byte-aligned MIPI CSI-2 layout. Only a flat dark field could reveal it,
  because an ordinary photograph hides the difference in image content.

## Documentation

- [Private driver ABI and data flow](docs/driver-abi.md)
- [Factory module selection, A1/all-16 tests, and bounded one-shot wrapper](docs/lcc-control.md)
- [Temporary root runner](docs/temporary-root.md)
- [All-16 dark frame series](docs/dark-frame-series.md)
- [Hostless all-16 dark frame series app](android/dark-frame-series/README.md)
- [Reproducing the offline analysis](docs/reproduction.md)
- [Security policy and device-safety boundary](SECURITY.md)
- [Contributors and AI-assistance disclosure](CONTRIBUTORS.md)

## Authorship and AI assistance

Tobias Brummer directed the research, supplied and controlled the examined
device and artifacts, made the safety and publication decisions, and maintains
this repository. OpenAI Codex provided substantial AI assistance with the
analysis workflow, binary cross-checks, documentation, clean-room interface
definitions, scripts, tests, and release preparation.

The technical claims were checked against identified local artifacts,
instruction listings, hashes, and reproducible tests. AI assistance does not
imply endorsement of this project by OpenAI. See
[`CONTRIBUTORS.md`](CONTRIBUTORS.md) for the detailed attribution boundary.

## Repository boundary

This repository contains only original documentation, clean-room interface
definitions, small analysis scripts, tests, hashes, and factual identifiers.
It intentionally contains no:

- LightOS update packages, kernel images, partition dumps, APKs, or vendor
  shared libraries;
- recovered factory executables or firmware;
- Ghidra databases, decompiler output, or long verbatim source excerpts;
- exploit binary, persistent `su`, patched boot image, or generic root shell.

Owners reproduce the analysis with files obtained from their own devices or
lawfully held backups.

## Host tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

The tests operate on synthetic byte strings and compile the clean-room ABI
header. They do not connect to a camera.

## Public context

The [Light-L16-Archive](https://github.com/helloavo/Light-L16-Archive) preserves
firmware, applications, and community material. The
[openlight-camera](https://github.com/ookami125/openlight-camera) project works
on the extracted Android camera application. As of 2026-08-09, searches for the
exact driver symbols and compatible string documented here did not find a
published Light-specific kernel tree or `light_ccb_spi.c` implementation.

The Qualcomm comparison source is the public MSM kernel commit
[`e1e85fa160463d8c5e55c58c1806668e9740a117`](https://android.googlesource.com/kernel/msm/+/e1e85fa160463d8c5e55c58c1806668e9740a117/).

## License

The original material in this repository is available under the MIT License.
Light, Light L16, Qualcomm, and other names may be trademarks of their
respective owners. The license does not apply to vendor software or data that
is not included here.
