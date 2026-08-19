#!/system/bin/sh
# SPDX-License-Identifier: MIT
# DANGER: after all fixed preconditions pass, this executes one fixed lcc
# capture. It is intentionally not a general camera or root wrapper. The exact
# installed path selects one of the eight compiled-in profiles below.

PATH=/sbin:/vendor/bin:/system/sbin:/system/bin:/system/xbin
export PATH

RUN_AUTOFOCUS=no
RUN_FACTORY_ASIC_RESET=no
USE_A1_AF_SHIM=no
USE_TIMEOUT_SHIM=no
EXPOSURE_COUNT=1
EXPOSURE_ARGS=20000000
EXPOSURE_ORDER=common_for_selected_modules
EXPOSURE_PLAN=selected:20000000
GAIN=1.0

case "$0" in
    /data/local/tmp/light_l16_a1_capture_once.sh)
        OUT=/data/local/tmp/light_l16_a1_capture.result
        ARM_FILE=/data/local/tmp/light_l16_a1_capture.armed
        ARM_VALUE=A1_CAPTURE_20000000NS_GAIN_1.0_ONCE
        WORK_PREFIX=/data/local/tmp/light_l16_a1_capture_run
        MODE=A1_FIXED_CAPTURE_20MS_ONCE
        MASK0=02
        MASK1=00
        MASK2=00
        SELECTION_DESCRIPTION='mask=02 00 00 module=A1 asic=1'
        CAPTURE_TIMEOUT_SECONDS=30
        MIN_DATA_FREE_KB=262144
        DIAGNOSTIC_LOG_LINES=2000
        ALLOW_CLEAN_NO_REBOOT=yes
        USE_ASYNC_SHIM=no
        ;;
    /data/local/tmp/light_l16_a1_center_af_capture_once.sh)
        OUT=/data/local/tmp/light_l16_a1_center_af_capture.result
        ARM_FILE=/data/local/tmp/light_l16_a1_center_af_capture.armed
        ARM_VALUE=A1_CENTER_AF_THEN_CAPTURE_20000000NS_GAIN_1.0_ONCE
        WORK_PREFIX=/data/local/tmp/light_l16_a1_center_af_capture_run
        MODE=A1_CENTER_AF_THEN_FIXED_CAPTURE_20MS_ONCE
        MASK0=02
        MASK1=00
        MASK2=00
        SELECTION_DESCRIPTION='mask=02 00 00 module=A1 asic=1 autofocus=center_50_percent'
        CAPTURE_TIMEOUT_SECONDS=30
        MIN_DATA_FREE_KB=262144
        DIAGNOSTIC_LOG_LINES=2000
        ALLOW_CLEAN_NO_REBOOT=no
        USE_ASYNC_SHIM=no
        RUN_AUTOFOCUS=yes
        RUN_FACTORY_ASIC_RESET=yes
        ;;
    /data/local/tmp/light_l16_a1_inline_af_capture_once.sh)
        OUT=/data/local/tmp/light_l16_a1_inline_af_capture.result
        ARM_FILE=/data/local/tmp/light_l16_a1_inline_af_capture.armed
        ARM_VALUE=A1_INLINE_AF_CAPTURE_20000000NS_GAIN_1.0_ONCE
        WORK_PREFIX=/data/local/tmp/light_l16_a1_inline_af_capture_run
        MODE=A1_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE
        MASK0=02
        MASK1=00
        MASK2=00
        SELECTION_DESCRIPTION='mask=02 00 00 module=A1 asic=1 inline_af_shim=required roi=center_50_percent'
        CAPTURE_TIMEOUT_SECONDS=45
        MIN_DATA_FREE_KB=262144
        DIAGNOSTIC_LOG_LINES=2000
        ALLOW_CLEAN_NO_REBOOT=no
        USE_ASYNC_SHIM=no
        USE_A1_AF_SHIM=yes
        ;;
    /data/local/tmp/light_l16_a_group_inline_af_capture_once.sh)
        OUT=/data/local/tmp/light_l16_a_group_inline_af_capture.result
        ARM_FILE=/data/local/tmp/light_l16_a_group_inline_af_capture.armed
        ARM_VALUE=A_GROUP_INLINE_AF_CAPTURE_20000000NS_GAIN_1.0_ONCE
        WORK_PREFIX=/data/local/tmp/light_l16_a_group_inline_af_capture_run
        MODE=A_GROUP_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE
        MASK0=3E
        MASK1=00
        MASK2=00
        SELECTION_DESCRIPTION='mask=3E 00 00 modules=A1-A5 asics=1,2 inline_af_shim=required roi=center_50_percent'
        CAPTURE_TIMEOUT_SECONDS=60
        MIN_DATA_FREE_KB=524288
        DIAGNOSTIC_LOG_LINES=2000
        ALLOW_CLEAN_NO_REBOOT=no
        USE_ASYNC_SHIM=no
        USE_A1_AF_SHIM=yes
        ;;
    /data/local/tmp/light_l16_a1_async_capture_once.sh)
        OUT=/data/local/tmp/light_l16_a1_async_capture.result
        ARM_FILE=/data/local/tmp/light_l16_a1_async_capture.armed
        ARM_VALUE=A1_ASYNC_SHIM_CAPTURE_20000000NS_GAIN_1.0_ONCE
        WORK_PREFIX=/data/local/tmp/light_l16_a1_async_capture_run
        MODE=A1_ASYNC_SHIM_FIXED_CAPTURE_20MS_ONCE
        MASK0=02
        MASK1=00
        MASK2=00
        SELECTION_DESCRIPTION='mask=02 00 00 module=A1 asic=1 async_shim=required'
        CAPTURE_TIMEOUT_SECONDS=30
        MIN_DATA_FREE_KB=262144
        DIAGNOSTIC_LOG_LINES=2000
        ALLOW_CLEAN_NO_REBOOT=no
        USE_ASYNC_SHIM=yes
        ;;
    /data/local/tmp/light_l16_all16_capture_once.sh)
        OUT=/data/local/tmp/light_l16_all16_capture.result
        ARM_FILE=/data/local/tmp/light_l16_all16_capture.armed
        ARM_VALUE=ALL16_CAPTURE_20000000NS_GAIN_1.0_ONCE
        WORK_PREFIX=/data/local/tmp/light_l16_all16_capture_run
        MODE=ALL16_FIXED_CAPTURE_20MS_ONCE
        MASK0=FE
        MASK1=FF
        MASK2=01
        SELECTION_DESCRIPTION='mask=FE FF 01 modules=A1-A5,B1-B5,C1-C6 asics=1,2,3'
        CAPTURE_TIMEOUT_SECONDS=60
        MIN_DATA_FREE_KB=1048576
        DIAGNOSTIC_LOG_LINES=2000
        ALLOW_CLEAN_NO_REBOOT=no
        USE_ASYNC_SHIM=no
        ;;
    /data/local/tmp/light_l16_all16_async_capture_once.sh)
        OUT=/data/local/tmp/light_l16_all16_async_capture.result
        ARM_FILE=/data/local/tmp/light_l16_all16_async_capture.armed
        ARM_VALUE=ALL16_ASYNC_SHIM_CAPTURE_20000000NS_GAIN_1.0_ONCE
        WORK_PREFIX=/data/local/tmp/light_l16_all16_async_capture_run
        MODE=ALL16_ASYNC_SHIM_FIXED_CAPTURE_20MS_ONCE
        MASK0=FE
        MASK1=FF
        MASK2=01
        SELECTION_DESCRIPTION='mask=FE FF 01 modules=A1-A5,B1-B5,C1-C6 asics=1,2,3 async_shim=required'
        CAPTURE_TIMEOUT_SECONDS=60
        MIN_DATA_FREE_KB=1048576
        DIAGNOSTIC_LOG_LINES=2000
        ALLOW_CLEAN_NO_REBOOT=no
        USE_ASYNC_SHIM=yes
        ;;
    /data/local/tmp/light_l16_timeout_probe_once.sh)
        OUT=/data/local/tmp/light_l16_timeout_probe.result
        ARM_FILE=/data/local/tmp/light_l16_timeout_probe.armed
        ARM_VALUE=TIMEOUT_PROBE_ALL16_8000000000NS_GAIN_1.0_ONCE
        WORK_PREFIX=/data/local/tmp/light_l16_timeout_probe_run
        MODE=TIMEOUT_PROBE_ALL16_8S_ONCE
        MASK0=FE
        MASK1=FF
        MASK2=01
        SELECTION_DESCRIPTION='mask=FE FF 01 modules=A1-A5,B1-B5,C1-C6 asics=1,2,3 async_shim=required timeout_shim=required probe=8s'
        # 8 s of integration plus readout and the LRI write.  The stock
        # completion budget would be 15 s and the run fails around 6 s; the
        # timeout shim raises it, and this outer bound still cuts a hung
        # pipeline short from outside.
        CAPTURE_TIMEOUT_SECONDS=180
        MIN_DATA_FREE_KB=1048576
        DIAGNOSTIC_LOG_LINES=2000
        ALLOW_CLEAN_NO_REBOOT=no
        USE_ASYNC_SHIM=no
        USE_TIMEOUT_SHIM=yes
        EXPOSURE_COUNT=1
        EXPOSURE_ARGS=8000000000
        EXPOSURE_ORDER=common_for_selected_modules
        EXPOSURE_PLAN=selected:8000000000
        ;;
    /data/local/tmp/light_l16_timeout_probe_6s_once.sh)
        OUT=/data/local/tmp/light_l16_timeout_probe_6s.result
        ARM_FILE=/data/local/tmp/light_l16_timeout_probe_6s.armed
        ARM_VALUE=TIMEOUT_PROBE_ALL16_6000000000NS_GAIN_1.0_ONCE
        WORK_PREFIX=/data/local/tmp/light_l16_timeout_probe_6s_run
        MODE=TIMEOUT_PROBE_ALL16_6S_ONCE
        MASK0=FE
        MASK1=FF
        MASK2=01
        SELECTION_DESCRIPTION='mask=FE FF 01 modules=A1-A5,B1-B5,C1-C6 asics=1,2,3 async_shim=required timeout_shim=required probe=6s'
        # The narrowest test of the shim.  lcc derives thread_time_out as
        # (uint)(max_capture_delay + exposure_s) + 1, which carries no readout
        # term, and the HAL turns anything at or below 9 into a flat 15 s
        # budget.  Reading all sixteen modules takes about 14 s, so 1 s of
        # integration still completes and 6 s does not.  If the shim works,
        # this exposure is the first that must pass.
        CAPTURE_TIMEOUT_SECONDS=180
        MIN_DATA_FREE_KB=1048576
        DIAGNOSTIC_LOG_LINES=2000
        ALLOW_CLEAN_NO_REBOOT=no
        USE_ASYNC_SHIM=no
        USE_TIMEOUT_SHIM=yes
        EXPOSURE_COUNT=1
        EXPOSURE_ARGS=6000000000
        EXPOSURE_ORDER=common_for_selected_modules
        EXPOSURE_PLAN=selected:6000000000
        ;;
    /data/local/tmp/light_l16_all16_hdr_async_capture_once.sh)
        OUT=/data/local/tmp/light_l16_all16_hdr_async_capture.result
        ARM_FILE=/data/local/tmp/light_l16_all16_hdr_async_capture.armed
        ARM_VALUE=ALL16_HDR_ASYNC_SHIM_CAPTURE_1250000_5000000_20000000NS_GAIN_1.0_ONCE
        WORK_PREFIX=/data/local/tmp/light_l16_all16_hdr_async_capture_run
        MODE=ALL16_HDR_ASYNC_SHIM_SINGLE_REQUEST_1P25_5_20MS_ONCE
        MASK0=FE
        MASK1=FF
        MASK2=01
        SELECTION_DESCRIPTION='mask=FE FF 01 modules=A1-A5,B1-B5,C1-C6 asics=1,2,3 async_shim=required hdr=single_request'
        CAPTURE_TIMEOUT_SECONDS=60
        MIN_DATA_FREE_KB=1048576
        DIAGNOSTIC_LOG_LINES=2000
        ALLOW_CLEAN_NO_REBOOT=no
        USE_ASYNC_SHIM=yes
        EXPOSURE_COUNT=16
        EXPOSURE_ARGS='1250000 20000000 5000000 5000000 20000000 20000000 5000000 5000000 1250000 20000000 20000000 5000000 5000000 20000000 1250000 20000000'
        EXPOSURE_ORDER=A1,A2,A3,A4,A5,B1,B2,B3,B4,B5,C1,C2,C3,C4,C5,C6
        EXPOSURE_PLAN=A1:1250000,A2:20000000,A3:5000000,A4:5000000,A5:20000000,B1:20000000,B2:5000000,B3:5000000,B4:1250000,B5:20000000,C1:20000000,C2:5000000,C3:5000000,C4:20000000,C5:1250000,C6:20000000
        ;;
    *)
        printf 'refusing unexpected invocation path: %s\n' "$0" >&2
        exit 2
        ;;
