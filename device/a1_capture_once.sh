#!/system/bin/sh
# SPDX-License-Identifier: MIT
# DANGER: after all fixed preconditions pass, this executes one A1 lcc capture.
# It is intentionally not a general camera or root wrapper.

PATH=/sbin:/vendor/bin:/system/sbin:/system/bin:/system/xbin
export PATH

OUT=/data/local/tmp/light_l16_a1_capture.result
ARM_FILE=/data/local/tmp/light_l16_a1_capture.armed
ARM_VALUE=A1_CAPTURE_2609592NS_GAIN_1.0_ONCE
WORK_PREFIX=/data/local/tmp/light_l16_a1_capture_run
LCC_SOURCE=/system/etc/lcc
HAL_SOURCE=/system/lib/hw/camera.msm8996.so
MANUAL_CONTROL=/sys/class/light_ccb/common/manual_control
LRI_DIR=/sdcard/DCIM/camera
EXPECTED_BUILD=00WW_1_351
EXPECTED_BUILD_TYPE=user
EXPECTED_DEBUGGABLE=0
EXPECTED_KERNEL=3.18.20-perf-g32d1d1c
EXPECTED_SELINUX=Permissive
EXPECTED_ASIC_FW=0076D11B
EXPECTED_LCC_SIZE=501352
EXPECTED_LCC_SHA1=01b4ea363174240bee5a3005ba9c39f6cb529e6f
EXPECTED_HAL_SIZE=1338100
EXPECTED_HAL_SHA1=016602174e0635e79cda5566d5e850c1294a9300
MIN_DATA_FREE_KB=262144

CAPTURE_ATTEMPTED=no
FINAL_STATUS=FAIL
FINAL_REASON=wrapper_did_not_finish
LCC_STATUS=not_run
NORMAL_REBOOT_REQUIRED=no
CLEANUP_OK=no
WORKDIR=
LCC_COPY=
LRI_OUTPUT_COUNT=unknown
LRI_OUTPUT_PATH=
LRI_OUTPUT_SIZE=unknown
LRI_OUTPUT_SHA1=

clear_runner() {
    setprop persist.sys.fihop 0
    setprop persist.sys.fihop1 ""
    setprop persist.sys.fihop2 ""
    setprop persist.sys.fihop3 ""
    setprop persist.sys.fihop4 ""
    setprop persist.sys.fihop5 ""
}

manual_is_zero() {
    VALUE=$(cat "$MANUAL_CONTROL" 2>/dev/null) || return 1
    case "$VALUE" in
        *0x0) return 0 ;;
        *) return 1 ;;
    esac
}

force_manual_zero() {
    [ -w "$MANUAL_CONTROL" ] || return 1
    printf '0\n' > "$MANUAL_CONTROL" || return 1
    manual_is_zero
}

camera_clients_none() {
    CAMERA_FILE=$1
    /system/bin/timeout -k 2s 10s /system/bin/dumpsys media.camera \
        > "$CAMERA_FILE" 2>&1 || return 1
    ACTIVE_CLIENTS=$(
        /system/bin/toybox sed -n \
            '/Active Camera Clients:/,/Allowed users:/p' "$CAMERA_FILE" \
            | /system/bin/toybox sed -n '2p'
    )
    [ "$ACTIVE_CLIENTS" = "[]" ]
}

snapshot_lri_paths() {
    TARGET=$1
    : > "$TARGET" || return 1
    for FILE in "$LRI_DIR"/RDI_*.lri; do
        [ -f "$FILE" ] || continue
        printf '%s\n' "$FILE" >> "$TARGET" || return 1
    done
}

path_in_snapshot() {
    CANDIDATE=$1
    SNAPSHOT=$2
    while IFS= read -r EXISTING; do
        [ "$CANDIDATE" = "$EXISTING" ] && return 0
    done < "$SNAPSHOT"
    return 1
}

valid_generated_lri_path() {
    case "$1" in
        "$LRI_DIR"/RDI_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9].lri)
            return 0
            ;;
        *) return 1 ;;
    esac
}

