#!/system/bin/sh
# SPDX-License-Identifier: MIT
# DANGER: after all fixed preconditions pass, this executes a fixed series of
# 24 lcc captures with the lens covered.  It is intentionally not a general
# camera or root wrapper.  The plan below is compiled in; the script accepts no
# arguments and no parameter is reachable from the app.

PATH=/sbin:/vendor/bin:/system/sbin:/system/bin:/system/xbin
export PATH

[ "$#" -eq 0 ] || {
    printf 'refusing unexpected arguments\n' >&2
    exit 2
}

RUN_AUTOFOCUS=no
RUN_FACTORY_ASIC_RESET=no
USE_A1_AF_SHIM=no
USE_ASYNC_SHIM=yes
MASK0=FE
MASK1=FF
MASK2=01

case "$0" in
    /data/local/tmp/light_l16_dark_frame_series_once.sh)
        # Exposure axis first at gain 1.0, ascending time; then the gain axis
        # at 1.25 ms, ascending gain.  Three repeats per cell.  The exposure
        # axis uses the already exercised gain 1.0, so a refusal on the
        # untested gain axis cannot cost the exposure measurement.
        CAPTURE_PLAN='10000:1.0 10000:1.0 10000:1.0 1250000:1.0 1250000:1.0 1250000:1.0 5000000:1.0 5000000:1.0 5000000:1.0 20000000:1.0 20000000:1.0 20000000:1.0 1250000:2.0 1250000:2.0 1250000:2.0 1250000:3.75 1250000:3.75 1250000:3.75 1250000:4.0 1250000:4.0 1250000:4.0 1250000:7.5 1250000:7.5 1250000:7.5'
        EXPECTED_PLAN_COUNT=24
        EXPOSURE_AXIS_COUNT=12
        GAIN_AXIS_EXPOSURE=1250000
        ALLOWED_EXPOSURES='10000 1250000 5000000 20000000'
        ALLOWED_GAINS='1.0 2.0 3.75 4.0 7.5'
        OUT=/data/local/tmp/light_l16_dark_frame_series.result
        ARM_FILE=/data/local/tmp/light_l16_dark_frame_series.armed
        ARM_VALUE=DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE
        WORK_PREFIX=/data/local/tmp/light_l16_dark_frame_series_run
        MODE=DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE
        SELECTION_DESCRIPTION='mask=FE FF 01 modules=A1-A5,B1-B5,C1-C6 asics=1,2,3 async_shim=required dark_frame_series=24_captures'
        CAPTURE_TIMEOUT_SECONDS=60
        MIN_DATA_FREE_KB=8388608
        ;;
    /data/local/tmp/light_l16_dark_frame_long_series_once.sh)
        # Long exposure axis at gain 1.0, ascending, to reach the dark current
        # the 20 ms series could not resolve.  The final cell repeats the
        # first: their difference measures the thermal drift accumulated over
        # the run, which is the term that made the short series' apparent
        # slope uninterpretable.
        CAPTURE_PLAN='100000000:1.0 100000000:1.0 100000000:1.0 1000000000:1.0 1000000000:1.0 1000000000:1.0 6000000000:1.0 6000000000:1.0 6000000000:1.0 29000000000:1.0 29000000000:1.0 29000000000:1.0 100000000:1.0 100000000:1.0 100000000:1.0'
        EXPECTED_PLAN_COUNT=15
        EXPOSURE_AXIS_COUNT=15
        GAIN_AXIS_EXPOSURE=0
        ALLOWED_EXPOSURES='100000000 1000000000 6000000000 29000000000'
        ALLOWED_GAINS='1.0'
        OUT=/data/local/tmp/light_l16_dark_frame_long_series.result
        ARM_FILE=/data/local/tmp/light_l16_dark_frame_long_series.armed
        ARM_VALUE=DARK_FRAME_LONG_SERIES_ALL16_15_CAPTURES_ONCE
        WORK_PREFIX=/data/local/tmp/light_l16_dark_frame_long_series_run
        MODE=DARK_FRAME_LONG_SERIES_ALL16_15_CAPTURES_ONCE
        SELECTION_DESCRIPTION='mask=FE FF 01 modules=A1-A5,B1-B5,C1-C6 asics=1,2,3 async_shim=required dark_frame_long_series=15_captures'
        # 29 s of integration plus readout and LRI writing; the 20 ms series
        # needed about 16 s per capture for everything but integration.
        CAPTURE_TIMEOUT_SECONDS=120
        MIN_DATA_FREE_KB=8388608
        ;;
    *)
        printf 'refusing unexpected invocation path: %s\n' "$0" >&2
        exit 2
        ;;
