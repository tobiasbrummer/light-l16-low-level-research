# Light L16 Camera2 meter/focus probe

This APK is a deliberately non-rooting precursor to the hostless raw capture.
It opens one Camera2 preview only after a deliberate tap, meters the center half
of the active sensor array, records the returned exposure time and sensitivity,
then starts center autofocus and records the terminal AF state. It always closes
the capture session, camera device, and background thread after PASS, failure,
or timeout.

It does not invoke `fihop`, `lcc`, `prog_app_p2`, manual-control sysfs, firmware,
or the hostless capture supervisor. It creates no LRI and does not reboot. The
purpose of the first device run is to establish whether the production L16
exposes the stock application's required preview/AE/AF path to a separately
installed Camera2 app.

The recovered stock `light_camera` ODEx confirms the same high-level ordering:
it installs a `CONTROL_AE_REGIONS` repeating preview request, reads
`SENSOR_EXPOSURE_TIME`, and then issues a one-shot request with
`CONTROL_AF_REGIONS` and `CONTROL_AF_TRIGGER_START`.

## Build and test

```sh
android/meter-focus-probe/build_debug_apk.sh
adb install -r .build/meter-focus-probe/light-l16-meter-focus-probe-debug.apk
```

Fully close the stock camera app first. Open **L16 Meter Focus Probe**, allow the
camera permission, point the camera at a textured subject, and tap the button
once. A useful result contains `metering=PASS`, nonzero
`sensor_exposure_time_ns`, and `focus=PASS`. `focus=NOT_FOCUSED_LOCKED` is also
a valid completed actuator transaction but means the selected scene did not
focus. Preserve the complete selectable report for every other outcome.
