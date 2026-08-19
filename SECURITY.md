# Security and device-safety policy

This project documents privileged and low-level interfaces on an unsupported
camera. A technically valid command can still hang camera services, corrupt
calibration data, or make the device fail to boot.

## Supported research target

The only confirmed target is LightOS 1.3.5.1 build `00WW_1_351` with kernel
`3.18.20-perf-g32d1d1c`. Stop on any identity or hash mismatch. Similar kernel
versions, permissive SELinux, or the presence of a service name do not establish
compatibility.

## Deliberate limits

- The root guide proves a bounded UID-0 runner. It does not install persistent
  root or expose an interactive root shell.
- Do not write an FFBM cookie to `misc`; a verified recovery path is absent.
- Do not use `camera_enable`, raw I2C/CCI/SPI writes, SPI `eeprom`, or SPI
  `firmware` as camera-control APIs.
- Do not execute recovered calibration, ASIC programming, or factory-init
  binaries.
- The enabled host wrapper is valid only for the exact checked identities and
  the compiled-in profiles documented in `docs/lcc-control.md`. Each profile
  fixes its own mask, exposure, gain and arm token, and is refused unless the
  payload and preload hashes match. Do not generalize it, add another
  executable, suppress a profile's required post-attempt normal reboot, or
  reuse it while a CameraService client exists.
- The wrapper has no dry-run mode. It arms and triggers a real capture before
  any host-side timeout can intervene, so an interrupted invocation still
  leaves a capture running on the device.
- The on-device apps are each narrower than the wrapper: one fixed profile,
  no arguments, and a hash-pinned copy of the exact payload they were built
  against. A root supervisor must reboot after every possible camera attempt
  because there is no independent host artifact pull. Do not remove the
  two-stage UI, one-install lock, script hashes, outer timeout, or reboot
  fallback. An app built before a payload change carries the older payload;
  rebuild it rather than assuming it matches this repository.
- Long exposures are bounded by the firmware at 29 s. Requesting more is
  rejected by the payload's own plan check rather than passed to the sensor.
- Never test on a device you do not own or administer with permission.

## Reporting a problem

Use the repository host's private security-advisory channel when a report
contains a working corruption or code-execution payload. A public issue is
appropriate for documentation errors, hash mismatches, non-destructive
reproductions, or fixes that remove risk. Do not attach proprietary images,
libraries, personal calibration data, or device identifiers.

There is no remaining vendor support channel known to this project. Publication
of a static defect should still separate code reachability from an executed
exploit and should include the exact build identity.