esac
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
        # Android 6 on this camera is 32-bit and its shell overflows on any
        # decimal above about 2.1e9: $((29000000000)) evaluates to
        # -1064771072, and even [ 20000000 -le 29981853000 ] is false
        # because the right-hand constant overflows.  Nanosecond bounds
        # therefore cannot be compared numerically at all.  Bound the digit
        # count instead, which is exact for decimal strings, and let the
        # compiled-in whitelist above enforce the individual values.
        [ "${#PLAN_EXPOSURE}" -ge 5 ] || fail plan_exposure_below_10000ns
        [ "${#PLAN_EXPOSURE}" -le 11 ] || fail plan_exposure_above_sensor_ceiling
        case " $ALLOWED_EXPOSURES " in
            *" $PLAN_EXPOSURE "*) ;;
            *) fail invalid_plan_exposure_value ;;
        esac
        case " $ALLOWED_GAINS " in
            *" $PLAN_GAIN "*) ;;
            *) fail invalid_plan_gain_value ;;
        esac
        if [ "$PLAN_INDEX" -le "$EXPOSURE_AXIS_COUNT" ]; then
            [ "$PLAN_GAIN" = "1.0" ] || fail exposure_axis_gain_not_one
        elif [ "$GAIN_AXIS_EXPOSURE" != "0" ]; then
            [ "$PLAN_EXPOSURE" = "$GAIN_AXIS_EXPOSURE" ] || \
                fail gain_axis_exposure_not_1250000
        fi
    done
    [ "$PLAN_INDEX" -eq "$EXPECTED_PLAN_COUNT" ] || fail invalid_plan_entry_count
    CAPTURES_REQUESTED=$PLAN_INDEX
}

# Between captures the series runs the same settle checks the single-capture
# wrapper performs once after its capture.  It deliberately does not reboot:
# 24 reboots would make the series impossible.  The first failed gate stops the
# series and keeps every frame written so far.
abort_series() {
    SERIES_ABORTED_AT=$1
    SERIES_ABORT_REASON=$2
    printf 'series_aborted_at=%s\n' "$SERIES_ABORTED_AT"
    printf 'series_abort_reason=%s\n' "$SERIES_ABORT_REASON"
}

settle_after_capture() {
    SETTLE_INDEX=$1
    force_manual_zero || {
        abort_series "$SETTLE_INDEX" manual_control_cleanup_failed
        return 1
    }
    if /system/bin/toybox pgrep -x lcc >/dev/null 2>&1; then
        abort_series "$SETTLE_INDEX" lcc_process_survived_capture
        return 1
    fi
    camera_clients_none "$WORKDIR/camera.after.$SETTLE_INDEX.txt" || {
        abort_series "$SETTLE_INDEX" camera_client_after_capture_or_state_unknown
        return 1
    }
    [ "$(getprop init.svc.media)" = "running" ] || {
        abort_series "$SETTLE_INDEX" media_stopped_after_capture
        return 1
    }
    [ "$(getprop init.svc.lightsvr)" = "running" ] || {
        abort_series "$SETTLE_INDEX" lightsvr_stopped_after_capture
        return 1
    }
    printf 'capture_%s_settled=yes\n' "$SETTLE_INDEX"
    return 0
}

