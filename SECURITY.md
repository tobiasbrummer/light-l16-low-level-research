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
- The enabled wrapper is valid only for the exact checked identities and its
  two fixed A1/all-16 profiles. Do not generalize it, add `prog_app_p2`,
  suppress a profile's required post-attempt normal reboot, or reuse it while
  a CameraService client exists.
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
