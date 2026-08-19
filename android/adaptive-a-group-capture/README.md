# Adaptive A-group HDR capture app

This separate Android package combines the preview-derived highlight/shadow
meter with the physically tested same-session A1-A5 center-AF capture path.
It is deliberately a first paired-measurement pilot, not a general root shell.

The UI has three deliberate stages:

1. open the Camera2 preview and let AE settle;
2. measure stable shadow frames plus a dedicated minimum-AE-compensation
   highlight phase;
3. only after both phases pass, start one A1-A5 capture using the displayed
   five-value exposure plan.

The measurement stage closes Camera2 before the root path is entered. The
third button is valid for 60 seconds and launches a private, non-exported
activity. That activity consumes a one-time UI token, performs the established
read-only device and payload preflight, and triggers the root supervisor only
on PASS.

The plan is a canonical app-private ASCII line:

```text
L16_ADAPTIVE_A_GROUP_PLAN_V1 A1 A2 A3 A4 A5
```

There are no editable parameters. Java, the root supervisor, and the child
capture script independently require exactly five decimal values in A1-A5
order, `A2 == A1`, a nondecreasing A1/A3/A4/A5 ladder, and values from 10 us to
20 ms. Gain is fixed at 1.0 and the module mask is fixed at `3E 00 00`.
Values below the already exercised 1.25 ms LCC profile are intentionally
accepted for this exposure-transfer pilot because shorter integration is not a
hardware stress, but their LCC/image behaviour is not yet physically verified.

After every possible camera attempt, the supervisor requests a normal reboot.
The one-install/one-shot marker is written before the root trigger, so an
ambiguous trigger delivery cannot be repeated accidentally. A fresh deliberate
test requires uninstalling and reinstalling the package.

The highlight estimator uses p99.9 together with the matching 0.1 % clipping
budget; isolated point reflections no longer cause the stricter, inconsistent
p99.99 veto. A measured ladder is also refused if the 20-ms pilot cap collapses
it below 0.5 EV or makes A1 and A5 equal. This prevents a very dark scene from
being incorrectly accepted as five identical 20-ms HDR roles.

If a reboot happens before Android copies the completed supervisor manifest to
external storage, install a newer APK with `adb install -r` and launch it once.
The spent installation is then handled in recovery-display-only mode: the app
reads its existing private `r.txt` and mirrors it to the capture report without
touching Camera2, root, or `lcc`. Preserve that report before uninstalling.
The current supervisor additionally mirrors its completed private manifest
directly to the already-created fixed external report path before the delayed
reboot, so a later app launch should no longer be required for normal runs.

The first useful physical adaptive run on 2026-08-16 succeeded at the artifact
level. Its requested A1-A5 plan was 6.360152, 6.360152, 10.099603, 16.037664,
and 20.000000 ms. The 81,484,025-byte LRI contains exactly A1-A5 with measured
exposures within 2,918 ns of those requests, analog/digital gain 1.0, one image
ID and timestamp, `focus_achieved=true`, nonzero lens positions, no lens
timeouts, valid nonconstant RAW10 data, and no unknown protobuf fields. The
external capture TXT retained only its pre-trigger progress text; that
diagnostic race is what the direct supervisor mirror addresses.

Build with:

```sh
./android/adaptive-a-group-capture/build_debug_apk.sh
```

The measurement and root result screens are mirrored to separate text files in
the package external-files directory. A successful run should leave exactly
one new `.lri` under `/sdcard/DCIM/camera` and reboot the camera.
