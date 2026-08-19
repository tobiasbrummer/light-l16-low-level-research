# Confirmed results, in the order they were established

+doc:documentation +project:light-l16-low-level-research

This is the running record of what has been established on hardware, kept in
the order it happened rather than reorganised after the fact. It includes
attempts that failed and conclusions that were later corrected, because the
route to a result is part of the evidence for it.

For a current summary of what works, see the [README](../README.md). For the
reasoning behind each result, see the topic documents listed there.

## Results

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
- A first two-stage hostless Android capture app was implemented for exactly
  one A1 exposure at 20 ms and gain 1.0. It hash-pinned the existing payload,
  locked itself after one trigger, and normally rebooted after any possible
  camera attempt. That exact legacy APK completed its first live capture on
  2026-08-13: the resulting 16,566,521-byte LRI decodes without unknown fields
  as one A1 RAW10 surface at 4160 x 3120, 19,999,956 ns, and analog/digital
  gain 1.0. Pixel content is valid but the bright window scene clips 19.03 % of
  raw samples at the 1023 white level. The file alone does not independently
  prove that the requested post-capture Android reboot completed. The current
  APK replaces the failed Camera2-close handoff with the fixed A1 preload: it
  builds and embeds the ARM32 hook, verifies all three payloads at each staging
  boundary, and invokes only the same-session center-AF/A1 profile. Its first
  physical attempt validated delivery and all staging gates but stopped before
  HAL loading because Android 6 did not resolve `bind` through `RTLD_NEXT`; no
  AF or capture was released and cleanup settled. A corrected raw-CCB run then
  reached the active HAL session and sent the fixed AF request, but the LCC
  preview loop continued resetting AF to idle, the stream ended in a SOF
  freeze, and capture remained suppressed. Cleanup and the required reboot
  completed. The current host-tested revision therefore does not issue raw
  I2C/CCB AF: it interposes LCC's Camera3 request and result PLT calls, injects
  standard AF metadata into the active preview session, and releases capture
  only for `AF_STATE_FOCUSED_LOCKED`. This revision still needs its first
  physical L16 run.
- The checked-in A1 dry-run passed its live identity, service-state, binary,
  and cleanup checks without invoking `lcc` or issuing a capture request.
- Seven of the separately armed wrapper's eight compiled-in profiles use 20 ms
  and gain 1.0: normal A1, two fixed center-AF/A1 variants,
  reversible-async A1, plus
  normal and reversible-async variants of the factory-derived explicit
  all-module mask `FE FF 01`. A first live center-AF attempt safely stopped before
  actuation: the idle ASIC rejected the request with an I2C NACK, so no
  post-focus capture was started. A second attempt passed the statically
  recovered, hash-verified, non-flashing normal-mode reset of all three ASICs
  and the stock `01 00` readiness response. Its AF request reached the I2C
  bridge without a NACK but produced no interrupt within 20 seconds, so capture
  was again suppressed. The test had no active CameraService client; static
  analysis also shows that autofocus workflow 0 does not itself open the camera
  HAL, making a missing active sensor/preview state the leading hypothesis, not
  a proven cause. The current A1-only preload closes that gap at the Camera3
  layer: it arms from `startCapture()`, puts `AF_MODE_AUTO`, a fixed center ROI,
  and one `AF_TRIGGER_START` into LCC's next preview request, keeps later
  requests at `AF_TRIGGER_IDLE`, and waits for the matching result stream to
  report `AF_STATE_FOCUSED_LOCKED`. Its host mock proves release-on-lock and
  capture suppression plus direct HAL cleanup on `NOT_FOCUSED_LOCKED`; this
  metadata revision has now completed one physical A1 capture: its LRI records
  `focus_achieved=true`, center ROI, `lens_position=11376`, two nonzero focus
  distances, and no lens timeout, where the earlier transition LRIs recorded
  zero focus state and lens position. The eighth profile applies this gate to
  the still-unverified fixed A1-A5 mask `3E 00 00`. The wrapper bounds every
  executable with an outer timeout, requires the focused-lock marker, powers
  the ASICs down through a fixed cleanup branch,
  repeats `manual_control` cleanup, collects logs, and identifies the
  HAL-generated timestamped LRI without touching older files. Only a verified
  clean unmodified A1 return may remain up. Every reset, AF, shim, or all-16
  run, timeout or failure, and every ambiguous or incomplete artifact transfer
  requests a normal reboot.
