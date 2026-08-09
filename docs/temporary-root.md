# Temporary root runner on LightOS 1.3.5.1

## What this is

The confirmed root path is a vendor debug interface, not a kernel exploit. The
normal LightOS init configuration defines a disabled one-shot service named
`fihop`, running as user `root`. A property trigger starts the service when
`persist.sys.fihop` becomes `8`. The vendor shell script reads five companion
properties and executes them as a program plus arguments.

On the examined production build this was sufficient to run one fixed-purpose
script as:

```text
uid=0(root) gid=0(root) groups=0(root) context=u:r:qti_init_shell:s0
```

It does not turn `adbd` into root, install `su`, survive as a root facility after
cleanup, patch boot, or write a partition. Every privileged task would require
a new bounded payload.

## Exact confirmed target

This procedure was verified on 2026-08-08 on one owner-controlled device with:

| Property | Confirmed value |
| --- | --- |
| LightOS | `1.3.5.1` |
| build incremental | `00WW_1_351` |
| build type | `user` |
| `ro.debuggable` | `0` |
| kernel | `3.18.20-perf-g32d1d1c` |
| SELinux | `Permissive` |
| `/system/etc/fihop.sh` SHA-256 | `6550cce118492e43c5285d469f7dc383e4d6c14c7cf766de1c82cb57fbaebe4f` |

Stop if any identity differs. This is especially important for SELinux state,
init imports, property permissions, and the vendor script hash.

## Risk model

The procedure temporarily changes `persist.sys.*` properties, which are backed
by persistent property storage. The payload therefore clears the trigger and
all arguments as its first privileged operations, and the host repeats cleanup
even if no result appears.

UID 0 can destroy the camera. The diagnostic payload included here performs
only these privileged actions:

- clear the six `fihop` properties;
- record identity, SELinux context, and boot mode;
- make that result readable by the normal ADB shell.

It does not access block devices, camera sysfs, firmware, calibration data, or
Android services.

## 1. Read-only preflight

Connect the unlocked camera over ADB and inspect it before setting a property:

```bash
adb devices -l
adb shell 'id; getprop ro.build.version.incremental; getprop ro.build.type; getprop ro.debuggable'
adb shell 'uname -r; getenforce; getprop sys.boot_completed; getprop ro.bootmode'
adb shell 'ls -l /system/etc/fihop.sh /data/local/tmp'
```

The normal shell should remain `uid=2000(shell)`. Pull the vendor script only to
hash your own copy; do not add it to this repository:

```bash
mkdir -p inputs
adb pull /system/etc/fihop.sh inputs/fihop.sh.device
sha256sum inputs/fihop.sh.device
```

Check that the trigger and all five argument properties are empty or zero:

```bash
adb shell 'for p in persist.sys.fihop persist.sys.fihop1 persist.sys.fihop2 persist.sys.fihop3 persist.sys.fihop4 persist.sys.fihop5; do printf "%s=%s\n" "$p" "$(getprop "$p")"; done'
```

If `sys.boot_completed` is not `1`, a property is unexpectedly populated, or
the script hash differs, stop and investigate.

## 2. Stage the fixed diagnostic payload

Review [`device/root_probe_payload.sh`](../device/root_probe_payload.sh), then:

```bash
adb push device/root_probe_payload.sh /data/local/tmp/light_l16_fihop_root_probe.sh
adb shell 'chmod 0700 /data/local/tmp/light_l16_fihop_root_probe.sh; rm -f /data/local/tmp/light_l16_fihop_root_probe.result'
```

Set the program and its single argument. Keep the trigger at zero until all
arguments are complete:

```bash
adb shell 'setprop persist.sys.fihop 0'
adb shell 'setprop persist.sys.fihop1 /system/bin/sh'
adb shell 'setprop persist.sys.fihop2 /data/local/tmp/light_l16_fihop_root_probe.sh'
adb shell 'setprop persist.sys.fihop3 ""; setprop persist.sys.fihop4 ""; setprop persist.sys.fihop5 ""'
```

Re-read the properties. `fihop1` and `fihop2` must contain exactly the two
values above; `fihop3` through `fihop5` must be empty.

## 3. Trigger once and read the result

Only this final property change starts the service:

```bash
adb shell 'setprop persist.sys.fihop 8'
```

Poll for at most five seconds rather than repeatedly retriggering:

```bash
for attempt in 1 2 3 4 5; do
  adb shell 'cat /data/local/tmp/light_l16_fihop_root_probe.result 2>/dev/null' && break
  sleep 1
done
```

The known successful result begins with the UID/GID/context line shown above.
Treat any other identity as failure; do not use it for a privileged task.

## 4. Mandatory host cleanup

Run this whether the probe succeeded or failed:

```bash
adb shell 'setprop persist.sys.fihop 0; setprop persist.sys.fihop1 ""; setprop persist.sys.fihop2 ""; setprop persist.sys.fihop3 ""; setprop persist.sys.fihop4 ""; setprop persist.sys.fihop5 ""'
adb shell 'rm -f /data/local/tmp/light_l16_fihop_root_probe.sh /data/local/tmp/light_l16_fihop_root_probe.result'
```

Verify the postcondition:

```bash
adb shell 'for p in persist.sys.fihop persist.sys.fihop1 persist.sys.fihop2 persist.sys.fihop3 persist.sys.fihop4 persist.sys.fihop5; do printf "%s=%s\n" "$p" "$(getprop "$p")"; done'
adb shell 'getprop init.svc.fihop; id; getprop ro.bootmode'
```

Expected: trigger `0`, five empty arguments, service `stopped`, ordinary ADB
shell still UID 2000, and unchanged boot mode.

## Paths deliberately rejected

- `adb root` is disabled by `ro.debuggable=0` on this production build.
- Permissive SELinux alone does not bypass Unix mode bits or provide root.
- CVE-2019-2215 remained an unverified research lead; public device-specific
  proof-of-concepts do not establish compatibility with this kernel.
- `adb reboot ffbm` is not a proven factory-mode entry on this build.
- Writing an `ffbm-` cookie to `misc` is persistent and has no independently
  verified recovery path. Do not try it.
- Patched boot/recovery images and persistent root are unnecessary for this
  diagnostic route and are outside this repository's scope.

## Using the runner beyond the probe

Do not convert this mechanism into an open-ended root shell. For a legitimate
read-only backup or diagnostic, create a new auditable script with a fixed list
of paths, bounded runtime, explicit output ownership, and the same self-clear
and host-cleanup sequence. Hash inputs before and after reading where practical.

Camera-control commands need additional service-state and `manual_control`
cleanup. A successful UID-0 probe is not by itself authorization to use the raw
driver sysfs nodes described in the safety policy.