capture_diagnostics() {
    SUFFIX=$1
    [ -n "$WORKDIR" ] && [ -d "$WORKDIR" ] || return 0
    /system/bin/dmesg | /system/bin/toybox tail -n 500 \
        > "$WORKDIR/dmesg.$SUFFIX.txt" 2>&1
    /system/bin/logcat -d -v threadtime -t 500 \
        > "$WORKDIR/logcat.$SUFFIX.txt" 2>&1
    {
        printf 'time_utc='; /system/bin/date -u '+%Y-%m-%dT%H:%M:%SZ'
        printf 'manual_control='; cat "$MANUAL_CONTROL" 2>&1
        printf 'fwupgrade=%s\n' "$(getprop init.svc.fwupgrade)"
        printf 'fihop=%s\n' "$(getprop init.svc.fihop)"
        printf 'media=%s\n' "$(getprop init.svc.media)"
        printf 'lightsvr=%s\n' "$(getprop init.svc.lightsvr)"
        printf 'aos=%s\n' "$(getprop ro.light.aos)"
        printf 'lcc_mode=%s\n' "$(getprop camera.light.lcc.mode)"
        printf 'tid='; cat /data/tid.txt 2>&1 || true
        /system/bin/ps
    } > "$WORKDIR/state.$SUFFIX.txt" 2>&1
}

fail() {
    FINAL_STATUS=FAIL
    FINAL_REASON=$1
    printf 'failure=%s\n' "$FINAL_REASON"
    exit 1
}