esac

AUTOFOCUS_X=1040
AUTOFOCUS_Y=780
AUTOFOCUS_WIDTH=2080
AUTOFOCUS_HEIGHT=1560
AUTOFOCUS_TIMEOUT_SECONDS=30
TUPLE0=11
TUPLE1=F1
TUPLE2=00
LCC_SOURCE=/system/etc/lcc
PROG_APP_SOURCE=/system/etc/prog_app_p2
HAL_SOURCE=/system/lib/hw/camera.msm8996.so
SHIM_SOURCE=/data/local/tmp/liblcc_async_writer_shim.so
AF_SHIM_SOURCE=/data/local/tmp/liblcc_a1_focus_capture_shim.so
TIMEOUT_SHIM_SOURCE=/data/local/tmp/liblcc_async_timeout_shim.so
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
EXPECTED_TIMEOUT_SHIM_SIZE=9904
EXPECTED_TIMEOUT_SHIM_SHA1=243e6419be6c6e06e4cb21c5204c74339e79985f
EXPECTED_AF_SHIM_SIZE=13764
EXPECTED_AF_SHIM_SHA1=67647b71767ab2b68a214fae87578e24eb3433b2

CAPTURE_ATTEMPTED=no
ASIC_RESET_ATTEMPTED=no
ASIC_RESET_STATUS=not_run
ASIC_READY_ATTEMPTED=no
ASIC_READY_STATUS=not_run
ASIC_READY_RESPONSE=not_run
ASIC_POWER_OFF_ATTEMPTED=no
ASIC_POWER_OFF_STATUS=not_run
AUTOFOCUS_ATTEMPTED=no
AUTOFOCUS_STATUS=not_run
AUTOFOCUS_RESPONSE=not_run
AUTOFOCUS_TID_BEFORE=
AUTOFOCUS_TID_AFTER=
AUTOFOCUS_RESPONSE_PATH=
AUTOFOCUS_RESPONSE_OWNED=no
AUTOFOCUS_RESPONSE_SIZE=unknown
AUTOFOCUS_RESPONSE_SHA1=
FINAL_STATUS=FAIL
FINAL_REASON=wrapper_did_not_finish
LCC_STATUS=not_run
NORMAL_REBOOT_REQUIRED=no
CLEANUP_OK=no
WORKDIR=
LCC_COPY=
PROG_APP_COPY=
SHIM_COPY=
AF_SHIM_COPY=
TIMEOUT_SHIM_COPY=
TIMEOUT_SHIM_STATUS=disabled
ASYNC_SHIM_STATUS=disabled
A1_AF_SHIM_STATUS=disabled
LRI_OUTPUT_COUNT=unknown
LRI_OUTPUT_PATH=
LRI_OUTPUT_SIZE=unknown
LRI_OUTPUT_SHA1=
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

