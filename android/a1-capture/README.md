# Light L16 hostless same-session A1 focus capture

This app packages the fixed same-session A1 autofocus prototype so the live
capture no longer needs an ADB-connected host. A computer is needed once to
install the APK. After that, the read-only preflight and the single armed
capture run from the L16 display.

This remains a deliberately narrow experiment, not a general camera controller
or root shell. The only compiled-in profile is:

- module `A1` only (`02 00 00`);
- fixed center-half AF ROI `1040,780,2080,1560`;
- one `4160 x 3120` RAW10 surface;
- exposure `20,000,000 ns` and gain `1.0`;
- exactly one attempt per fresh app installation;
- a normal Android reboot after every possible camera attempt.

The app itself requests no Android permission and does not open Camera2. Its
second tap stages three packaged, hash-pinned payloads: the root supervisor,
the eight-profile child script, and the generated ARM32 A1 focus preload. The
supervisor invokes only the child's fixed
`A1_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE` installed path.

`lcc` opens the camera HAL and starts its preview request thread. At the fixed
`startCapture()` boundary, the preload arms an AF gate. It interposes LCC's next
Camera3 preview request, clones its settings, and adds `AF_MODE_AUTO`, the
center region `[1040,780,3120,2340,1000]`, and exactly one
`AF_TRIGGER_START`. Later requests keep the same mode and ROI with
`AF_TRIGGER_IDLE`. Only a result at or after the trigger frame with
`AF_STATE_FOCUSED_LOCKED` releases the real capture. A five-second timeout,
`NOT_FOCUSED_LOCKED`, malformed metadata, duplicate start, or HAL request error
suppresses capture and takes the bounded direct-HAL cleanup path. The preload
does not send a raw CCB/I2C focus command.

The measured focus is therefore in the same HAL session as the RAW capture. It
does not rely on the disproven Camera2-focus/close/`lcc` handoff, which produced
`lens_position=0` in the resulting LRI.

## Safety and recovery policy

The first button only checks the exact known production build, normal boot,
SELinux state, idle root runner, vendor runner hash, and all three packaged
payload hashes. It reports `camera_not_touched=yes` and arms the second button
for 60 seconds.

Before triggering root, the app writes a persistent one-install lock. It cannot
silently retry an ambiguous operation. The root supervisor accepts no command
or camera parameter, consumes two fixed arm tokens, verifies the child and
preload again after staging, and bounds the child with an outer timeout.

Because a hostless app cannot pull and independently verify the new LRI before
deciding that the camera may stay up, every possible camera attempt requests a
normal Android reboot, including a clean PASS. A complete child preflight
failure proving all three fields below is the only no-reboot result:

```text
child_final_status=FAIL
capture_attempted=no
child_normal_reboot_required=no
```

Never press the capture button again after an ambiguous result. If the camera
does not reboot after a possible attempt, perform one normal manual restart and
inspect the retained result over ADB before considering another fresh install.
No partition is flashed and no persistent root is installed.

## Build

```sh
android/a1-capture/build_debug_apk.sh
```

The build creates the ARM32 preload from the reviewed C source in a temporary
directory, requires its pinned size and SHA-256, and then embeds it with the two
scripts. Changed payloads are refused until every pin layer is deliberately
updated. The signed APK is written to:

```text
.build/a1-capture/light-l16-a1-inline-focus-capture-debug.apk
```

## One-time installation

The old transition APK used the same package name. Its spent marker survives
`adb install -r`, so use a deliberate uninstall before this first inline-focus
test:

```sh
adb uninstall io.github.tobiasbrummer.lightl16.a1capture
adb install .build/a1-capture/light-l16-a1-inline-focus-capture-debug.apk
```

The uninstall removes only this research app and its private state. Once the
new APK is installed, the camera does not need to remain connected to a
computer for the capture.

## Device test

