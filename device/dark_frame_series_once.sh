#!/system/bin/sh
# SPDX-License-Identifier: MIT
# DANGER: after all fixed preconditions pass, this executes a fixed series of
# 24 lcc captures with the lens covered.  It is intentionally not a general
# camera or root wrapper.  The plan below is compiled in; the script accepts no
# arguments and no parameter is reachable from the app.

PATH=/sbin:/vendor/bin:/system/sbin:/system/bin:/system/xbin
export PATH

[ "$0" = /data/local/tmp/light_l16_dark_frame_series_once.sh ] || {
    printf 'refusing unexpected invocation path: %s\n' "$0" >&2
    exit 2
}
[ "$#" -eq 0 ] || {
    printf 'refusing unexpected arguments\n' >&2
    exit 2
}

# Exposure axis first at gain 1.0, ascending time; then the gain axis at
# 1.25 ms, ascending gain.  Three repeats per cell.  The exposure axis uses the
# already exercised gain 1.0, so a refusal on the untested gain axis cannot
# cost the exposure measurement.
CAPTURE_PLAN='10000:1.0 10000:1.0 10000:1.0 1250000:1.0 1250000:1.0 1250000:1.0 5000000:1.0 5000000:1.0 5000000:1.0 20000000:1.0 20000000:1.0 20000000:1.0 1250000:2.0 1250000:2.0 1250000:2.0 1250000:3.75 1250000:3.75 1250000:3.75 1250000:4.0 1250000:4.0 1250000:4.0 1250000:7.5 1250000:7.5 1250000:7.5'
EXPECTED_PLAN_COUNT=24
EXPOSURE_AXIS_COUNT=12
GAIN_AXIS_EXPOSURE=1250000

RUN_AUTOFOCUS=no
RUN_FACTORY_ASIC_RESET=no
USE_A1_AF_SHIM=no
USE_ASYNC_SHIM=yes

OUT=/data/local/tmp/light_l16_dark_frame_series.result
ARM_FILE=/data/local/tmp/light_l16_dark_frame_series.armed
ARM_VALUE=DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE
WORK_PREFIX=/data/local/tmp/light_l16_dark_frame_series_run
MODE=DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE
MASK0=FE
MASK1=FF
MASK2=01
SELECTION_DESCRIPTION='mask=FE FF 01 modules=A1-A5,B1-B5,C1-C6 asics=1,2,3 async_shim=required dark_frame_series=24_captures'
CAPTURE_TIMEOUT_SECONDS=60
MIN_DATA_FREE_KB=8388608
DIAGNOSTIC_LOG_LINES=2000
TUPLE0=11
TUPLE1=F1
TUPLE2=00
LCC_SOURCE=/system/etc/lcc
PROG_APP_SOURCE=/system/etc/prog_app_p2
HAL_SOURCE=/system/lib/hw/camera.msm8996.so
SHIM_SOURCE=/data/local/tmp/liblcc_async_writer_shim.so
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
EXPECTED_PROG_APP_SIZE=159664
EXPECTED_PROG_APP_SHA1=d6d74641759f2e208beac4318507ea1b71923db4
EXPECTED_HAL_SIZE=1338100
EXPECTED_HAL_SHA1=016602174e0635e79cda5566d5e850c1294a9300
EXPECTED_SHIM_SIZE=8904
EXPECTED_SHIM_SHA1=150e53a736624010dc7fb741490ea8dca7afbfb8

CAPTURE_ATTEMPTED=no
CAPTURES_REQUESTED=0
CAPTURES_COMPLETED=0
SERIES_ABORTED_AT=none
SERIES_ABORT_REASON=none
FINAL_STATUS=FAIL
FINAL_REASON=wrapper_did_not_finish
NORMAL_REBOOT_REQUIRED=no
CLEANUP_OK=no
WORKDIR=
LCC_COPY=
SHIM_COPY=
ASYNC_SHIM_STATUS=disabled
MANIFEST=
MANUAL_AFTER=unknown
SETTLED_CAMERA_CLIENTS=unknown
MEDIA_AFTER=unknown
LIGHTSVR_AFTER=unknown

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
    /system/bin/dmesg | /system/bin/toybox tail -n "$DIAGNOSTIC_LOG_LINES" \
        > "$WORKDIR/dmesg.$SUFFIX.txt" 2>&1
    /system/bin/logcat -d -v threadtime -t "$DIAGNOSTIC_LOG_LINES" \
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

# Independently re-derive the compiled plan.  A malformed plan is refused
# before the arm token is spent and before any device state is touched.
validate_plan() {
    PLAN_INDEX=0
    for PLAN_ENTRY in $CAPTURE_PLAN; do
        PLAN_INDEX=$((PLAN_INDEX + 1))
        PLAN_EXPOSURE=${PLAN_ENTRY%%:*}
        PLAN_GAIN=${PLAN_ENTRY##*:}
        case "$PLAN_EXPOSURE" in
            ""|*[!0-9]*) fail invalid_plan_exposure_value ;;
        esac
        [ "$PLAN_EXPOSURE" -ge 10000 ] || fail plan_exposure_below_10000ns
        [ "$PLAN_EXPOSURE" -le 20000000 ] || fail plan_exposure_above_20000000ns
        case "$PLAN_EXPOSURE" in
            10000|1250000|5000000|20000000) ;;
            *) fail invalid_plan_exposure_value ;;
        esac
        case "$PLAN_GAIN" in
            1.0|2.0|3.75|4.0|7.5) ;;
            *) fail invalid_plan_gain_value ;;
        esac
        if [ "$PLAN_INDEX" -le "$EXPOSURE_AXIS_COUNT" ]; then
            [ "$PLAN_GAIN" = "1.0" ] || fail exposure_axis_gain_not_one
        else
            [ "$PLAN_EXPOSURE" = "$GAIN_AXIS_EXPOSURE" ] || \
                fail gain_axis_exposure_not_1250000
        fi
    done
    [ "$PLAN_INDEX" -eq "$EXPECTED_PLAN_COUNT" ] || fail invalid_plan_entry_count
    CAPTURES_REQUESTED=$PLAN_INDEX
}

# Placeholder until the series and its reporting exist.  Replaced in the
# capture-series step; kept here so the trap below has a target.
finish() {
    ORIGINAL_STATUS=$?
    trap - EXIT HUP INT TERM
    clear_runner
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

printf 'mode=%s\n' "$MODE"
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


validate_plan
printf 'captures_requested=%s\n' "$CAPTURES_REQUESTED"
printf 'capture_plan=%s\n' "$CAPTURE_PLAN"