# Attribute exactly one new LRI to this capture.  Zero means the HAL wrote
# nothing; more than one means the attribution is ambiguous.  Both stop the
# series rather than guessing which file belongs to which exposure.
record_capture_lri() {
    RECORD_INDEX=$1
    snapshot_lri_paths "$WORKDIR/lri.after.$RECORD_INDEX.txt" || {
        abort_series "$RECORD_INDEX" cannot_snapshot_lri_after
        return 1
    }
    : > "$WORKDIR/lri.new.$RECORD_INDEX.txt" || {
        abort_series "$RECORD_INDEX" cannot_create_lri_delta
        return 1
    }
    while IFS= read -r FILE; do
        [ -n "$FILE" ] || continue
        if ! path_in_snapshot "$FILE" "$WORKDIR/lri.before.$RECORD_INDEX.txt"
        then
            printf '%s\n' "$FILE" >> "$WORKDIR/lri.new.$RECORD_INDEX.txt" || {
                abort_series "$RECORD_INDEX" cannot_record_new_lri
                return 1
            }
        fi
    done < "$WORKDIR/lri.after.$RECORD_INDEX.txt"
    RECORD_COUNT=$(
        /system/bin/toybox wc -l < "$WORKDIR/lri.new.$RECORD_INDEX.txt"
    ) || {
        abort_series "$RECORD_INDEX" cannot_count_new_lri
        return 1
    }
    [ "$RECORD_COUNT" = "1" ] || {
        abort_series "$RECORD_INDEX" capture_lri_count_not_one
        return 1
    }
    RECORD_PATH=$(
        /system/bin/toybox sed -n '1p' "$WORKDIR/lri.new.$RECORD_INDEX.txt"
    ) || {
        abort_series "$RECORD_INDEX" cannot_read_new_lri_path
        return 1
    }
    valid_generated_lri_path "$RECORD_PATH" || {
        abort_series "$RECORD_INDEX" capture_lri_path_invalid
        return 1
    }
    RECORD_SIZE=$(/system/bin/toybox wc -c < "$RECORD_PATH") || {
        abort_series "$RECORD_INDEX" cannot_size_new_lri
        return 1
    }
    case "$RECORD_SIZE" in
        ""|*[!0-9]*)
            abort_series "$RECORD_INDEX" invalid_new_lri_size
            return 1
            ;;
    esac
    [ "$RECORD_SIZE" -ge 32 ] || {
        abort_series "$RECORD_INDEX" new_lri_too_small
        return 1
    }
    RECORD_SHA1=$(/system/bin/toybox sha1sum "$RECORD_PATH") || {
        abort_series "$RECORD_INDEX" cannot_hash_new_lri
        return 1
    }
    RECORD_SHA1=${RECORD_SHA1%% *}
    printf 'capture_%s_lri_path=%s\n' "$RECORD_INDEX" "$RECORD_PATH"
    printf 'capture_%s_lri_size=%s\n' "$RECORD_INDEX" "$RECORD_SIZE"
    printf 'capture_%s_lri_sha1=%s\n' "$RECORD_INDEX" "$RECORD_SHA1"
    printf '%s %s %s %s %s\n' "$RECORD_INDEX" "$CAPTURE_EXPOSURE" \
        "$CAPTURE_GAIN" "$RECORD_SIZE" "$RECORD_SHA1" >> "$MANIFEST"
    return 0
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
        if camera_clients_none "$WORKDIR/camera.final.txt"; then
            SETTLED_CAMERA_CLIENTS=none
        else
            SETTLED_CAMERA_CLIENTS=present_or_unknown
        fi
    fi

    LCC_REMAINS=no
    if /system/bin/toybox pgrep -x lcc >/dev/null 2>&1; then
        LCC_REMAINS=yes
    fi
    MANUAL_AFTER=unreadable
    if [ -r "$MANUAL_CONTROL" ]; then
        MANUAL_AFTER=$(cat "$MANUAL_CONTROL" 2>/dev/null)
    fi
    MEDIA_AFTER=$(getprop init.svc.media)
    LIGHTSVR_AFTER=$(getprop init.svc.lightsvr)

    if manual_is_zero && [ "$LCC_REMAINS" = "no" ] && \
        [ "$SETTLED_CAMERA_CLIENTS" = "none" ] && \
        [ "$MEDIA_AFTER" = "running" ] && [ "$LIGHTSVR_AFTER" = "running" ]
    then
        CLEANUP_OK=yes
    fi
    # A series that wrote frames but did not come back cleanly is not a
    # trustworthy PARTIAL: the frames are still listed, but the run is a FAIL.
    if [ "$CAPTURE_ATTEMPTED" = "yes" ] && [ "$CLEANUP_OK" != "yes" ]; then
        FINAL_STATUS=FAIL
        FINAL_REASON=post_series_cleanup_failed
    fi

    if [ -n "$LCC_COPY" ] && [ -f "$LCC_COPY" ]; then
        rm -f "$LCC_COPY"
    fi
    if [ "$USE_ASYNC_SHIM" = "yes" ]; then
        if [ -n "$SHIM_COPY" ] && [ -f "$SHIM_COPY" ]; then
            rm -f "$SHIM_COPY"
        fi
        rm -f "$SHIM_SOURCE"
    fi

    printf 'capture_attempted=%s\n' "$CAPTURE_ATTEMPTED"
    printf 'captures_requested=%s\n' "$CAPTURES_REQUESTED"
    printf 'captures_completed=%s\n' "$CAPTURES_COMPLETED"
    printf 'series_aborted_at=%s\n' "$SERIES_ABORTED_AT"
    printf 'series_abort_reason=%s\n' "$SERIES_ABORT_REASON"
    printf 'async_shim_status=%s\n' "$ASYNC_SHIM_STATUS"
    printf 'manual_control_after=%s\n' "$MANUAL_AFTER"
    printf 'lcc_process_after=%s\n' "$LCC_REMAINS"
    printf 'cleanup_ok=%s\n' "$CLEANUP_OK"
    printf 'settled_camera_clients=%s\n' "$SETTLED_CAMERA_CLIENTS"
    printf 'media_after=%s\n' "$MEDIA_AFTER"
    printf 'lightsvr_after=%s\n' "$LIGHTSVR_AFTER"
    printf 'normal_reboot_required=%s\n' "$NORMAL_REBOOT_REQUIRED"
    printf 'workdir=%s\n' "$WORKDIR"
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