read_decimal_tid() {
    TID_TEXT=$(cat /data/tid.txt 2>/dev/null) || return 1
    set -- $TID_TEXT
    [ "$#" -eq 1 ] || return 1
    case "$1" in
        ""|*[!0-9]*) return 1 ;;
    esac
    printf '%s\n' "$1"
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

finish() {
    ORIGINAL_STATUS=$?
    trap - EXIT HUP INT TERM

    clear_runner
    if [ "$ASIC_RESET_ATTEMPTED" = "yes" ] || \
        [ "$CAPTURE_ATTEMPTED" = "yes" ] || \
        [ "$AUTOFOCUS_ATTEMPTED" = "yes" ]; then
        NORMAL_REBOOT_REQUIRED=yes
        force_manual_zero || true
        /system/bin/sleep 1
    fi

    # The factory reset profile powers all three ASICs into their normal boot
    # mode.  Drive the same reset/power GPIOs low through prog_app_p2's fixed
    # -F branch before collecting slower diagnostics.  A normal Android reboot
    # remains mandatory even when this bounded cleanup succeeds.
    if [ "$ASIC_RESET_ATTEMPTED" = "yes" ]; then
        ASIC_POWER_OFF_ATTEMPTED=yes
        if [ -n "$PROG_APP_COPY" ] && [ -x "$PROG_APP_COPY" ] && \
            ! /system/bin/toybox pgrep -x prog_app_p2 >/dev/null 2>&1
        then
            (
                cd "$WORKDIR" || exit 126
                /system/bin/timeout -k 2s 10s "$PROG_APP_COPY" -F
            ) > "$WORKDIR/prog_app.poweroff.txt" 2>&1
            ASIC_POWER_OFF_STATUS=$?
        else
            ASIC_POWER_OFF_STATUS=precondition_failed
        fi
        /system/bin/sleep 1
    fi

    capture_diagnostics after
    if [ -n "$WORKDIR" ] && [ -d "$WORKDIR" ]; then
        if camera_clients_none "$WORKDIR/camera.after.txt"; then
            SETTLED_CAMERA_CLIENTS=none
        else
            SETTLED_CAMERA_CLIENTS=present_or_unknown
        fi
    fi

    LCC_REMAINS=no
    if /system/bin/toybox pgrep -x lcc >/dev/null 2>&1; then
        LCC_REMAINS=yes
    fi
    PROG_APP_REMAINS=no
    if /system/bin/toybox pgrep -x prog_app_p2 >/dev/null 2>&1; then
        PROG_APP_REMAINS=yes
    fi
    MANUAL_AFTER=unreadable
    if [ -r "$MANUAL_CONTROL" ]; then
        MANUAL_AFTER=$(cat "$MANUAL_CONTROL" 2>/dev/null)
    fi

    MEDIA_AFTER=$(getprop init.svc.media)
    LIGHTSVR_AFTER=$(getprop init.svc.lightsvr)
    ASIC_CLEANUP_OK=yes
    if [ "$ASIC_RESET_ATTEMPTED" = "yes" ] && \
        { [ "$ASIC_POWER_OFF_STATUS" != "0" ] || \
          [ "$PROG_APP_REMAINS" != "no" ]; }
    then
        ASIC_CLEANUP_OK=no
    fi
    if manual_is_zero && [ "$LCC_REMAINS" = "no" ] && \
        [ "$ASIC_CLEANUP_OK" = "yes" ] && \
        [ "$SETTLED_CAMERA_CLIENTS" = "none" ] && \
        [ "$MEDIA_AFTER" = "running" ] && [ "$LIGHTSVR_AFTER" = "running" ]
    then
        CLEANUP_OK=yes
    fi
    if { [ "$ASIC_RESET_ATTEMPTED" = "yes" ] || \
         [ "$CAPTURE_ATTEMPTED" = "yes" ] || \
         [ "$AUTOFOCUS_ATTEMPTED" = "yes" ]; } && \
        [ "$CLEANUP_OK" != "yes" ]; then
        FINAL_STATUS=FAIL
        FINAL_REASON=post_capture_cleanup_failed
    fi

    if [ -n "$LCC_COPY" ] && [ -f "$LCC_COPY" ]; then
        rm -f "$LCC_COPY"
    fi
    if [ -n "$PROG_APP_COPY" ] && [ -f "$PROG_APP_COPY" ]; then
        rm -f "$PROG_APP_COPY"
    fi
    if [ "$USE_ASYNC_SHIM" = "yes" ]; then
        if [ -n "$SHIM_COPY" ] && [ -f "$SHIM_COPY" ]; then
            rm -f "$SHIM_COPY"
        fi
        rm -f "$SHIM_SOURCE"
    fi
    if [ "$USE_TIMEOUT_SHIM" = "yes" ]; then
        if [ -n "$TIMEOUT_SHIM_COPY" ] && [ -f "$TIMEOUT_SHIM_COPY" ]; then
            rm -f "$TIMEOUT_SHIM_COPY"
        fi
        rm -f "$TIMEOUT_SHIM_SOURCE"
    fi
    if [ "$USE_A1_AF_SHIM" = "yes" ]; then
        if [ -n "$AF_SHIM_COPY" ] && [ -f "$AF_SHIM_COPY" ]; then
            rm -f "$AF_SHIM_COPY"
        fi
        rm -f "$AF_SHIM_SOURCE"
    fi
    if [ "$AUTOFOCUS_RESPONSE_OWNED" = "yes" ] && \
        [ -n "$AUTOFOCUS_RESPONSE_PATH" ]; then
        case "$AUTOFOCUS_RESPONSE_PATH" in
            /data/lcc_output_[0-9a-f][0-9a-f][0-9a-f][0-9a-f].txt)
                rm -f "$AUTOFOCUS_RESPONSE_PATH"
                ;;
        esac
    fi

    # A clean, normally returned lcc process has now closed the HAL, remained
    # absent for the settle interval, released CameraService, and restored the
    # manual-control gate.  Only that exact PASS path may continue without a
    # reboot; every timeout, signal, failure, or ambiguous state keeps the
    # fail-safe reboot requirement.
    if [ "$ALLOW_CLEAN_NO_REBOOT" = "yes" ] && \
        [ "$ORIGINAL_STATUS" = "0" ] && [ "$CAPTURE_ATTEMPTED" = "yes" ] && \
        [ "$FINAL_STATUS" = "PASS" ] && [ "$LCC_STATUS" = "0" ] && \
        [ "$LRI_OUTPUT_COUNT" = "1" ] && [ "$CLEANUP_OK" = "yes" ]
    then
        NORMAL_REBOOT_REQUIRED=no
    fi

    printf 'capture_attempted=%s\n' "$CAPTURE_ATTEMPTED"
    printf 'asic_reset_attempted=%s\n' "$ASIC_RESET_ATTEMPTED"
    printf 'asic_reset_exit_status=%s\n' "$ASIC_RESET_STATUS"
    printf 'asic_ready_attempted=%s\n' "$ASIC_READY_ATTEMPTED"
    printf 'asic_ready_exit_status=%s\n' "$ASIC_READY_STATUS"
    printf 'asic_ready_response=%s\n' "$ASIC_READY_RESPONSE"
    printf 'asic_power_off_attempted=%s\n' "$ASIC_POWER_OFF_ATTEMPTED"
    printf 'asic_power_off_exit_status=%s\n' "$ASIC_POWER_OFF_STATUS"
    printf 'autofocus_attempted=%s\n' "$AUTOFOCUS_ATTEMPTED"
    printf 'autofocus_exit_status=%s\n' "$AUTOFOCUS_STATUS"
    printf 'autofocus_response=%s\n' "$AUTOFOCUS_RESPONSE"
    printf 'autofocus_tid_before=%s\n' "$AUTOFOCUS_TID_BEFORE"
    printf 'autofocus_tid_after=%s\n' "$AUTOFOCUS_TID_AFTER"
    printf 'autofocus_response_size=%s\n' "$AUTOFOCUS_RESPONSE_SIZE"
    printf 'autofocus_response_sha1=%s\n' "$AUTOFOCUS_RESPONSE_SHA1"
    printf 'lcc_exit_status=%s\n' "$LCC_STATUS"
    printf 'manual_control_after=%s\n' "$MANUAL_AFTER"
    printf 'lcc_process_after=%s\n' "$LCC_REMAINS"
    printf 'prog_app_process_after=%s\n' "$PROG_APP_REMAINS"
    printf 'cleanup_ok=%s\n' "$CLEANUP_OK"
    printf 'settled_camera_clients=%s\n' "$SETTLED_CAMERA_CLIENTS"
    printf 'media_after=%s\n' "$MEDIA_AFTER"
    printf 'lightsvr_after=%s\n' "$LIGHTSVR_AFTER"
    printf 'normal_reboot_required=%s\n' "$NORMAL_REBOOT_REQUIRED"
    printf 'async_shim=%s\n' "$ASYNC_SHIM_STATUS"
    printf 'timeout_shim=%s\n' "$TIMEOUT_SHIM_STATUS"
    printf 'a1_af_shim=%s\n' "$A1_AF_SHIM_STATUS"
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