- The seventh profile is a fixed single-request HDR experiment. It selects all 16
  modules once at gain 1.0 and assigns 1.25, 5, or 20 ms to each module in
  ascending module-bit order. Its argument construction, ordering, refusal
  behavior, and simulated host path are tested, but this exact exposure profile
  has not yet run on a camera and is not counted as a confirmed capture.
- A separate non-rooting HDR meter APK now opens a live Camera2 preview, uses
  the converged AE exposure/sensitivity as its starting point, and originally
  attempted a bounded ISO-100 `RAW_SENSOR` probe. Its first physical run proved
  the AE path but the advertised RAW request returned neither image nor result;
  cleanup completed without root/LCC. The current revision therefore samples
  eight continuous YUV preview frames, estimates highlight headroom and temporal
  shadow SNR, and distributes four Bayer exposures logarithmically between the
  measured endpoints. Its first YUV run completed and measured stable ISO-100
  shadows, but the base preview was 15.59 % clipped, so that revision could not
  resolve highlights. The current revision adds a standard `-2 EV` AE highlight
  phase and evaluates p99.9 against a matching 0.1 % clipping budget. It builds and
  is host-tested but still needs that physical run and paired-LRI calibration.
- A separate adaptive A-group pilot now connects that two-phase meter to the
  already exercised same-session A1-A5 focus path. It exposes no editable root
  parameters: after a stable, resolved measurement, a third button is valid for
  60 seconds and writes one canonical app-private A1-A5 plan. Java, the fixed
  root supervisor, and the fixed child independently require five decimal
  exposures in A1-A5 order, `A2 == A1`, a nondecreasing Bayer ladder, 10 us to
  20 ms bounds, mask `3E 00 00`, and gain 1.0. Camera2 is closed before the root
  trigger, the capture activity is not exported, payloads remain hash-pinned,
  and every possible camera attempt requests a reboot. The first physical
  attempt exposed a gate bug: a 42-ms/ISO-3200 scene produced 460-ms-to-1.344-s
  ideal ISO-100 endpoints, which the pilot cap collapsed to five equal 20-ms
  values. The camera rebooted without a visible new LRI, while the external
  report retained only pre-trigger progress. The revision now refuses equal
  A1/A5 or less than 0.5 EV pilot span and can expose the retained private
  supervisor result after `adb install -r` without re-entering the camera path.
  A later useful run produced an 81,484,025-byte LRI with exactly A1-A5 at the
  requested 6.360152/6.360152/10.099603/16.037664/20.000000-ms plan: measured
  metadata stays within 2,918 ns, both gains are 1.0, both headers report
  focused success, lens positions are nonzero without timeouts, all RAW10
  surfaces are nonconstant, and no protobuf field remains unknown. The
  external capture TXT nevertheless retained only pre-trigger progress, so the
  supervisor now mirrors its completed private manifest directly before its
  delayed reboot. Dynamic five-value submission is therefore physically
  verified; cross-module radiometry, panchromatic A2 response, and sub-1.25-ms
  LCC behavior remain unverified.
- The eighth profile is a fixed same-session A1-A5 focus experiment. It has no
  caller-controlled parameters, selects only `3E 00 00`, requires an exact
  Camera3 focused-lock result, requests five 20 ms/gain-1 RAW10 surfaces, and
  always reboots. Its first physical LRI contains exactly A1-A5 under one image
  ID and timestamp, with `focus_achieved=true`, five nonzero lens positions and
  no lens timeout. The outdoor 20-ms frame is 36.57-58.28 % saturated; it proves
  focused multi-module capture, not useful exposure selection. The matching
  A-group supervisor report also passes all packaged/staged hashes, focused-lock,
  LCC exit, cleanup, settled services/clients, LRI manifest, and normal-reboot
  checks.
- Two manual A1-only captures have completed on the identified device: first at
  2.61 ms and then at 20 ms, both at analog and digital gain 1.0. Both LRIs
  decode as exactly one A1 RAW10 surface at 4160 x 3120 with no unknown protobuf
  fields. The 20 ms run also verified the clean no-reboot path and continued
  normal camera-service state.
