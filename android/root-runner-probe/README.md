# Light L16 local root-runner probe

This separate, zero-permission Android app performs one bounded end-to-end
test of the previously confirmed LightOS `fihop` root runner without a host.
It does not contain camera control and does not expose a shell.

The app refuses to arm unless all of these preconditions match the examined
production target:

- build incremental `00WW_1_351`, `user` build, `ro.debuggable=0`, model
  `L16`, product `LFC_0002_FIH01`, and kernel
  `3.18.20-perf-g32d1d1c`;
- SELinux is actually permissive through `/sys/fs/selinux/enforce`;
- completed normal boot and an idle `fihop` service. Because it is disabled and
  one-shot, `init.svc.fihop` may be absent before its first-ever start; the app
  accepts either empty or `stopped` only at this initial precondition;
- `persist.sys.fihop=0` with all five argument properties empty;
- `/system/etc/fihop.sh` has the known size and SHA-256 digest;
- no stale private payload, result, or arm file exists.

Android 6 may report the owner-zero application directory through either the
`/data/data` or `/data/user/0` alias. The app allowlists those two exact names
for its own package only; the runner argument itself remains the fixed
`/data/data/.../p.sh` path shown below.

On an explicit button press it writes one embedded, fixed-purpose script into
the app's private directory, verifies its digest, creates a one-use arm token,
sets exactly this runner command, re-reads it, and changes the trigger to `8`:

```text
/system/bin/sh /data/data/io.github.tobiasbrummer.lightl16.runnerprobe/files/p.sh
```

The script requires the exact arm token, deletes it, and clears all six runner
properties before recording only `id`, SELinux context, boot mode, and a fixed
completion marker. The app polls for at most five seconds, validates the whole
result, deletes its files, and verifies the runner's neutral postcondition.
After a trigger, the final service state must be exactly `stopped`; an empty
state is no longer accepted.

No Android permissions are requested. The app contains no camera, storage,
network, native, arbitrary-command, or partition code. Uninstall it after the
test if it is no longer needed.

## Build

```sh
android/root-runner-probe/build_debug_apk.sh
```

The generated APK is written below `.build/root-runner-probe/`, which is not
tracked by Git.

## Device test

Install and open the new `L16 Root Runner Probe` app. This is deliberately a
different package from the property-only probe. Inspect the preflight shown by
the app and press the button once.

Require all of these final lines:

```text
result=PASS
identity=uid=0(root) gid=0(root) groups=0(root)
runner_final=NEUTRAL
files_final=CLEAN
```

On the confirmed build, Android's `id` can append
`context=u:r:qti_init_shell:s0` to the `identity` line; the app accepts only
that exact context. The button remains disabled after the one attempt. Reopen
the app only to inspect the retained report, not to repeat an ambiguous test.

Do not press the button again if the result is ambiguous. If either final state
is not clean, connect ADB and use the mandatory cleanup in
`docs/temporary-root.md` before doing further work.

After an ambiguous trigger the app deletes its fixed private files only after
the service is confirmed stopped with neutral properties. Otherwise it reports
`files_final=PRESERVED_CHECK_REQUIRED`, retaining the one-use, self-clearing
payload for diagnosis instead of racing a possibly delayed start.
