# Light L16 low-level research

Clean-room documentation and reproducible host tools for the Light L16 camera,
covering the LightOS 1.3.5.1 kernel camera extensions, the factory capture tool
`lcc`, and the vendor's own temporary root runner.

The practical result is that a stock, unflashed L16 can be made to take a raw
capture from all sixteen modules at once, at a chosen exposure and gain, and
write it as a single 260 MB LRI you can decode offline.

Everything here targets exactly one build. Nothing is flashed, no partition is
written, and no persistent root is installed.

## What is confirmed on hardware

| | |
|---|---|
| Exposure range | 10,443 ns (sensor floor) to 29 s, all sixteen modules |
| Exposure accuracy | Quantised to row time: 6 s is recorded as 6,000,159,744 ns |
| Modules | A1-A5, B1-B5, C1-C6 in one request, mask `FE FF 01` |
| Full frame | 259,999,993 bytes, sixteen RAW10 surfaces at 4160 x 3120 |
| Gain | `-g` is analog only, no digital remainder, no rounding up to 4.0 |
| Black level | 42 DN across all sixteen modules, within 0.39 DN |
| Read noise | 0.68 DN at gain 1 |
| Amplifier | Before the ADC: `variance = (g * 0.348 DN)^2 + (0.598 DN)^2`, error under 2 % |

Each capture records the exposure and gain it actually used, so the
quantisation is visible per file rather than assumed.

The 29 s ceiling is the firmware's, not the sensor's. There is no exposure
limit around six seconds -- that was an artefact of this project's own
asynchronous LRI writer, which is [documented in
detail](docs/lcc-control.md#long-exposures-fail-in-writefile-not-on-the-completion-timeout)
because the wrong explanation survived several rounds of plausible evidence.

## Before you run anything

Read [SECURITY.md](SECURITY.md) first. In short:

- The only verified target is LightOS 1.3.5.1, build `00WW_1_351`, kernel
  `3.18.20-perf-g32d1d1c`. Every tool stops on an identity or hash mismatch.
  A similar kernel version is not compatibility.
- Every capture profile reboots the camera afterwards, on purpose. Expect to
  reset USB to file transfer on the device after each run to get `adb` back.
- The wrapper triggers a real capture. There is no dry-run mode.
- Nothing is written to `misc`, no partition is modified, and the temporary
  root runner is the vendor's own service, used for a fixed script and cleared
  afterwards.

## Requirements

- Linux with `adb`
- `clang` with an `armv7a-linux-androideabi23` target and `ld.lld`, to build
  the preload from source
- Python 3.11+ for the offline analysis (`requirements-analysis.txt`)
- No Android SDK, unless you want to build the optional on-device apps

## Getting started

Build the preload the capture profiles use, then run one capture:

```sh
sh host/build_lcc_async_shim.sh /absolute/path/liblcc_async_writer_shim.so

LIGHT_L16_ASYNC_SHIM=/absolute/path/liblcc_async_writer_shim.so \
  ./host/run_a1_capture_once.sh --execute-fixed-all16-async-shim-20ms-once-and-reboot
```

Run it with no arguments to see all fifteen profiles. Each writes its logs,
device state before and after, and the captured LRI under `output/`.

To check a run end to end -- device state, camera stack errors, container
framing and cleanup:

```sh
python -m tools.analyze_a1_capture output/<run>
```

To reduce captured frames to per-module statistics, pass the directory holding
them:

```sh
python -m tools.analyze_dark_frame_series output/<run>/pixels
```

## Documentation

- [Private driver ABI and data flow](docs/driver-abi.md)
- [Factory module selection, A1/all-16 tests, and bounded one-shot wrapper](docs/lcc-control.md)
- [Fixed single-request HDR capture profile](docs/single-shot-hdr.md)
- [Ownership-safe asynchronous LRI writer design and host model](docs/async-lri-writer.md)
- [Temporary root runner](docs/temporary-root.md)
- [Hostless Android root-runner probe](android/root-runner-probe/README.md)
- [Non-rooting Camera2 metering/focus probe](android/meter-focus-probe/README.md)
- [Non-rooting Camera2 RAW HDR meter](android/hdr-meter-probe/README.md)
- [Adaptive measured A1-A5 HDR capture pilot](android/adaptive-a-group-capture/README.md)
- [Hostless fixed A1 capture app](android/a1-capture/README.md)
- [No-root same-session stock-path LRI capture](android/stock-lri-capture/README.md)
- [Recovered stock Camera2 path to a focused LRI](docs/stock-camera-path.md)
- [Stock zoom, stacking, and module-group reconstruction](docs/stock-app-control.md)
- [All-16 dark frame series](docs/dark-frame-series.md)
- [Confirmed results in the order they were established](docs/results-history.md)
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
