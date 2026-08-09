#!/system/bin/sh
# SPDX-License-Identifier: MIT
# Fixed-purpose, camera-read-only preflight for a future A1 capture.
# It writes only its temporary result and clears the fihop runner properties.

OUT=/data/local/tmp/light_l16_a1_dry_run.result
CAMERA_DUMP=/data/local/tmp/light_l16_a1_camera_service.txt
LCC_SOURCE=/system/etc/lcc
MANUAL_CONTROL=/sys/class/light_ccb/common/manual_control
EXPECTED_BUILD=00WW_1_351
EXPECTED_BUILD_TYPE=user
EXPECTED_DEBUGGABLE=0
EXPECTED_KERNEL=3.18.20-perf-g32d1d1c
EXPECTED_SELINUX=Permissive
EXPECTED_ASIC_FW=0076D11B
EXPECTED_LCC_SIZE=501352
EXPECTED_LCC_SHA1=01b4ea363174240bee5a3005ba9c39f6cb529e6f

# Clear the persistent root-runner trigger and arguments before diagnostics.
setprop persist.sys.fihop 0
setprop persist.sys.fihop1 ""
setprop persist.sys.fihop2 ""
setprop persist.sys.fihop3 ""
setprop persist.sys.fihop4 ""
setprop persist.sys.fihop5 ""

umask 022
: > "$OUT" || exit 1
exec >> "$OUT" 2>&1

finish() {
    rm -f "$CAMERA_DUMP"
    chown 2000:2000 "$OUT"
    chmod 0644 "$OUT"
}

fail() {
    printf 'preflight=FAIL reason=%s\n' "$1"
    exit 1
}

trap finish EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

printf 'mode=A1_DRY_RUN_ONLY\n'
IDENTITY=$(id) || fail "cannot_read_identity"
printf 'identity=%s\n' "$IDENTITY"
case "$IDENTITY" in
    uid=0\(root\)*) ;;
    *) fail "not_uid_0" ;;
esac

BUILD=$(getprop ro.build.version.incremental)
BUILD_TYPE=$(getprop ro.build.type)
DEBUGGABLE=$(getprop ro.debuggable)
BOOT_COMPLETED=$(getprop sys.boot_completed)
BOOT_MODE=$(getprop ro.bootmode)
KERNEL=$(uname -r)
SELINUX=$(getenforce)
ASIC_FW=$(getprop ASIC_FW_VERSION)
printf 'build=%s type=%s debuggable=%s kernel=%s selinux=%s\n' \
    "$BUILD" "$BUILD_TYPE" "$DEBUGGABLE" "$KERNEL" "$SELINUX"
printf 'boot_completed=%s bootmode=%s asic_fw=%s\n' \
    "$BOOT_COMPLETED" "$BOOT_MODE" "$ASIC_FW"
[ "$BUILD" = "$EXPECTED_BUILD" ] || fail "unexpected_build"
[ "$BUILD_TYPE" = "$EXPECTED_BUILD_TYPE" ] || fail "unexpected_build_type"
[ "$DEBUGGABLE" = "$EXPECTED_DEBUGGABLE" ] || fail "unexpected_debuggable"
[ "$KERNEL" = "$EXPECTED_KERNEL" ] || fail "unexpected_kernel"
[ "$SELINUX" = "$EXPECTED_SELINUX" ] || fail "unexpected_selinux"
[ "$BOOT_COMPLETED" = "1" ] || fail "boot_not_completed"
[ "$BOOT_MODE" = "unknown" ] || fail "unexpected_bootmode"
[ "$ASIC_FW" = "$EXPECTED_ASIC_FW" ] || fail "unexpected_asic_firmware"

[ "$(getprop persist.sys.fihop)" = "0" ] || fail "root_trigger_not_cleared"
for PROPERTY in \
    persist.sys.fihop1 persist.sys.fihop2 persist.sys.fihop3 \
    persist.sys.fihop4 persist.sys.fihop5
do
    [ -z "$(getprop "$PROPERTY")" ] || fail "root_argument_not_cleared"
done

[ -r "$LCC_SOURCE" ] || fail "lcc_missing"
LCC_SIZE=$(/system/bin/toybox wc -c < "$LCC_SOURCE") || fail "cannot_size_lcc"
[ "$LCC_SIZE" = "$EXPECTED_LCC_SIZE" ] || fail "unexpected_lcc_size"
LCC_SHA1=$(/system/bin/toybox sha1sum "$LCC_SOURCE") || fail "cannot_hash_lcc"
LCC_SHA1=${LCC_SHA1%% *}
printf 'lcc_size=%s lcc_sha1=%s\n' "$LCC_SIZE" "$LCC_SHA1"
[ "$LCC_SHA1" = "$EXPECTED_LCC_SHA1" ] || fail "unexpected_lcc_hash"

[ -r "$MANUAL_CONTROL" ] || fail "manual_control_missing"
MANUAL_VALUE=$(cat "$MANUAL_CONTROL") || fail "cannot_read_manual_control"
printf 'manual_control=%s\n' "$MANUAL_VALUE"
case "$MANUAL_VALUE" in
    *0x0) ;;
    *) fail "manual_control_not_zero" ;;
esac

FWUPGRADE_STATE=$(getprop init.svc.fwupgrade)
printf 'fwupgrade=%s\n' "$FWUPGRADE_STATE"
[ "$FWUPGRADE_STATE" = "stopped" ] || fail "fwupgrade_not_stopped"

/system/bin/dumpsys media.camera > "$CAMERA_DUMP" \
    || fail "camera_service_dump_failed"
ACTIVE_CLIENTS=$(
    /system/bin/toybox sed -n \
        '/Active Camera Clients:/,/Allowed users:/p' "$CAMERA_DUMP" \
        | /system/bin/toybox sed -n '2p'
)
[ "$ACTIVE_CLIENTS" = "[]" ] || fail "camera_client_present_or_state_unknown"
printf 'camera_clients=none\n'

printf '%s\n' 'mask=02 00 00 module=A1 asic=1'
printf '%s\n' 'factory_tuple=11 F1 00'
printf '%s\n' \
    'planned_argv=<lcc-copy> -m 0 -s 0 -f 1 02 00 00 11 F1 00 -R 4160,3120 -e 2609592 -g 1.0'
printf '%s\n' 'capture_executed=no'
printf '%s\n' 'preflight=PASS'
