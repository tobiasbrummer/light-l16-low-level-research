# Light L16 local property permission probe

This zero-permission Android app answers one question: can an ordinary app on
the production LightOS build write the `persist.sys.*` property class required
to start the already documented, bounded `fihop` runner?

It does **not** start that runner. Before doing anything, it requires
`persist.sys.fihop=0` and all five argument properties to be empty. It then
attempts one round trip on `persist.sys.fihop5` only:

1. write a process-specific harmless marker;
2. read the marker back;
3. clear the property immediately;
4. verify that the final value is empty.

The setter contains an additional code-level allowlist which rejects every
property name except `persist.sys.fihop5`. The manifest requests no Android
permissions. The app has no camera, storage, network, shell, or root code.

## Build

The build script uses an existing Android SDK and debug keystore. It does not
download dependencies or use Gradle:

```sh
android/property-probe/build_debug_apk.sh
```

Set `ANDROID_SDK_ROOT` and/or `LIGHT_L16_DEBUG_KEYSTORE` if they are not in the
usual local locations. The generated debug APK is written below
`.build/property-probe/`, which is not tracked by Git.

## Device test

Install and open the app, inspect the displayed preconditions, then press the
single test button. `PASS` means an ordinary app can write this property class;
`DENIED_OR_ERROR` is the expected safe outcome if Android's property service
rejects the app UID. `REFUSED` means the runner was not in the exact neutral
state and no write was attempted.

After either outcome, require `probe_final=<empty>` and `cleanup=CLEAN`. If
either is absent, inspect and clear slot 5 over the already established ADB
path before doing further work.