if [ "$USE_ASYNC_SHIM" = "yes" ]; then
    ASYNC_SHIM_STATUS=required_unverified
    [ -r "$SHIM_SOURCE" ] || fail async_shim_missing
    SHIM_SIZE=$(/system/bin/toybox wc -c < "$SHIM_SOURCE") || \
        fail cannot_size_async_shim
    [ "$SHIM_SIZE" = "$EXPECTED_SHIM_SIZE" ] || fail unexpected_async_shim_size
    SHIM_SHA1=$(/system/bin/toybox sha1sum "$SHIM_SOURCE") || \
        fail cannot_hash_async_shim
    SHIM_SHA1=${SHIM_SHA1%% *}
    printf 'async_shim_size=%s async_shim_sha1=%s\n' "$SHIM_SIZE" "$SHIM_SHA1"
    [ "$SHIM_SHA1" = "$EXPECTED_SHIM_SHA1" ] || fail unexpected_async_shim_hash
fi

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

if [ "$USE_ASYNC_SHIM" = "yes" ]; then
    SHIM_COPY="$WORKDIR/liblcc_async_writer_shim.so"
    cp "$SHIM_SOURCE" "$SHIM_COPY" || fail cannot_copy_async_shim
    chmod 0400 "$SHIM_COPY" || fail cannot_secure_async_shim_copy
    SHIM_COPY_SHA1=$(/system/bin/toybox sha1sum "$SHIM_COPY") || \
        fail cannot_hash_async_shim_copy
    SHIM_COPY_SHA1=${SHIM_COPY_SHA1%% *}
    [ "$SHIM_COPY_SHA1" = "$EXPECTED_SHIM_SHA1" ] || \
        fail copied_async_shim_hash_mismatch
    printf 'async_shim_copy_sha1=%s\n' "$SHIM_COPY_SHA1"