finish() {
    ORIGINAL_STATUS=$?
    trap - EXIT HUP INT TERM

    clear_runner
    if [ "$CAPTURE_ATTEMPTED" = "yes" ]; then
        NORMAL_REBOOT_REQUIRED=yes
        force_manual_zero || true
        /system/bin/sleep 1
    fi

    capture_diagnostics after
    if [ -n "$WORKDIR" ] && [ -d "$WORKDIR" ]; then
        /system/bin/timeout -k 2s 10s /system/bin/dumpsys media.camera \
            > "$WORKDIR/camera.after.txt" 2>&1 || true
    fi

    LCC_REMAINS=no
    if /system/bin/toybox pgrep -x lcc >/dev/null 2>&1; then
        LCC_REMAINS=yes
    fi
    MANUAL_AFTER=unreadable
    if [ -r "$MANUAL_CONTROL" ]; then
        MANUAL_AFTER=$(cat "$MANUAL_CONTROL" 2>/dev/null)
    fi

    if manual_is_zero && [ "$LCC_REMAINS" = "no" ]; then
        CLEANUP_OK=yes
    fi
    if [ "$CAPTURE_ATTEMPTED" = "yes" ] && [ "$CLEANUP_OK" != "yes" ]; then
        FINAL_STATUS=FAIL
        FINAL_REASON=post_capture_cleanup_failed
    fi

    if [ -n "$LCC_COPY" ] && [ -f "$LCC_COPY" ]; then
        rm -f "$LCC_COPY"
    fi

    printf 'capture_attempted=%s\n' "$CAPTURE_ATTEMPTED"
    printf 'lcc_exit_status=%s\n' "$LCC_STATUS"
    printf 'manual_control_after=%s\n' "$MANUAL_AFTER"
    printf 'lcc_process_after=%s\n' "$LCC_REMAINS"
    printf 'cleanup_ok=%s\n' "$CLEANUP_OK"
    printf 'normal_reboot_required=%s\n' "$NORMAL_REBOOT_REQUIRED"
    printf 'lri_output_count=%s\n' "$LRI_OUTPUT_COUNT"
    printf 'lri_output_path=%s\n' "$LRI_OUTPUT_PATH"
    printf 'lri_output_size=%s\n' "$LRI_OUTPUT_SIZE"
    printf 'lri_output_sha1=%s\n' "$LRI_OUTPUT_SHA1"
    printf 'workdir=%s\n' "$WORKDIR"

    if [ -n "$WORKDIR" ] && [ -d "$WORKDIR" ]; then
        for FILE in "$WORKDIR"/*; do
            [ -f "$FILE" ] || continue
            chown 2000:2000 "$FILE"
            chmod 0640 "$FILE"
        done
        chown 2000:2000 "$WORKDIR"
        chmod 0750 "$WORKDIR"
    fi
    chown 2000:2000 "$OUT"
    chmod 0644 "$OUT"
    # The host uses final_status as the completion marker. Emit it only after
    # logs are readable and the temporary lcc executable has been removed.
    printf 'final_reason=%s\n' "$FINAL_REASON"
    printf 'final_status=%s\n' "$FINAL_STATUS"
    return "$ORIGINAL_STATUS"
}

# Clear the persistent root-runner trigger and arguments before diagnostics.
clear_runner

umask 077
: > "$OUT" || exit 1
chmod 0644 "$OUT" || exit 1
exec >> "$OUT" 2>&1

trap finish EXIT
trap 'FINAL_REASON=signal_hup; exit 129' HUP
trap 'FINAL_REASON=signal_int; exit 130' INT
trap 'FINAL_REASON=signal_term; exit 143' TERM

printf 'mode=A1_FIXED_CAPTURE_ONCE\n'
printf 'warning=this_payload_executes_lcc_after_preflight\n'

[ -r "$ARM_FILE" ] || fail not_armed
ARMED=$(cat "$ARM_FILE") || fail cannot_read_arm_file
rm -f "$ARM_FILE" || fail cannot_consume_arm_file
[ "$ARMED" = "$ARM_VALUE" ] || fail wrong_arm_value
printf 'arm_token=accepted_and_consumed\n'

WORKDIR="$WORK_PREFIX.$$"
[ ! -e "$WORKDIR" ] || fail workdir_already_exists
mkdir "$WORKDIR" || fail cannot_create_workdir
chmod 0700 "$WORKDIR" || fail cannot_secure_workdir
LCC_COPY="$WORKDIR/lcc"
printf 'workdir_created=%s\n' "$WORKDIR"

IDENTITY=$(id) || fail cannot_read_identity
printf 'identity=%s\n' "$IDENTITY"
case "$IDENTITY" in
    uid=0\(root\)*) ;;
    *) fail not_uid_0 ;;
esac

BUILD=$(getprop ro.build.version.incremental)
BUILD_TYPE=$(getprop ro.build.type)
DEBUGGABLE=$(getprop ro.debuggable)
BOOT_COMPLETED=$(getprop sys.boot_completed)
BOOT_MODE=$(getprop ro.bootmode)
KERNEL=$(uname -r)
SELINUX=$(getenforce)
ASIC_FW=$(getprop ASIC_FW_VERSION)
AOS=$(getprop ro.light.aos)
LCC_MODE=$(getprop camera.light.lcc.mode)
MEDIA_STATE=$(getprop init.svc.media)
LIGHTSVR_STATE=$(getprop init.svc.lightsvr)
printf 'build=%s type=%s debuggable=%s kernel=%s selinux=%s\n' \
    "$BUILD" "$BUILD_TYPE" "$DEBUGGABLE" "$KERNEL" "$SELINUX"
printf 'boot_completed=%s bootmode=%s asic_fw=%s aos=%s lcc_mode=%s\n' \
    "$BOOT_COMPLETED" "$BOOT_MODE" "$ASIC_FW" "$AOS" "$LCC_MODE"
printf 'media=%s lightsvr=%s\n' "$MEDIA_STATE" "$LIGHTSVR_STATE"
[ "$BUILD" = "$EXPECTED_BUILD" ] || fail unexpected_build
[ "$BUILD_TYPE" = "$EXPECTED_BUILD_TYPE" ] || fail unexpected_build_type
[ "$DEBUGGABLE" = "$EXPECTED_DEBUGGABLE" ] || fail unexpected_debuggable
[ "$KERNEL" = "$EXPECTED_KERNEL" ] || fail unexpected_kernel
[ "$SELINUX" = "$EXPECTED_SELINUX" ] || fail unexpected_selinux
[ "$BOOT_COMPLETED" = "1" ] || fail boot_not_completed
[ "$BOOT_MODE" = "unknown" ] || fail unexpected_bootmode
[ "$ASIC_FW" = "$EXPECTED_ASIC_FW" ] || fail unexpected_asic_firmware
[ "$AOS" = "1" ] || fail unexpected_aos_state
case "$LCC_MODE" in
    ""|0) ;;
    *) fail unexpected_lcc_mode ;;
esac
[ "$MEDIA_STATE" = "running" ] || fail media_not_running
[ "$LIGHTSVR_STATE" = "running" ] || fail lightsvr_not_running

[ "$(getprop persist.sys.fihop)" = "0" ] || fail root_trigger_not_cleared
for PROPERTY in \
    persist.sys.fihop1 persist.sys.fihop2 persist.sys.fihop3 \
    persist.sys.fihop4 persist.sys.fihop5
do
    [ -z "$(getprop "$PROPERTY")" ] || fail root_argument_not_cleared
done

[ -r "$LCC_SOURCE" ] || fail lcc_missing
LCC_SIZE=$(/system/bin/toybox wc -c < "$LCC_SOURCE") || fail cannot_size_lcc
[ "$LCC_SIZE" = "$EXPECTED_LCC_SIZE" ] || fail unexpected_lcc_size
LCC_SHA1=$(/system/bin/toybox sha1sum "$LCC_SOURCE") || fail cannot_hash_lcc
LCC_SHA1=${LCC_SHA1%% *}
printf 'lcc_size=%s lcc_sha1=%s\n' "$LCC_SIZE" "$LCC_SHA1"
[ "$LCC_SHA1" = "$EXPECTED_LCC_SHA1" ] || fail unexpected_lcc_hash
[ -r "$HAL_SOURCE" ] || fail camera_hal_missing
HAL_SIZE=$(/system/bin/toybox wc -c < "$HAL_SOURCE") || fail cannot_size_camera_hal
[ "$HAL_SIZE" = "$EXPECTED_HAL_SIZE" ] || fail unexpected_camera_hal_size
HAL_SHA1=$(/system/bin/toybox sha1sum "$HAL_SOURCE") || fail cannot_hash_camera_hal
HAL_SHA1=${HAL_SHA1%% *}
printf 'camera_hal_size=%s camera_hal_sha1=%s\n' "$HAL_SIZE" "$HAL_SHA1"
[ "$HAL_SHA1" = "$EXPECTED_HAL_SHA1" ] || fail unexpected_camera_hal_hash
[ -x /system/bin/timeout ] || fail timeout_missing

[ -r "$MANUAL_CONTROL" ] || fail manual_control_missing
manual_is_zero || fail manual_control_not_zero
printf 'manual_control_before=zero\n'

FWUPGRADE_STATE=$(getprop init.svc.fwupgrade)
printf 'fwupgrade=%s\n' "$FWUPGRADE_STATE"
[ "$FWUPGRADE_STATE" = "stopped" ] || fail fwupgrade_not_stopped

if /system/bin/toybox pgrep -x lcc >/dev/null 2>&1; then
    fail lcc_already_running
fi
if /system/bin/toybox grep -qi ':1388' /proc/net/udp /proc/net/udp6 2>/dev/null; then
    fail udp_port_5000_in_use
fi

DATA_LINE=$(/system/bin/toybox df -k /data | /system/bin/toybox tail -n 1) \
    || fail cannot_read_data_free_space
set -- $DATA_LINE
DATA_FREE_KB=$4
case "$DATA_FREE_KB" in
    ""|*[!0-9]*) fail invalid_data_free_space ;;
esac
printf 'data_free_kb=%s\n' "$DATA_FREE_KB"
[ "$DATA_FREE_KB" -ge "$MIN_DATA_FREE_KB" ] || fail insufficient_data_free_space

[ -d "$LRI_DIR" ] || fail lri_output_directory_missing
[ -w "$LRI_DIR" ] || fail lri_output_directory_not_writable
snapshot_lri_paths "$WORKDIR/lri.before.txt" || fail cannot_snapshot_lri_before

capture_diagnostics before
camera_clients_none "$WORKDIR/camera.before.txt" || \
    fail camera_client_present_or_state_unknown
printf 'camera_clients_before=none\n'

cp "$LCC_SOURCE" "$LCC_COPY" || fail cannot_copy_lcc
chmod 0700 "$LCC_COPY" || fail cannot_make_lcc_executable
COPY_SHA1=$(/system/bin/toybox sha1sum "$LCC_COPY") || fail cannot_hash_lcc_copy
COPY_SHA1=${COPY_SHA1%% *}
[ "$COPY_SHA1" = "$EXPECTED_LCC_SHA1" ] || fail copied_lcc_hash_mismatch
printf 'lcc_copy_sha1=%s\n' "$COPY_SHA1"

printf '%s\n' 'mask=02 00 00 module=A1 asic=1'
printf '%s\n' 'factory_tuple=11 F1 00'
printf '%s\n' \
    'executed_argv=<verified-lcc-copy> -m 0 -s 0 -f 1 02 00 00 11 F1 00 -R 4160,3120 -e 2609592 -g 1.0'
printf '%s\n' 'outer_timeout=TERM_after_30s_KILL_after_5s'
printf '%s\n' 'lcc_response_files=disabled'
printf '%s\n' 'hal_lri_output=expected_automatically'
printf 'hal_lri_directory=%s\n' "$LRI_DIR"

CAPTURE_ATTEMPTED=yes
NORMAL_REBOOT_REQUIRED=yes
(
    cd "$WORKDIR" || exit 126
    /system/bin/timeout -k 5s 30s "$LCC_COPY" \
        -m 0 -s 0 -f 1 02 00 00 11 F1 00 \
        -R 4160,3120 -e 2609592 -g 1.0
) > "$WORKDIR/lcc.txt" 2>&1
LCC_STATUS=$?
printf 'lcc_returned=%s\n' "$LCC_STATUS"

# lcc normally performs this itself. Repeat it from the still-running root
# supervisor before any slower diagnostics, including on nonzero exit.
force_manual_zero || fail immediate_manual_control_cleanup_failed

if /system/bin/toybox pgrep -x lcc >/dev/null 2>&1; then
    fail lcc_process_survived_timeout
fi
camera_clients_none "$WORKDIR/camera.after_immediate.txt" || \
    fail camera_client_after_capture_or_state_unknown
printf 'camera_clients_after_immediate=none\n'
[ "$(getprop init.svc.media)" = "running" ] || fail media_stopped_after_capture
[ "$(getprop init.svc.lightsvr)" = "running" ] || fail lightsvr_stopped_after_capture

snapshot_lri_paths "$WORKDIR/lri.after.txt" || fail cannot_snapshot_lri_after
: > "$WORKDIR/lri.new.txt" || fail cannot_create_lri_delta
while IFS= read -r FILE; do
    [ -n "$FILE" ] || continue
    if ! path_in_snapshot "$FILE" "$WORKDIR/lri.before.txt"; then
        printf '%s\n' "$FILE" >> "$WORKDIR/lri.new.txt" || \
            fail cannot_record_new_lri
    fi
done < "$WORKDIR/lri.after.txt"
LRI_OUTPUT_COUNT=$(/system/bin/toybox wc -l < "$WORKDIR/lri.new.txt") || \
    fail cannot_count_new_lri
case "$LRI_OUTPUT_COUNT" in
    ""|*[!0-9]*) fail invalid_new_lri_count ;;
esac
printf 'new_lri_count=%s\n' "$LRI_OUTPUT_COUNT"

if [ "$LRI_OUTPUT_COUNT" = "1" ]; then
    LRI_OUTPUT_PATH=$(/system/bin/toybox sed -n '1p' "$WORKDIR/lri.new.txt") || \
        fail cannot_read_new_lri_path
    valid_generated_lri_path "$LRI_OUTPUT_PATH" || fail unexpected_new_lri_path
    [ -r "$LRI_OUTPUT_PATH" ] || fail new_lri_not_readable
    LRI_OUTPUT_SIZE=$(/system/bin/toybox wc -c < "$LRI_OUTPUT_PATH") || \
        fail cannot_size_new_lri
    case "$LRI_OUTPUT_SIZE" in
        ""|*[!0-9]*) fail invalid_new_lri_size ;;
    esac
    [ "$LRI_OUTPUT_SIZE" -ge 32 ] || fail new_lri_too_small
    LRI_OUTPUT_SHA1=$(/system/bin/toybox sha1sum "$LRI_OUTPUT_PATH") || \
        fail cannot_hash_new_lri
    LRI_OUTPUT_SHA1=${LRI_OUTPUT_SHA1%% *}
    printf 'new_lri_path=%s\n' "$LRI_OUTPUT_PATH"
    printf 'new_lri_size=%s\n' "$LRI_OUTPUT_SIZE"
    printf 'new_lri_sha1=%s\n' "$LRI_OUTPUT_SHA1"
fi

[ "$LCC_STATUS" = "0" ] || fail lcc_nonzero_or_timeout
[ "$LRI_OUTPUT_COUNT" = "1" ] || fail lri_artifact_missing_or_ambiguous
FINAL_STATUS=PASS
FINAL_REASON=lcc_exit_zero_lri_captured_cleanup_verified_content_not_validated
exit 0