1. Start from a completed normal boot with a well-charged battery.
2. Fully close the stock camera app; do not leave its preview in the background.
3. Open **L16 A1 Inline AF**.
4. Tap **1. VORPRÜFUNG & SCHARFSCHALTEN**. Continue only after
   `preflight=PASS` and `camera_not_touched=yes`.
5. Point A1 at a well-lit, detailed subject with structure near the image
   center. Within 60 seconds, tap **2. A1 CENTER-AF + 20 MS AUSLÖSEN** once.
6. Expect one normal reboot. Do not press the power button while the operation
   is running unless the camera remains unresponsive beyond the documented
   135-second app window.
7. After Android boots, reopen the app. A valid success includes:

```text
supervisor=L16_HOSTLESS_A1_INLINE_AF_CAPTURE_V1
autofocus_attempted=yes
autofocus_exit_status=0
autofocus_response=camera3_af_state_focused_locked_inline_hal_session
a1_af_shim=verified
supervisor_complete=PASS
capture_attempted=yes
supervisor_decision=normal_reboot_after_hostless_capture_success
app_interpretation=PASS_MANIFEST_REBOOT_REQUESTED
```

The report also records the LRI path, byte size, SHA-1, and retained diagnostic
work directory. The new LRI remains under `/sdcard/DCIM/camera`. These markers
prove the bounded focus gate and artifact creation; they do not yet prove image
sharpness or a nonzero LRI `lens_position`. That requires copying and decoding
the first live output.

Every change to the on-screen report is also mirrored as UTF-8 text without an
additional Android storage permission:

```text
/sdcard/Android/data/io.github.tobiasbrummer.lightl16.a1capture/files/light-l16-a1-inline-af-last-display.txt
```

This file contains the same final app interpretation shown after reboot and can
be copied with ordinary `adb pull`. It is app-owned external state and is
deleted when the APK is uninstalled, so copy it before preparing another fresh
one-shot test.

## Validation status

The preload's native mock proves both key branches: one Camera3
`AF_STATE_FOCUSED_LOCKED` result reaches the real capture and normal close
exactly once, while `NOT_FOCUSED_LOCKED` reaches neither and uses direct HAL
cleanup. It also verifies one START request, later IDLE requests, the exact ROI,
and result forwarding. The complete repository test suite and APK build
exercise the hostless packaging and hash chain without touching a camera.

The first physical hostless attempt on 2026-08-16 validated app-to-root
delivery, all packaged and staged hashes, the exact target identity, clean
camera preconditions, and preload startup. It then failed before HAL loading:
Android 6's linker returned no `bind` target for `dlsym(RTLD_NEXT, "bind")`.
The shim emitted `real_bind_resolve_error`; no AF request was sent and capture
was never released. Cleanup completed with no remaining `lcc` process,
`manual_control=0`, no CameraService client, and both services running.

A second physical attempt used the corrected Bionic `bind` resolution and
reached the active LCC/HAL session. The raw CCB AF write succeeded at the I2C
node, but the running preview requests continued reporting AF reset/idle. The
stream later hit a SOF freeze, the camera daemon stopped, and LCC returned
`-19`; the shim never released capture. The wrapper removed temporary state and
the required reboot restored the normal services. Increasing that raw-request
timeout would therefore not address the conflict.

The current build replaces that raw path with the Camera3 metadata interposer
described above. Static ELF evidence shows both internal calls use
`R_ARM_JUMP_SLOT` PLT entries, while disassembly fixes the request layout and
the result-metadata pointer. Native success and fail-closed tests pass. The
first physical run of this revision also passed: the 16,566,521-byte A1 LRI
has SHA-1 `0c1a2caf98ec8857fa4bdcb57c3a05c28a71b856`, parses completely, and
records `focus_achieved=true`, center ROI, `lens_position=11376`, focus
distances 1691 mm and 2439.4873 mm, and no lens timeout. Earlier transition
LRIs stored `focus_achieved=false` and `lens_position=0`. The test scene was
near the RAW black level, so the metadata and Hall-code transition are proven;
a controlled resolution-chart sharpness measurement is not.