fi

MANIFEST="$WORKDIR/series.manifest"
: > "$MANIFEST" || fail cannot_create_manifest

printf '%s\n' "$SELECTION_DESCRIPTION"
printf 'factory_tuple=%s %s %s\n' "$TUPLE0" "$TUPLE1" "$TUPLE2"
printf 'series_policy=settle_gate_between_captures_single_reboot_after_series\n'
printf 'outer_timeout_per_capture=TERM_after_%ss_KILL_after_5s\n' \
    "$CAPTURE_TIMEOUT_SECONDS"
printf 'hal_lri_directory=%s\n' "$LRI_DIR"

CAPTURE_INDEX=0
for PLAN_ENTRY in $CAPTURE_PLAN; do
    CAPTURE_INDEX=$((CAPTURE_INDEX + 1))
    CAPTURE_EXPOSURE=${PLAN_ENTRY%%:*}
    CAPTURE_GAIN=${PLAN_ENTRY##*:}
    printf 'capture_%s_exposure_ns=%s\n' "$CAPTURE_INDEX" "$CAPTURE_EXPOSURE"
    printf 'capture_%s_gain=%s\n' "$CAPTURE_INDEX" "$CAPTURE_GAIN"

    snapshot_lri_paths "$WORKDIR/lri.before.$CAPTURE_INDEX.txt" || {
        abort_series "$CAPTURE_INDEX" cannot_snapshot_lri_before
        break
    }

    # From this assignment onward a camera attempt has happened, so the
    # supervisor must reboot however the series ends.
    CAPTURE_ATTEMPTED=yes
    NORMAL_REBOOT_REQUIRED=yes

    set -- -m 0 -s 0 -f 1 "$MASK0" "$MASK1" "$MASK2" \
        "$TUPLE0" "$TUPLE1" "$TUPLE2" \
        -R 4160,3120 -e "$CAPTURE_EXPOSURE" -g "$CAPTURE_GAIN"
    (
        cd "$WORKDIR" || exit 126
        /system/bin/timeout -k 5s "${CAPTURE_TIMEOUT_SECONDS}s" \
            /system/bin/sh -c \
            'LD_PRELOAD=$1; export LD_PRELOAD; shift; exec "$@"' \
            l16-dark-frame-launch "$SHIM_COPY" "$LCC_COPY" "$@"
    ) > "$WORKDIR/lcc.$CAPTURE_INDEX.txt" 2>&1
    CAPTURE_LCC_STATUS=$?
    printf 'capture_%s_lcc_returned=%s\n' "$CAPTURE_INDEX" "$CAPTURE_LCC_STATUS"

    settle_after_capture "$CAPTURE_INDEX" || break
    record_capture_lri "$CAPTURE_INDEX" || break
    if [ "$CAPTURE_LCC_STATUS" != "0" ]; then
        abort_series "$CAPTURE_INDEX" capture_lcc_nonzero_or_timeout
        break
    fi
    CAPTURES_COMPLETED=$CAPTURE_INDEX
    printf 'capture_%s=ok\n' "$CAPTURE_INDEX"
done

ASYNC_SHIM_STATUS=exercised_per_capture
printf 'captures_completed=%s\n' "$CAPTURES_COMPLETED"

if [ "$CAPTURES_COMPLETED" -eq "$CAPTURES_REQUESTED" ]; then
    FINAL_STATUS=PASS
    FINAL_REASON=full_dark_frame_series_completed_settled_cleanup_content_not_validated
elif [ "$CAPTURES_COMPLETED" -gt 0 ]; then
    FINAL_STATUS=PARTIAL
    FINAL_REASON=series_aborted_after_completed_captures
else
    FINAL_STATUS=FAIL
    FINAL_REASON=series_produced_no_verified_capture
fi
exit 0
