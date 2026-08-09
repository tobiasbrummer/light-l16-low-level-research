#!/system/bin/sh
# SPDX-License-Identifier: MIT
# Fixed-purpose Light L16 fihop probe. This is not a general root shell.

OUT=/data/local/tmp/light_l16_fihop_root_probe.result

# Clear the persistent trigger and arguments before doing anything else.
setprop persist.sys.fihop 0
setprop persist.sys.fihop1 ""
setprop persist.sys.fihop2 ""
setprop persist.sys.fihop3 ""
setprop persist.sys.fihop4 ""
setprop persist.sys.fihop5 ""

umask 022
{
    id
    printf 'context='
    cat /proc/self/attr/current
    printf 'bootmode=%s\n' "$(getprop ro.bootmode)"
} > "$OUT"

chown 2000:2000 "$OUT"
chmod 0644 "$OUT"