if [ "$RUN_FACTORY_ASIC_RESET" = "yes" ]; then
    [ -r "$PROG_APP_SOURCE" ] || fail prog_app_missing
    PROG_APP_SIZE=$(/system/bin/toybox wc -c < "$PROG_APP_SOURCE") || \
        fail cannot_size_prog_app
    [ "$PROG_APP_SIZE" = "$EXPECTED_PROG_APP_SIZE" ] || \
        fail unexpected_prog_app_size
    PROG_APP_SHA1=$(/system/bin/toybox sha1sum "$PROG_APP_SOURCE") || \
        fail cannot_hash_prog_app
    PROG_APP_SHA1=${PROG_APP_SHA1%% *}
    printf 'prog_app_size=%s prog_app_sha1=%s\n' \
        "$PROG_APP_SIZE" "$PROG_APP_SHA1"
    [ "$PROG_APP_SHA1" = "$EXPECTED_PROG_APP_SHA1" ] || \
        fail unexpected_prog_app_hash
fi

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

if [ "$USE_TIMEOUT_SHIM" = "yes" ]; then
    TIMEOUT_SHIM_STATUS=required_unverified
    [ -r "$TIMEOUT_SHIM_SOURCE" ] || fail timeout_shim_missing
    TIMEOUT_SHIM_SIZE=$(/system/bin/toybox wc -c < "$TIMEOUT_SHIM_SOURCE") || \
        fail cannot_size_timeout_shim
    [ "$TIMEOUT_SHIM_SIZE" = "$EXPECTED_TIMEOUT_SHIM_SIZE" ] || \
        fail unexpected_timeout_shim_size
    TIMEOUT_SHIM_SHA1=$(/system/bin/toybox sha1sum "$TIMEOUT_SHIM_SOURCE") || \
        fail cannot_hash_timeout_shim
    TIMEOUT_SHIM_SHA1=${TIMEOUT_SHIM_SHA1%% *}
    printf 'timeout_shim_size=%s timeout_shim_sha1=%s\n' \
        "$TIMEOUT_SHIM_SIZE" "$TIMEOUT_SHIM_SHA1"
    [ "$TIMEOUT_SHIM_SHA1" = "$EXPECTED_TIMEOUT_SHIM_SHA1" ] || \
        fail unexpected_timeout_shim_hash