- One additional fixed A1 capture completed through the reversible asynchronous
  writer shim at 20 ms and gain 1.0. The exact ARM32 preload remained under
  `/data/local/tmp`; no installed HAL was replaced. All eleven lifecycle gates,
  including the seven factory helper commands and the writer/close join, passed.
  Its LRI again decodes as only A1 at 19,999,956 ns with analog and digital gain
  1.0 and no unknown protobuf fields. The mandatory reboot returned to the
  expected service, manual-control, process, and CameraService state.
- One explicit all-16 capture completed at 20 ms and gain 1.0. A single HAL
  request produced one 259,999,993-byte LRI containing 16 enabled RAW10
  surfaces in the expected 6 + 6 + 4 ASIC grouping. All three capture headers
  have the same image ID and timestamp, every module records 19,999,956 ns,
  and all approximately 208 million decoded samples are below saturation.
  New HAL timeout and metadata-buffer errors mean that the conservative public
  log analyzer still reports `CONTROL_PATH_FAILED`; the decoded artifact,
  clean teardown, mandatory reboot, and normal post-boot state are reported
  separately rather than hidden by that verdict.
- A second explicit all-16 capture completed through the reversible async
  writer shim with the same 259,999,993-byte layout and exact per-module
  exposure/gain metadata. Relative to the synchronous baseline, both sets of
  49 metadata-pool/failed-SOF messages disappeared completely. The independent
  19 RDI-SOF timeouts and two unmap messages remained unchanged. This is strong
  device evidence that synchronous LRI storage caused the metadata exhaustion,
  while the remaining control-path diagnostics have a different cause.
- The no-root stock Camera2 path has now completed one live same-session
  center-AE/AF capture through a third-party app: the on-device report displayed
  `result=PASS` after receiving and saving both format-48 LRI and JPEG buffers.
  The transferred 162,625,785-byte LRI matches the report SHA-256, parses to the
  exact end with no unknown protobuf fields, and contains the normal 28 mm A/B
  set: ten enabled 4160 x 3120 packed-RAW10 surfaces in two transfer blocks.
  Both headers record `focus_achieved=true` and `HW_SHORT_PRESS (6)`; every
  module has a non-zero lens position and no actuator timeout. Decoded pixels
  are non-constant, but module saturation ranges from 1.26 % to 12.70 % for
  this high-gain scene. The report proves the JPEG saver completed; that JPEG
  has not yet been transferred for independent hash/structure verification.
- A host-only analyzer conservatively separates wrapper failure, new camera or
  kernel diagnostics, incomplete evidence, and a control-path pass. It verifies
  the LRI transfer hash and public LELR framing but never upgrades that result
  to decoded, plausible pixels or a verified post-reboot state.

This repository claims the documented A1 captures, two explicit all-16
captures, and the decoded no-root stock-path A/B capture only for the exact
production build and fixed profiles documented here. It does not yet claim
that every arbitrary subset has been exercised, that the single-request HDR
profile has run successfully, nanosecond-level inter-sensor synchronization,
direct per-module focus or mirror control, or a general safe camera-control
API.
- A 24-capture all-16 dark frame series completed on 2026-08-18. It is the
  first profile here to issue more than one `lcc` capture per root session:
  the settle gate between captures held 23 times, cleanup verified, and a
  single reboot followed. All four requested integration times arrive
  unchanged, with 10 us landing on the sensor floor at 10,443 ns.
- `lcc -g` is applied **entirely as analog gain**. `sensor_digital_gain`
  stayed exactly 1.0 across all 24 captures while `sensor_analog_gain`
  reproduced 2.0, 3.75, 4.0, and 7.5 exactly; the 4.0 request was not rounded
  onto the neighbouring stock step. Read noise against gain fits
  `sigma^2 = (g*0.348 DN)^2 + (0.598 DN)^2` to within 2 %, which places the
  amplifier before the ADC: input-referred noise falls from 0.692 DN at gain 1
  to 0.357 DN at gain 7.5.
- At 10 us and gain 1.0 all sixteen modules read a black level between 41.81
  and 42.20 DN, a spread of 0.39 DN, with 0.66 to 0.92 DN of fixed pattern
  noise. Dark current is below the noise floor at 20 ms and room temperature
  and would need second-scale integrations to resolve.
- That series also disproved this repository's assumption about the RAW10
  pixel packing. It is a continuous little-endian bitstream, LSB first, not
  the byte-aligned MIPI CSI-2 layout. Only a flat dark field could reveal it;
  an ordinary photograph hides the difference in image content.