fi

if [ "$USE_A1_AF_SHIM" = "yes" ]; then
    A1_AF_SHIM_STATUS=required_unverified
    [ -r "$AF_SHIM_SOURCE" ] || fail a1_af_shim_missing
    AF_SHIM_SIZE=$(/system/bin/toybox wc -c < "$AF_SHIM_SOURCE") || \
        fail cannot_size_a1_af_shim
    [ "$AF_SHIM_SIZE" = "$EXPECTED_AF_SHIM_SIZE" ] || \
        fail unexpected_a1_af_shim_size
    AF_SHIM_SHA1=$(/system/bin/toybox sha1sum "$AF_SHIM_SOURCE") || \
        fail cannot_hash_a1_af_shim
    AF_SHIM_SHA1=${AF_SHIM_SHA1%% *}
    printf 'a1_af_shim_size=%s a1_af_shim_sha1=%s\n' \
        "$AF_SHIM_SIZE" "$AF_SHIM_SHA1"
    [ "$AF_SHIM_SHA1" = "$EXPECTED_AF_SHIM_SHA1" ] || \
        fail unexpected_a1_af_shim_hash
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

if [ "$RUN_FACTORY_ASIC_RESET" = "yes" ]; then
    PROG_APP_COPY="$WORKDIR/prog_app_p2"
    cp "$PROG_APP_SOURCE" "$PROG_APP_COPY" || fail cannot_copy_prog_app
    chmod 0700 "$PROG_APP_COPY" || fail cannot_make_prog_app_executable
    PROG_APP_COPY_SHA1=$(
        /system/bin/toybox sha1sum "$PROG_APP_COPY"
    ) || fail cannot_hash_prog_app_copy
    PROG_APP_COPY_SHA1=${PROG_APP_COPY_SHA1%% *}
    [ "$PROG_APP_COPY_SHA1" = "$EXPECTED_PROG_APP_SHA1" ] || \
        fail copied_prog_app_hash_mismatch
    printf 'prog_app_copy_sha1=%s\n' "$PROG_APP_COPY_SHA1"
fi

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

if [ "$USE_TIMEOUT_SHIM" = "yes" ]; then
    TIMEOUT_SHIM_COPY="$WORKDIR/liblcc_async_timeout_shim.so"
    cp "$TIMEOUT_SHIM_SOURCE" "$TIMEOUT_SHIM_COPY" || fail cannot_copy_timeout_shim
    chmod 0400 "$TIMEOUT_SHIM_COPY" || fail cannot_secure_timeout_shim_copy
    TIMEOUT_SHIM_COPY_SHA1=$(/system/bin/toybox sha1sum "$TIMEOUT_SHIM_COPY") || \
        fail cannot_hash_timeout_shim_copy
    TIMEOUT_SHIM_COPY_SHA1=${TIMEOUT_SHIM_COPY_SHA1%% *}
    [ "$TIMEOUT_SHIM_COPY_SHA1" = "$EXPECTED_TIMEOUT_SHIM_SHA1" ] || \
        fail copied_timeout_shim_hash_mismatch
    printf 'timeout_shim_copy_sha1=%s\n' "$TIMEOUT_SHIM_COPY_SHA1"
fi

if [ "$USE_A1_AF_SHIM" = "yes" ]; then
    AF_SHIM_COPY="$WORKDIR/liblcc_a1_focus_capture_shim.so"
    cp "$AF_SHIM_SOURCE" "$AF_SHIM_COPY" || fail cannot_copy_a1_af_shim
    chmod 0400 "$AF_SHIM_COPY" || fail cannot_secure_a1_af_shim_copy
    AF_SHIM_COPY_SHA1=$(/system/bin/toybox sha1sum "$AF_SHIM_COPY") || \
        fail cannot_hash_a1_af_shim_copy
    AF_SHIM_COPY_SHA1=${AF_SHIM_COPY_SHA1%% *}
    [ "$AF_SHIM_COPY_SHA1" = "$EXPECTED_AF_SHIM_SHA1" ] || \
        fail copied_a1_af_shim_hash_mismatch
    printf 'a1_af_shim_copy_sha1=%s\n' "$AF_SHIM_COPY_SHA1"
fi

if [ "$RUN_AUTOFOCUS" = "yes" ]; then
    [ "$RUN_FACTORY_ASIC_RESET" = "yes" ] || \
        fail autofocus_requires_factory_asic_reset
    AUTOFOCUS_TID_BEFORE=$(read_decimal_tid) || \
        fail cannot_read_autofocus_tid_before
    EXPECTED_AUTOFOCUS_TID=$((AUTOFOCUS_TID_BEFORE + 1))
    [ "$EXPECTED_AUTOFOCUS_TID" -le 65535 ] || fail autofocus_tid_would_wrap
    AUTOFOCUS_RESPONSE_PATH=$(
        /system/bin/printf '/data/lcc_output_%04x.txt' "$EXPECTED_AUTOFOCUS_TID"
    ) || fail cannot_format_autofocus_response_path
    case "$AUTOFOCUS_RESPONSE_PATH" in
        /data/lcc_output_[0-9a-f][0-9a-f][0-9a-f][0-9a-f].txt) ;;
        *) fail unexpected_autofocus_response_path ;;
    esac
    [ ! -e "$AUTOFOCUS_RESPONSE_PATH" ] || \
        fail autofocus_response_path_already_exists

    # Factory actuator tests first place all three ASICs in normal boot mode
    # through prog_app_p2 -q. Static analysis of this exact binary confirms
    # that the -q branch only selects normal strap GPIOs and toggles the three
    # ASIC reset GPIOs; it returns before configuration, SPI, erase, write, or
    # firmware paths. This is nevertheless an all-ASIC hardware reset, so any
    # attempt mandates both the fixed -F cleanup below and an Android reboot.
    printf '%s\n' 'asic_reset_scope=all_three_asics_normal_mode_nonflashing'
    printf '%s\n' 'asic_reset_executed_argv=<verified-prog-app-copy> -q'
    ASIC_RESET_ATTEMPTED=yes
    NORMAL_REBOOT_REQUIRED=yes
    (
        cd "$WORKDIR" || exit 126
        /system/bin/timeout -k 2s 10s "$PROG_APP_COPY" -q
    ) > "$WORKDIR/prog_app.reset.txt" 2>&1
    ASIC_RESET_STATUS=$?
    printf 'asic_reset_returned=%s\n' "$ASIC_RESET_STATUS"
    [ "$ASIC_RESET_STATUS" = "0" ] || fail asic_normal_reset_nonzero_or_timeout
    if /system/bin/toybox pgrep -x prog_app_p2 >/dev/null 2>&1; then
        fail prog_app_process_after_asic_reset
    fi
    /system/bin/sleep 1

    # This is the stock boot script's read-only readiness request. It expects
    # a ten-byte response (eight-byte header plus two data bytes); byte zero of
    # the returned payload must be 0x01 before an actuator command is allowed.
    ASIC_READY_ATTEMPTED=yes
    printf '%s\n' \
        'asic_ready_executed_argv=<verified-lcc-copy> -m 0 -s 0 -r -p 12 34 15 02'
    (
        cd "$WORKDIR" || exit 126
        /system/bin/timeout -k 2s 10s "$LCC_COPY" \
            -m 0 -s 0 -r -p 12 34 15 02
    ) > "$WORKDIR/lcc.asic-ready.txt" 2>&1
    ASIC_READY_STATUS=$?
    printf 'asic_ready_returned=%s\n' "$ASIC_READY_STATUS"
    [ "$ASIC_READY_STATUS" = "0" ] || \
        fail asic_ready_nonzero_or_timeout
    ASIC_READY_OK_COUNT=$(
        /system/bin/toybox grep -c '^01 [0-9A-F][0-9A-F] *$' \
            "$WORKDIR/lcc.asic-ready.txt"
    )
    [ "$ASIC_READY_OK_COUNT" = "1" ] || \
        fail unexpected_asic_ready_response
    ASIC_READY_RESPONSE=ready_01
    if /system/bin/toybox pgrep -x lcc >/dev/null 2>&1; then
        fail lcc_process_after_asic_ready
    fi
    if /system/bin/toybox grep -qi ':1388' \
        /proc/net/udp /proc/net/udp6 2>/dev/null; then
        fail udp_port_5000_after_asic_ready
    fi
    camera_clients_none "$WORKDIR/camera.after_asic_ready.txt" || \
        fail camera_client_after_asic_ready_or_state_unknown
    printf 'asic_ready_verified=yes\n'

    printf 'autofocus_mask=%s %s %s\n' "$MASK0" "$MASK1" "$MASK2"
    printf 'autofocus_roi=%s,%s,%s,%s\n' \
        "$AUTOFOCUS_X" "$AUTOFOCUS_Y" \
        "$AUTOFOCUS_WIDTH" "$AUTOFOCUS_HEIGHT"
    printf 'autofocus_executed_argv=<verified-lcc-copy> -m 0 -s 0 -V -C -H -f 0 %s %s %s %s %s %s %s\n' \
        "$MASK0" "$MASK1" "$MASK2" \
        "$AUTOFOCUS_X" "$AUTOFOCUS_Y" \
        "$AUTOFOCUS_WIDTH" "$AUTOFOCUS_HEIGHT"
    printf 'autofocus_outer_timeout=TERM_after_%ss_KILL_after_5s\n' \
        "$AUTOFOCUS_TIMEOUT_SECONDS"

    AUTOFOCUS_ATTEMPTED=yes
    NORMAL_REBOOT_REQUIRED=yes
    (
        cd "$WORKDIR" || exit 126
        /system/bin/timeout -k 5s "${AUTOFOCUS_TIMEOUT_SECONDS}s" \
            "$LCC_COPY" -m 0 -s 0 -V -C -H -f 0 \
            "$MASK0" "$MASK1" "$MASK2" \
            "$AUTOFOCUS_X" "$AUTOFOCUS_Y" \
            "$AUTOFOCUS_WIDTH" "$AUTOFOCUS_HEIGHT"
    ) > "$WORKDIR/lcc.autofocus.txt" 2>&1
    AUTOFOCUS_STATUS=$?
    if [ -e "$AUTOFOCUS_RESPONSE_PATH" ]; then
        AUTOFOCUS_RESPONSE_OWNED=yes
    fi
    printf 'autofocus_returned=%s\n' "$AUTOFOCUS_STATUS"

    # The factory workflow returns zero even when its internal 20-second
    # response wait expires. Require the exact positive response marker and
    # reject the exact timeout marker instead of trusting the exit status alone.
    AUTOFOCUS_RECEIVED_COUNT=$(
        /system/bin/toybox grep -c '^Receive interrupt signal$' \
            "$WORKDIR/lcc.autofocus.txt"
    )
    AUTOFOCUS_TIMEOUT_COUNT=$(
        /system/bin/toybox grep -c "^Don't recieve interrupt signal$" \
            "$WORKDIR/lcc.autofocus.txt"
    )
    printf 'autofocus_interrupt_received_count=%s\n' \
        "$AUTOFOCUS_RECEIVED_COUNT"
    printf 'autofocus_interrupt_timeout_count=%s\n' "$AUTOFOCUS_TIMEOUT_COUNT"
    AUTOFOCUS_TID_HEX=$(
        /system/bin/printf '%04x' "$EXPECTED_AUTOFOCUS_TID"
    ) || fail cannot_format_autofocus_tid_hex
    AUTOFOCUS_HEADER_COUNT=$(
        /system/bin/toybox grep -c \
            "^Transaction ID 0x$AUTOFOCUS_TID_HEX, status" \
            "$WORKDIR/lcc.autofocus.txt"
    )
    AUTOFOCUS_STATUS_ZERO_COUNT=$(
        /system/bin/toybox grep -c \
            "^Transaction ID 0x$AUTOFOCUS_TID_HEX, status  0 *$" \
            "$WORKDIR/lcc.autofocus.txt"
    )
    printf 'autofocus_header_count=%s\n' "$AUTOFOCUS_HEADER_COUNT"
    printf 'autofocus_status_zero_count=%s\n' \
        "$AUTOFOCUS_STATUS_ZERO_COUNT"

    # Never leave an attempted autofocus operation described as "not_run".
    # Refine this diagnostic as each independently verified response gate is
    # reached; the final success value is assigned only after the response file
    # has also been checked and retained below.
    AUTOFOCUS_RESPONSE=interrupt_markers_invalid
    if [ "$AUTOFOCUS_RECEIVED_COUNT" = "0" ] && \
        [ "$AUTOFOCUS_TIMEOUT_COUNT" = "1" ]; then
        AUTOFOCUS_RESPONSE=interrupt_not_received
    elif [ "$AUTOFOCUS_RECEIVED_COUNT" = "1" ] && \
        [ "$AUTOFOCUS_TIMEOUT_COUNT" = "0" ]; then
        AUTOFOCUS_RESPONSE=interrupt_received_status_unverified
        if [ "$AUTOFOCUS_HEADER_COUNT" = "1" ] && \
            [ "$AUTOFOCUS_STATUS_ZERO_COUNT" = "0" ]; then
            AUTOFOCUS_RESPONSE=interrupt_received_status_nonzero
        elif [ "$AUTOFOCUS_HEADER_COUNT" = "1" ] && \
            [ "$AUTOFOCUS_STATUS_ZERO_COUNT" = "1" ]; then
            AUTOFOCUS_RESPONSE=interrupt_received_status_zero_stdout
        fi
    fi

    force_manual_zero || fail autofocus_manual_control_cleanup_failed
    if /system/bin/toybox pgrep -x lcc >/dev/null 2>&1; then
        fail lcc_process_after_autofocus
    fi
    if /system/bin/toybox grep -qi ':1388' \
        /proc/net/udp /proc/net/udp6 2>/dev/null; then
        fail udp_port_5000_after_autofocus
    fi
    [ "$AUTOFOCUS_STATUS" = "0" ] || fail autofocus_nonzero_or_timeout
    [ "$AUTOFOCUS_RECEIVED_COUNT" = "1" ] || \
        fail autofocus_interrupt_not_received_once
    [ "$AUTOFOCUS_TIMEOUT_COUNT" = "0" ] || \
        fail autofocus_reported_interrupt_timeout
    [ "$AUTOFOCUS_HEADER_COUNT" = "1" ] || \
        fail autofocus_response_header_missing_or_repeated
    [ "$AUTOFOCUS_STATUS_ZERO_COUNT" = "1" ] || \
        fail autofocus_response_status_nonzero

    AUTOFOCUS_TID_AFTER=$(read_decimal_tid) || \
        fail cannot_read_autofocus_tid_after
    [ "$AUTOFOCUS_TID_AFTER" = "$EXPECTED_AUTOFOCUS_TID" ] || \
        fail unexpected_autofocus_tid_after
    [ -f "$AUTOFOCUS_RESPONSE_PATH" ] || \
        fail autofocus_response_file_missing
    AUTOFOCUS_RESPONSE_SIZE=$(
        /system/bin/toybox wc -c < "$AUTOFOCUS_RESPONSE_PATH"
    ) || fail cannot_size_autofocus_response
    case "$AUTOFOCUS_RESPONSE_SIZE" in
        ""|*[!0-9]*) fail invalid_autofocus_response_size ;;
    esac
    [ "$AUTOFOCUS_RESPONSE_SIZE" -gt 0 ] || \
        fail empty_autofocus_response
    AUTOFOCUS_FILE_STATUS_ZERO_COUNT=$(
        /system/bin/toybox grep -c \
            "^Transaction ID 0x$AUTOFOCUS_TID_HEX, status  0$" \
            "$AUTOFOCUS_RESPONSE_PATH"
    )
    [ "$AUTOFOCUS_FILE_STATUS_ZERO_COUNT" = "1" ] || \
        fail autofocus_response_file_status_nonzero
    AUTOFOCUS_RESPONSE_SHA1=$(
        /system/bin/toybox sha1sum "$AUTOFOCUS_RESPONSE_PATH"
    ) || fail cannot_hash_autofocus_response
    AUTOFOCUS_RESPONSE_SHA1=${AUTOFOCUS_RESPONSE_SHA1%% *}
    cp "$AUTOFOCUS_RESPONSE_PATH" "$WORKDIR/autofocus.response.txt" || \
        fail cannot_retain_autofocus_response
    rm -f "$AUTOFOCUS_RESPONSE_PATH" || \
        fail cannot_remove_autofocus_response
    AUTOFOCUS_RESPONSE_OWNED=no
    AUTOFOCUS_RESPONSE=interrupt_received_status_zero
    printf 'autofocus_response_file_size=%s\n' "$AUTOFOCUS_RESPONSE_SIZE"
    printf 'autofocus_response_file_sha1=%s\n' "$AUTOFOCUS_RESPONSE_SHA1"

    /system/bin/sleep 1
    camera_clients_none "$WORKDIR/camera.after_autofocus.txt" || \
        fail camera_client_after_autofocus_or_state_unknown
    [ "$(getprop init.svc.media)" = "running" ] || \
        fail media_stopped_after_autofocus
    [ "$(getprop init.svc.lightsvr)" = "running" ] || \
        fail lightsvr_stopped_after_autofocus
    printf 'autofocus_settled=yes\n'
fi

printf '%s\n' "$SELECTION_DESCRIPTION"
printf 'factory_tuple=%s %s %s\n' "$TUPLE0" "$TUPLE1" "$TUPLE2"
EXPOSURE_VALUE_COUNT=0
for EXPOSURE_VALUE in $EXPOSURE_ARGS; do
    case "$EXPOSURE_VALUE" in
        ""|*[!0-9]*) fail invalid_compiled_exposure_value ;;
    esac
    # Android 6 here is 32-bit and its shell overflows past about 2.1e9:
    # $((8000000000)) evaluates to -589934592, so a second-scale exposure
    # would be rejected as nonpositive.  Bound the digit count instead,
    # which is exact for decimal strings.
    [ "${#EXPOSURE_VALUE}" -ge 1 ] || fail empty_compiled_exposure_value
    [ "${#EXPOSURE_VALUE}" -le 11 ] || fail compiled_exposure_above_sensor_ceiling
    case "$EXPOSURE_VALUE" in
        0|00*) fail nonpositive_compiled_exposure_value ;;
    esac
    EXPOSURE_VALUE_COUNT=$((EXPOSURE_VALUE_COUNT + 1))
done
[ "$EXPOSURE_VALUE_COUNT" -eq "$EXPOSURE_COUNT" ] || \
    fail compiled_exposure_count_mismatch
printf 'exposure_argument_count=%s\n' "$EXPOSURE_COUNT"
printf 'exposure_argument_module_order=%s\n' "$EXPOSURE_ORDER"
printf 'exposure_plan_module_order=%s\n' "$EXPOSURE_PLAN"
printf 'executed_argv=<verified-lcc-copy> -m 0 -s 0 -f 1 %s %s %s %s %s %s -R 4160,3120 -e %s -g %s\n' \
    "$MASK0" "$MASK1" "$MASK2" "$TUPLE0" "$TUPLE1" "$TUPLE2" \
    "$EXPOSURE_ARGS" "$GAIN"
printf 'outer_timeout=TERM_after_%ss_KILL_after_5s\n' \
    "$CAPTURE_TIMEOUT_SECONDS"
printf '%s\n' 'lcc_response_files=disabled'
printf '%s\n' 'hal_lri_output=expected_automatically'
printf 'hal_lri_directory=%s\n' "$LRI_DIR"

if [ "$USE_A1_AF_SHIM" = "yes" ]; then
    printf 'autofocus_mask=%s %s %s\n' "$MASK0" "$MASK1" "$MASK2"
    printf 'autofocus_roi=%s,%s,%s,%s\n' \
        "$AUTOFOCUS_X" "$AUTOFOCUS_Y" \
        "$AUTOFOCUS_WIDTH" "$AUTOFOCUS_HEIGHT"
    printf '%s\n' \
        'autofocus_execution=camera3_metadata_inside_same_lcc_hal_session_before_start_capture'
    AUTOFOCUS_ATTEMPTED=yes
    NORMAL_REBOOT_REQUIRED=yes
fi

CAPTURE_ATTEMPTED=yes
NORMAL_REBOOT_REQUIRED=yes
# Build each exposure as a distinct argv element. lcc's -e parser consumes
# consecutive numeric arguments until the next option; a comma-separated or
# single quoted list would therefore be wrong for the 16-value profile.
set -- -m 0 -s 0 -f 1 "$MASK0" "$MASK1" "$MASK2" \
    "$TUPLE0" "$TUPLE1" "$TUPLE2" -R 4160,3120 -e
for EXPOSURE_VALUE in $EXPOSURE_ARGS; do
    set -- "$@" "$EXPOSURE_VALUE"
done
set -- "$@" -g "$GAIN"
(
    cd "$WORKDIR" || exit 126
    if [ "$USE_TIMEOUT_SHIM" = "yes" ]; then
        # One preload doing both jobs.  Two separate preloads did load
        # correctly, but each runs its own child self-test, and that extra
        # system() call broke the helper-command count the async half
        # verifies.
        /system/bin/timeout -k 5s "${CAPTURE_TIMEOUT_SECONDS}s" \
            /system/bin/sh -c \
            'LD_PRELOAD=$1; export LD_PRELOAD; shift; exec "$@"' \
            l16-timeout-launch "$TIMEOUT_SHIM_COPY" "$LCC_COPY" "$@"
    elif [ "$USE_ASYNC_SHIM" = "yes" ]; then
        /system/bin/timeout -k 5s "${CAPTURE_TIMEOUT_SECONDS}s" \
            /system/bin/sh -c \
            'LD_PRELOAD=$1; export LD_PRELOAD; shift; exec "$@"' \
            l16-async-launch "$SHIM_COPY" "$LCC_COPY" "$@"
    elif [ "$USE_A1_AF_SHIM" = "yes" ]; then
        /system/bin/timeout -k 5s "${CAPTURE_TIMEOUT_SECONDS}s" \
            /system/bin/sh -c \
            'LD_PRELOAD=$1; export LD_PRELOAD; shift; exec "$@"' \
            l16-a1-af-launch "$AF_SHIM_COPY" "$LCC_COPY" "$@"
    else
        /system/bin/timeout -k 5s "${CAPTURE_TIMEOUT_SECONDS}s" \
            "$LCC_COPY" "$@"
    fi
) > "$WORKDIR/lcc.txt" 2>&1
LCC_STATUS=$?
printf 'lcc_returned=%s\n' "$LCC_STATUS"

if [ "$USE_ASYNC_SHIM" = "yes" ]; then
    for MARKER in \
        loaded preload_cleared resolve_targets_ok preload_child_selftest_ok \
        enqueue_ok worker_start worker_done_ok close_wait close_continue \
        helper_commands_ok close_reports_ok
    do
        MARKER_COUNT=$(/system/bin/toybox grep -c \
            "^L16_ASYNC_SHIM $MARKER$" "$WORKDIR/lcc.txt")
        [ "$MARKER_COUNT" = "1" ] || fail async_shim_marker_missing_or_repeated
    done
    if /system/bin/toybox grep -Eq \
        '^L16_ASYNC_SHIM .*(error|failed|unexpected)' "$WORKDIR/lcc.txt"
    then
        fail async_shim_reported_error
    fi
    ASYNC_SHIM_STATUS=verified
    printf 'async_shim_runtime_markers=verified\n'
fi

if [ "$USE_TIMEOUT_SHIM" = "yes" ]; then
    for MARKER in \
        loaded preload_cleared resolve_targets_ok preload_child_selftest_ok \
        timeout_patched enqueue_ok worker_start worker_done_ok \
        close_wait close_continue helper_commands_ok close_reports_ok
    do
        MARKER_COUNT=$(/system/bin/toybox grep -c \
            "^L16_ASYNC_SHIM $MARKER$" "$WORKDIR/lcc.txt")
        [ "$MARKER_COUNT" = "1" ] || fail "timeout_shim_marker_${MARKER}_count_${MARKER_COUNT}"
    done
    if /system/bin/toybox grep -Eq \
        '^L16_ASYNC_SHIM .*(error|failed|not_patched)' "$WORKDIR/lcc.txt"
    then
        fail timeout_shim_reported_error
    fi
    TIMEOUT_SHIM_STATUS=verified
    printf 'timeout_shim_runtime_markers=verified\n'
fi

if [ "$USE_A1_AF_SHIM" = "yes" ]; then
    for MARKER in \
        loaded preload_cleared resolve_targets_ok metadata_resolve_ok \
        preload_child_selftest_ok af_gate_enter af_trigger_request_armed \
        af_metadata_trigger_injected af_state_focused_locked \
        af_gate_pass capture_released helper_commands_ok close_reports_ok
    do
        MARKER_COUNT=$(/system/bin/toybox grep -c \
            "^L16_A1_AF_SHIM $MARKER$" "$WORKDIR/lcc.txt")
        if [ "$MARKER_COUNT" != "1" ]; then
            printf 'a1_af_shim_marker_%s_count=%s\n' \
                "$MARKER" "$MARKER_COUNT"
            fail "a1_af_shim_marker_${MARKER}_count_${MARKER_COUNT}"
        fi
    done
    if /system/bin/toybox grep -Eq \
        '^L16_A1_AF_SHIM .*(error|failed|suppressed|without_capture)' \
        "$WORKDIR/lcc.txt"
    then
        fail a1_af_shim_reported_failure
    fi
    AUTOFOCUS_STATUS=0
    AUTOFOCUS_RESPONSE=camera3_af_state_focused_locked_inline_hal_session
    A1_AF_SHIM_STATUS=verified
    printf 'a1_af_shim_runtime_markers=verified\n'
fi

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
if [ "$USE_ASYNC_SHIM" = "yes" ]; then
    FINAL_REASON=async_shim_join_verified_lcc_exit_zero_lri_captured_settled_cleanup_content_not_validated
elif [ "$USE_A1_AF_SHIM" = "yes" ]; then
    if [ "$MODE" = "A_GROUP_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE" ]; then
        FINAL_REASON=inline_hal_session_a_group_camera3_af_focused_locked_then_lcc_exit_zero_lri_captured_settled_cleanup_content_not_validated
    else
        FINAL_REASON=inline_hal_session_a1_camera3_af_focused_locked_then_lcc_exit_zero_lri_captured_settled_cleanup_content_not_validated
    fi
elif [ "$RUN_AUTOFOCUS" = "yes" ]; then
    FINAL_REASON=asic_ready_autofocus_status_zero_then_lcc_exit_zero_lri_captured_powered_off_reboot_required_content_not_validated
else
    FINAL_REASON=lcc_exit_zero_lri_captured_settled_cleanup_verified_content_not_validated
fi
exit 0
