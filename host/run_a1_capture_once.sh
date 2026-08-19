#!/bin/sh
# SPDX-License-Identifier: MIT
# Host supervisor for the fixed device payload. A fully verified clean A1
# return stays up. The focus experiments, experimental async A1, and every all-16
# attempt, including the fixed single-request HDR profile, reboot.
set -eu

CONFIRM_A1=--execute-fixed-a1-20ms-once-with-failure-reboot
CONFIRM_A1_CENTER_AF=--execute-fixed-a1-center-af-then-20ms-capture-once-and-reboot
CONFIRM_A1_INLINE_AF=--execute-fixed-a1-inline-af-then-20ms-capture-once-and-reboot
CONFIRM_A_GROUP_INLINE_AF=--execute-fixed-a-group-inline-af-then-20ms-capture-once-and-reboot
CONFIRM_A1_ASYNC=--execute-fixed-a1-async-shim-20ms-once-and-reboot
CONFIRM_ALL16=--execute-fixed-all16-20ms-once-and-reboot
CONFIRM_ALL16_ASYNC=--execute-fixed-all16-async-shim-20ms-once-and-reboot
CONFIRM_ALL16_HDR_ASYNC=--execute-fixed-all16-hdr-async-shim-1p25-5-20ms-once-and-reboot
EXPECTED_SHIM_SIZE=8904
EXPECTED_SHIM_SHA1=150e53a736624010dc7fb741490ea8dca7afbfb8
EXPECTED_AF_SHIM_SIZE=13764
EXPECTED_AF_SHIM_SHA1=67647b71767ab2b68a214fae87578e24eb3433b2

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(dirname "$SCRIPT_DIR")
PAYLOAD="$REPO_ROOT/device/a1_capture_once.sh"
ADB=${LIGHT_L16_ADB:-adb}
ASYNC_SHIM_REQUIRED=no
AUTOFOCUS_REQUIRED=no
A1_AF_SHIM_REQUIRED=no
SHIM_LOCAL=
REMOTE_SHIM=
EXPECTED_EXPOSURE_COUNT=1
EXPECTED_EXPOSURE_ORDER=common_for_selected_modules
EXPECTED_EXPOSURE_PLAN=selected:20000000
if [ "$#" -eq 1 ] && [ "$1" = "$CONFIRM_A1" ]; then
    PROFILE=a1
    PROFILE_LABEL=A1
    EXPECTED_MODE=A1_FIXED_CAPTURE_20MS_ONCE
    REMOTE_PAYLOAD=/data/local/tmp/light_l16_a1_capture_once.sh
    REMOTE_RESULT=/data/local/tmp/light_l16_a1_capture.result
    REMOTE_ARM=/data/local/tmp/light_l16_a1_capture.armed
    REMOTE_WORK_PREFIX=/data/local/tmp/light_l16_a1_capture_run
    ARM_VALUE=A1_CAPTURE_20000000NS_GAIN_1.0_ONCE
    OUTPUT_PREFIX=a1-capture
    POLL_LIMIT=90
    PASS_REBOOT_REQUIRED=no
elif [ "$#" -eq 1 ] && [ "$1" = "$CONFIRM_A1_CENTER_AF" ]; then
    PROFILE=a1-center-af
    PROFILE_LABEL=A1-CENTER-AF
    EXPECTED_MODE=A1_CENTER_AF_THEN_FIXED_CAPTURE_20MS_ONCE
    REMOTE_PAYLOAD=/data/local/tmp/light_l16_a1_center_af_capture_once.sh
    REMOTE_RESULT=/data/local/tmp/light_l16_a1_center_af_capture.result
    REMOTE_ARM=/data/local/tmp/light_l16_a1_center_af_capture.armed
    REMOTE_WORK_PREFIX=/data/local/tmp/light_l16_a1_center_af_capture_run
    ARM_VALUE=A1_CENTER_AF_THEN_CAPTURE_20000000NS_GAIN_1.0_ONCE
    OUTPUT_PREFIX=a1-center-af-capture
    POLL_LIMIT=120
    PASS_REBOOT_REQUIRED=yes
    AUTOFOCUS_REQUIRED=yes
elif [ "$#" -eq 1 ] && [ "$1" = "$CONFIRM_A1_INLINE_AF" ]; then
    PROFILE=a1-inline-af
    PROFILE_LABEL=A1-INLINE-AF
    EXPECTED_MODE=A1_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE
    REMOTE_PAYLOAD=/data/local/tmp/light_l16_a1_inline_af_capture_once.sh
    REMOTE_RESULT=/data/local/tmp/light_l16_a1_inline_af_capture.result
    REMOTE_ARM=/data/local/tmp/light_l16_a1_inline_af_capture.armed
    REMOTE_WORK_PREFIX=/data/local/tmp/light_l16_a1_inline_af_capture_run
    REMOTE_SHIM=/data/local/tmp/liblcc_a1_focus_capture_shim.so
    ARM_VALUE=A1_INLINE_AF_CAPTURE_20000000NS_GAIN_1.0_ONCE
    OUTPUT_PREFIX=a1-inline-af-capture
    POLL_LIMIT=120
    PASS_REBOOT_REQUIRED=yes
    A1_AF_SHIM_REQUIRED=yes
elif [ "$#" -eq 1 ] && [ "$1" = "$CONFIRM_A_GROUP_INLINE_AF" ]; then
    PROFILE=a-group-inline-af
    PROFILE_LABEL=A-GROUP-INLINE-AF
    EXPECTED_MODE=A_GROUP_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE
    REMOTE_PAYLOAD=/data/local/tmp/light_l16_a_group_inline_af_capture_once.sh
    REMOTE_RESULT=/data/local/tmp/light_l16_a_group_inline_af_capture.result
    REMOTE_ARM=/data/local/tmp/light_l16_a_group_inline_af_capture.armed
    REMOTE_WORK_PREFIX=/data/local/tmp/light_l16_a_group_inline_af_capture_run
    REMOTE_SHIM=/data/local/tmp/liblcc_a1_focus_capture_shim.so
    ARM_VALUE=A_GROUP_INLINE_AF_CAPTURE_20000000NS_GAIN_1.0_ONCE
    OUTPUT_PREFIX=a-group-inline-af-capture
    POLL_LIMIT=150
    PASS_REBOOT_REQUIRED=yes
    A1_AF_SHIM_REQUIRED=yes
elif [ "$#" -eq 1 ] && [ "$1" = "$CONFIRM_A1_ASYNC" ]; then
    PROFILE=a1-async
    PROFILE_LABEL=A1-ASYNC
    EXPECTED_MODE=A1_ASYNC_SHIM_FIXED_CAPTURE_20MS_ONCE
    REMOTE_PAYLOAD=/data/local/tmp/light_l16_a1_async_capture_once.sh
    REMOTE_RESULT=/data/local/tmp/light_l16_a1_async_capture.result
    REMOTE_ARM=/data/local/tmp/light_l16_a1_async_capture.armed
    REMOTE_WORK_PREFIX=/data/local/tmp/light_l16_a1_async_capture_run
    REMOTE_SHIM=/data/local/tmp/liblcc_async_writer_shim.so
    ARM_VALUE=A1_ASYNC_SHIM_CAPTURE_20000000NS_GAIN_1.0_ONCE
    OUTPUT_PREFIX=a1-async-capture
    POLL_LIMIT=90
    PASS_REBOOT_REQUIRED=yes
    ASYNC_SHIM_REQUIRED=yes
elif [ "$#" -eq 1 ] && [ "$1" = "$CONFIRM_ALL16" ]; then
    PROFILE=all16
    PROFILE_LABEL=ALL16
    EXPECTED_MODE=ALL16_FIXED_CAPTURE_20MS_ONCE
    REMOTE_PAYLOAD=/data/local/tmp/light_l16_all16_capture_once.sh
    REMOTE_RESULT=/data/local/tmp/light_l16_all16_capture.result
    REMOTE_ARM=/data/local/tmp/light_l16_all16_capture.armed
    REMOTE_WORK_PREFIX=/data/local/tmp/light_l16_all16_capture_run
    ARM_VALUE=ALL16_CAPTURE_20000000NS_GAIN_1.0_ONCE
    OUTPUT_PREFIX=all16-capture
    POLL_LIMIT=150
    PASS_REBOOT_REQUIRED=yes
elif [ "$#" -eq 1 ] && [ "$1" = "$CONFIRM_ALL16_ASYNC" ]; then
    PROFILE=all16-async
    PROFILE_LABEL=ALL16-ASYNC
    EXPECTED_MODE=ALL16_ASYNC_SHIM_FIXED_CAPTURE_20MS_ONCE
    REMOTE_PAYLOAD=/data/local/tmp/light_l16_all16_async_capture_once.sh
    REMOTE_RESULT=/data/local/tmp/light_l16_all16_async_capture.result
    REMOTE_ARM=/data/local/tmp/light_l16_all16_async_capture.armed
    REMOTE_WORK_PREFIX=/data/local/tmp/light_l16_all16_async_capture_run
    REMOTE_SHIM=/data/local/tmp/liblcc_async_writer_shim.so
    ARM_VALUE=ALL16_ASYNC_SHIM_CAPTURE_20000000NS_GAIN_1.0_ONCE
    OUTPUT_PREFIX=all16-async-capture
    POLL_LIMIT=150
    PASS_REBOOT_REQUIRED=yes
    ASYNC_SHIM_REQUIRED=yes
elif [ "$#" -eq 1 ] && [ "$1" = "$CONFIRM_ALL16_HDR_ASYNC" ]; then
    PROFILE=all16-hdr-async
    PROFILE_LABEL=ALL16-HDR-ASYNC
    EXPECTED_MODE=ALL16_HDR_ASYNC_SHIM_SINGLE_REQUEST_1P25_5_20MS_ONCE
    REMOTE_PAYLOAD=/data/local/tmp/light_l16_all16_hdr_async_capture_once.sh
    REMOTE_RESULT=/data/local/tmp/light_l16_all16_hdr_async_capture.result
    REMOTE_ARM=/data/local/tmp/light_l16_all16_hdr_async_capture.armed
    REMOTE_WORK_PREFIX=/data/local/tmp/light_l16_all16_hdr_async_capture_run
    REMOTE_SHIM=/data/local/tmp/liblcc_async_writer_shim.so
    ARM_VALUE=ALL16_HDR_ASYNC_SHIM_CAPTURE_1250000_5000000_20000000NS_GAIN_1.0_ONCE
    OUTPUT_PREFIX=all16-hdr-async-capture
    POLL_LIMIT=150
    PASS_REBOOT_REQUIRED=yes
    ASYNC_SHIM_REQUIRED=yes
    EXPECTED_EXPOSURE_COUNT=16
    EXPECTED_EXPOSURE_ORDER=A1,A2,A3,A4,A5,B1,B2,B3,B4,B5,C1,C2,C3,C4,C5,C6
    EXPECTED_EXPOSURE_PLAN=A1:1250000,A2:20000000,A3:5000000,A4:5000000,A5:20000000,B1:20000000,B2:5000000,B3:5000000,B4:1250000,B5:20000000,C1:20000000,C2:5000000,C3:5000000,C4:20000000,C5:1250000,C6:20000000
else
    printf 'usage: %s {%s|%s|%s|%s|%s|%s|%s|%s}\n' \
        "$0" "$CONFIRM_A1" "$CONFIRM_A1_CENTER_AF" \
        "$CONFIRM_A1_INLINE_AF" "$CONFIRM_A_GROUP_INLINE_AF" \
        "$CONFIRM_A1_ASYNC" "$CONFIRM_ALL16" "$CONFIRM_ALL16_ASYNC" \
        "$CONFIRM_ALL16_HDR_ASYNC" >&2
    printf 'Profiles perform one real lcc capture request. HDR uses fixed 1.25/5/20 ms module roles; AF, shim, and ALL16 profiles always reboot.\n' >&2
    exit 2
fi

RUN_STAMP=$(date -u '+%Y%m%dT%H%M%SZ')
OUTPUT_ROOT=${LIGHT_L16_OUTPUT_ROOT:-"$REPO_ROOT/output"}
HOST_OUTPUT="$OUTPUT_ROOT/$OUTPUT_PREFIX-$RUN_STAMP"
RESULT_SEEN=no
RESULT_PARSED=no
CAPTURE_ATTEMPTED=unknown
ASIC_RESET_ATTEMPTED=unknown
ASIC_RESET_EXIT_STATUS=unknown
ASIC_READY_EXIT_STATUS=unknown
ASIC_READY_RESPONSE=unknown
ASIC_POWER_OFF_EXIT_STATUS=unknown
AUTOFOCUS_ATTEMPTED=unknown
AUTOFOCUS_EXIT_STATUS=unknown
AUTOFOCUS_RESPONSE=unknown
FINAL_STATUS=unknown
RESULT_MODE=unknown
LCC_EXIT_STATUS=unknown
CLEANUP_OK=unknown
MANUAL_CONTROL_AFTER=unknown
LCC_PROCESS_AFTER=unknown
NORMAL_REBOOT_REQUIRED=unknown
SETTLED_CAMERA_CLIENTS=unknown
MEDIA_AFTER=unknown
LIGHTSVR_AFTER=unknown
ASYNC_SHIM_STATUS=unknown
A1_AF_SHIM_STATUS=unknown
RESULT_EXPOSURE_COUNT=unknown
RESULT_EXPOSURE_ORDER=unknown
RESULT_EXPOSURE_PLAN=unknown
PROPERTIES_CLEARED=no
REMOTE_FILES_CLEARED=no
TRIGGER_SENT=no
REBOOT_SENT=no
DEVICE_LOGS_PULLED=no
LRI_PULLED=no
SAFE_NO_REBOOT=no

remove_remote_staging() {
    if [ -n "$REMOTE_SHIM" ]; then
        "$ADB" shell \
            "rm -f '$REMOTE_PAYLOAD' '$REMOTE_ARM' '$REMOTE_SHIM'" \
            >/dev/null 2>&1 || true
    else
        "$ADB" shell "rm -f '$REMOTE_PAYLOAD' '$REMOTE_ARM'" \
            >/dev/null 2>&1 || true
    fi
}

pull_lri_artifact() {
    RESULT_FILE=$1
    REMOTE_LRI_COUNT=$(sed -n 's/^lri_output_count=//p' "$RESULT_FILE" | tail -n 1)
    if [ "$REMOTE_LRI_COUNT" != "1" ]; then
        if [ "$FINAL_STATUS" = "PASS" ]; then
            printf 'PASS result did not declare exactly one LRI\n' >&2
            return 1
        fi
        return 0
    fi

    REMOTE_LRI=$(sed -n 's/^lri_output_path=//p' "$RESULT_FILE" | tail -n 1)
    REMOTE_LRI_SIZE=$(sed -n 's/^lri_output_size=//p' "$RESULT_FILE" | tail -n 1)
    REMOTE_LRI_SHA1=$(sed -n 's/^lri_output_sha1=//p' "$RESULT_FILE" | tail -n 1)
    if ! printf '%s\n' "$REMOTE_LRI" | \
        grep -Eq '^/sdcard/DCIM/camera/RDI_[0-9]{8}_[0-9]{6}_[0-9]{3}\.lri$'
    then
        printf 'refusing unexpected LRI path: %s\n' "$REMOTE_LRI" >&2
        return 1
    fi
    case "$REMOTE_LRI_SIZE" in
        ""|*[!0-9]*)
            printf 'invalid device LRI size: %s\n' "$REMOTE_LRI_SIZE" >&2
            return 1
            ;;
    esac
    if [ "$REMOTE_LRI_SIZE" -lt 32 ]; then
        printf 'device LRI is too small: %s bytes\n' "$REMOTE_LRI_SIZE" >&2
        return 1
    fi
    if ! printf '%s\n' "$REMOTE_LRI_SHA1" | grep -Eq '^[0-9a-f]{40}$'; then
        printf 'invalid device LRI SHA-1: %s\n' "$REMOTE_LRI_SHA1" >&2
        return 1
    fi

    PIXEL_DIR="$HOST_OUTPUT/pixels"
    mkdir -p "$PIXEL_DIR"
    LRI_NAME=${REMOTE_LRI##*/}
    LOCAL_LRI="$PIXEL_DIR/$LRI_NAME"
    "$ADB" pull "$REMOTE_LRI" "$LOCAL_LRI" >/dev/null
    LOCAL_LRI_SIZE=$(wc -c < "$LOCAL_LRI")
    LOCAL_LRI_SHA1=$(sha1sum "$LOCAL_LRI")
    LOCAL_LRI_SHA1=${LOCAL_LRI_SHA1%% *}
    [ "$LOCAL_LRI_SIZE" = "$REMOTE_LRI_SIZE" ] || {
        printf 'LRI size mismatch: device=%s host=%s\n' \
            "$REMOTE_LRI_SIZE" "$LOCAL_LRI_SIZE" >&2
        return 1
    }
    [ "$LOCAL_LRI_SHA1" = "$REMOTE_LRI_SHA1" ] || {
        printf 'LRI SHA-1 mismatch: device=%s host=%s\n' \
            "$REMOTE_LRI_SHA1" "$LOCAL_LRI_SHA1" >&2
        return 1
    }
    {
        printf 'profile=%s\n' "$PROFILE"
        printf 'mode=%s\n' "$RESULT_MODE"
        printf 'exposure_argument_count=%s\n' "$RESULT_EXPOSURE_COUNT"
        printf 'exposure_argument_module_order=%s\n' "$RESULT_EXPOSURE_ORDER"
        printf 'exposure_plan_module_order=%s\n' "$RESULT_EXPOSURE_PLAN"
        printf 'remote_path=%s\n' "$REMOTE_LRI"
        printf 'local_file=%s\n' "$LRI_NAME"
        printf 'size=%s\n' "$LOCAL_LRI_SIZE"
        printf 'sha1=%s\n' "$LOCAL_LRI_SHA1"
        printf 'remote_file_retained=yes\n'
    } > "$PIXEL_DIR/manifest.txt"
    LRI_PULLED=yes
    printf 'LRI copied with matching size and SHA-1: %s\n' "$LOCAL_LRI" >&2
}

clear_properties() {
    "$ADB" shell \
        'setprop persist.sys.fihop 0; setprop persist.sys.fihop1 ""; setprop persist.sys.fihop2 ""; setprop persist.sys.fihop3 ""; setprop persist.sys.fihop4 ""; setprop persist.sys.fihop5 ""' \
        >/dev/null 2>&1 || true
    PROPERTIES_CLEARED=yes
}

finish_host() {
    trap - EXIT HUP INT TERM
    if [ "$PROPERTIES_CLEARED" != "yes" ]; then
        clear_properties
    fi
    # Once the trigger may have been delivered, deleting the arm file here can
    # race the just-started device payload.  Leave both files in place for the
    # reboot/recovery path; the normal completed path removes them below.
    if [ "$REMOTE_FILES_CLEARED" != "yes" ] && [ "$TRIGGER_SENT" = "no" ]; then
        remove_remote_staging
    fi
    if [ "$REBOOT_SENT" != "yes" ] && [ "$SAFE_NO_REBOOT" != "yes" ] && \
        { [ "$ASIC_RESET_ATTEMPTED" = "yes" ] || \
          [ "$CAPTURE_ATTEMPTED" = "yes" ] || \
          [ "$AUTOFOCUS_ATTEMPTED" = "yes" ] || \
          { [ "$TRIGGER_SENT" != "no" ] && [ "$RESULT_PARSED" != "yes" ]; }; }
    then
        printf 'Host-side failure after trigger; requesting conservative normal reboot.\n' >&2
        "$ADB" reboot >/dev/null 2>&1 || true
    fi
}

trap finish_host EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

[ -f "$PAYLOAD" ] || {
    printf 'missing payload: %s\n' "$PAYLOAD" >&2
    exit 1
}

if [ "$ASYNC_SHIM_REQUIRED" = "yes" ]; then
    SHIM_LOCAL=${LIGHT_L16_ASYNC_SHIM:-}
    PROFILE_SHIM_SIZE=$EXPECTED_SHIM_SIZE
    PROFILE_SHIM_SHA1=$EXPECTED_SHIM_SHA1
    PROFILE_SHIM_LABEL=async
    [ -n "$SHIM_LOCAL" ] && [ -f "$SHIM_LOCAL" ] || {
        printf 'set LIGHT_L16_ASYNC_SHIM to the reviewed ARM32 shim file\n' >&2
        exit 1
    }
elif [ "$A1_AF_SHIM_REQUIRED" = "yes" ]; then
    SHIM_LOCAL=${LIGHT_L16_A1_AF_SHIM:-}
    PROFILE_SHIM_SIZE=$EXPECTED_AF_SHIM_SIZE
    PROFILE_SHIM_SHA1=$EXPECTED_AF_SHIM_SHA1
    PROFILE_SHIM_LABEL=a1_af
    [ -n "$SHIM_LOCAL" ] && [ -f "$SHIM_LOCAL" ] || {
        printf 'set LIGHT_L16_A1_AF_SHIM to the reviewed ARM32 shim file\n' >&2
        exit 1
    }
fi

if [ -n "$SHIM_LOCAL" ]; then
    HOST_SHIM_SIZE=$(wc -c < "$SHIM_LOCAL")
    HOST_SHIM_SHA1=$(sha1sum "$SHIM_LOCAL")
    HOST_SHIM_SHA1=${HOST_SHIM_SHA1%% *}
    [ "$HOST_SHIM_SIZE" = "$PROFILE_SHIM_SIZE" ] && \
        [ "$HOST_SHIM_SHA1" = "$PROFILE_SHIM_SHA1" ] || {
            printf 'refusing unexpected %s shim: size=%s sha1=%s\n' \
                "$PROFILE_SHIM_LABEL" "$HOST_SHIM_SIZE" \
                "$HOST_SHIM_SHA1" >&2
            exit 1
        }
fi

DEVICE_COUNT=$(
    "$ADB" devices | awk 'NR > 1 && $2 == "device" {n++} END {print n + 0}'
)
[ "$DEVICE_COUNT" = "1" ] || {
    printf 'expected exactly one authorized ADB device, found %s\n' "$DEVICE_COUNT" >&2
    exit 1
}

DEVICE_BUILD=$("$ADB" shell 'getprop ro.build.version.incremental' | tr -d '\r')
DEVICE_MODEL=$("$ADB" shell 'getprop ro.product.model' | tr -d '\r')
DEVICE_NAME=$("$ADB" shell 'getprop ro.product.name' | tr -d '\r')
[ "$DEVICE_BUILD" = "00WW_1_351" ] && [ "$DEVICE_MODEL" = "L16" ] && \
    [ "$DEVICE_NAME" = "LFC_0002_FIH01" ] || {
        printf 'refusing unexpected ADB target: build=%s model=%s product=%s\n' \
            "$DEVICE_BUILD" "$DEVICE_MODEL" "$DEVICE_NAME" >&2
        exit 1
    }

[ ! -e "$HOST_OUTPUT" ] || {
    printf 'refusing to reuse host output directory: %s\n' "$HOST_OUTPUT" >&2
    exit 1
}
mkdir -p "$HOST_OUTPUT"
clear_properties
remove_remote_staging
"$ADB" push "$PAYLOAD" "$REMOTE_PAYLOAD" >/dev/null
"$ADB" shell \
    "chmod 0700 '$REMOTE_PAYLOAD'; rm -f '$REMOTE_RESULT' '$REMOTE_ARM'"
if [ -n "$SHIM_LOCAL" ]; then
    "$ADB" push "$SHIM_LOCAL" "$REMOTE_SHIM" >/dev/null
    "$ADB" shell "chmod 0600 '$REMOTE_SHIM'"
fi

HOST_SHA1=$(sha1sum "$PAYLOAD")
HOST_SHA1=${HOST_SHA1%% *}
DEVICE_SHA1=$("$ADB" shell "/system/bin/toybox sha1sum '$REMOTE_PAYLOAD'")
DEVICE_SHA1=${DEVICE_SHA1%% *}
DEVICE_SHA1=$(printf '%s' "$DEVICE_SHA1" | tr -d '\r')
[ "$HOST_SHA1" = "$DEVICE_SHA1" ] || {
    printf 'payload hash mismatch: host=%s device=%s\n' "$HOST_SHA1" "$DEVICE_SHA1" >&2
    exit 1
}
printf 'payload_sha1=%s\n' "$HOST_SHA1"

if [ -n "$SHIM_LOCAL" ]; then
    DEVICE_SHIM_SIZE=$(
        "$ADB" shell "/system/bin/toybox wc -c < '$REMOTE_SHIM'" | tr -d '\r'
    )
    DEVICE_SHIM_SHA1=$(
        "$ADB" shell "/system/bin/toybox sha1sum '$REMOTE_SHIM'"
    )
    DEVICE_SHIM_SHA1=${DEVICE_SHIM_SHA1%% *}
    DEVICE_SHIM_SHA1=$(printf '%s' "$DEVICE_SHIM_SHA1" | tr -d '\r')
    [ "$DEVICE_SHIM_SIZE" = "$PROFILE_SHIM_SIZE" ] && \
        [ "$DEVICE_SHIM_SHA1" = "$PROFILE_SHIM_SHA1" ] || {
            printf '%s shim device mismatch: size=%s sha1=%s\n' \
                "$PROFILE_SHIM_LABEL" "$DEVICE_SHIM_SIZE" \
                "$DEVICE_SHIM_SHA1" >&2
            exit 1
        }
    printf '%s_shim_sha1=%s\n' "$PROFILE_SHIM_LABEL" "$DEVICE_SHIM_SHA1"
fi

"$ADB" shell \
    "printf '%s\\n' '$ARM_VALUE' > '$REMOTE_ARM'; chmod 0600 '$REMOTE_ARM'"
DEVICE_ARM_VALUE=$("$ADB" shell "cat '$REMOTE_ARM'" | tr -d '\r')
[ "$DEVICE_ARM_VALUE" = "$ARM_VALUE" ] || {
    printf 'refusing trigger: arm file did not round-trip exactly\n' >&2
    exit 1
}
"$ADB" shell 'setprop persist.sys.fihop 0'
"$ADB" shell "setprop persist.sys.fihop1 /system/bin/sh"
"$ADB" shell "setprop persist.sys.fihop2 '$REMOTE_PAYLOAD'"
"$ADB" shell 'setprop persist.sys.fihop3 ""; setprop persist.sys.fihop4 ""; setprop persist.sys.fihop5 ""'

F0=$("$ADB" shell 'getprop persist.sys.fihop' | tr -d '\r')
F1=$("$ADB" shell 'getprop persist.sys.fihop1' | tr -d '\r')
F2=$("$ADB" shell 'getprop persist.sys.fihop2' | tr -d '\r')
F3=$("$ADB" shell 'getprop persist.sys.fihop3' | tr -d '\r')
F4=$("$ADB" shell 'getprop persist.sys.fihop4' | tr -d '\r')
F5=$("$ADB" shell 'getprop persist.sys.fihop5' | tr -d '\r')
[ "$F0" = "0" ] && [ "$F1" = "/system/bin/sh" ] && \
    [ "$F2" = "$REMOTE_PAYLOAD" ] && [ -z "$F3" ] && \
    [ -z "$F4" ] && [ -z "$F5" ] || {
        printf 'refusing trigger: fihop properties did not round-trip exactly\n' >&2
        exit 1
    }

PROPERTIES_CLEARED=no
TRIGGER_SENT=maybe
if "$ADB" shell 'setprop persist.sys.fihop 8'; then
    TRIGGER_SENT=yes
else
    # The property service can start fihop before adb observes the command's
    # exit status.  Treat this as ambiguous delivery and poll the result instead
    # of running the EXIT cleanup against a payload that may already be active.
    printf 'Trigger command returned nonzero; delivery may have occurred, polling result.\n' >&2
fi

ATTEMPT=0
while [ "$ATTEMPT" -lt "$POLL_LIMIT" ]; do
    # This production Android build uses the legacy adb shell protocol: the
    # host sees status 0 even when the remote command exits nonzero.  Determine
    # completion from an exact stdout marker, never from adb's exit status.
    POLL_STATE=$(
        "$ADB" shell \
            "if /system/bin/toybox grep -q '^final_status=' '$REMOTE_RESULT' 2>/dev/null; then printf '%s\\n' LIGHT_L16_RESULT_COMPLETE; else printf '%s\\n' LIGHT_L16_RESULT_PENDING; fi" \
            2>/dev/null || true
    )
    POLL_STATE=$(printf '%s' "$POLL_STATE" | tr -d '\r')
    case "$POLL_STATE" in
        LIGHT_L16_RESULT_COMPLETE)
            RESULT_SEEN=yes
            break
            ;;
        LIGHT_L16_RESULT_PENDING|"") ;;
        *)
            printf 'Ignoring unexpected result-poll response: %s\n' \
                "$POLL_STATE" >&2
            ;;
    esac
    ATTEMPT=$((ATTEMPT + 1))
    sleep 1
done

clear_properties
"$ADB" shell "rm -f '$REMOTE_ARM'" >/dev/null 2>&1 || true

if [ "$RESULT_SEEN" = "yes" ]; then
    "$ADB" pull "$REMOTE_RESULT" "$HOST_OUTPUT/result.txt" >/dev/null
    cat "$HOST_OUTPUT/result.txt"
    CAPTURE_ATTEMPTED=$(sed -n 's/^capture_attempted=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    ASIC_RESET_ATTEMPTED=$(sed -n 's/^asic_reset_attempted=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    ASIC_RESET_EXIT_STATUS=$(sed -n 's/^asic_reset_exit_status=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    ASIC_READY_EXIT_STATUS=$(sed -n 's/^asic_ready_exit_status=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    ASIC_READY_RESPONSE=$(sed -n 's/^asic_ready_response=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    ASIC_POWER_OFF_EXIT_STATUS=$(sed -n 's/^asic_power_off_exit_status=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    AUTOFOCUS_ATTEMPTED=$(sed -n 's/^autofocus_attempted=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    AUTOFOCUS_EXIT_STATUS=$(sed -n 's/^autofocus_exit_status=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    AUTOFOCUS_RESPONSE=$(sed -n 's/^autofocus_response=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    FINAL_STATUS=$(sed -n 's/^final_status=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    RESULT_MODE=$(sed -n 's/^mode=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    LCC_EXIT_STATUS=$(sed -n 's/^lcc_exit_status=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    CLEANUP_OK=$(sed -n 's/^cleanup_ok=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    MANUAL_CONTROL_AFTER=$(sed -n 's/^manual_control_after=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    LCC_PROCESS_AFTER=$(sed -n 's/^lcc_process_after=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    NORMAL_REBOOT_REQUIRED=$(sed -n 's/^normal_reboot_required=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    SETTLED_CAMERA_CLIENTS=$(sed -n 's/^settled_camera_clients=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    MEDIA_AFTER=$(sed -n 's/^media_after=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    LIGHTSVR_AFTER=$(sed -n 's/^lightsvr_after=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    ASYNC_SHIM_STATUS=$(sed -n 's/^async_shim=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    A1_AF_SHIM_STATUS=$(sed -n 's/^a1_af_shim=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    RESULT_EXPOSURE_COUNT=$(sed -n 's/^exposure_argument_count=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    RESULT_EXPOSURE_ORDER=$(sed -n 's/^exposure_argument_module_order=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    RESULT_EXPOSURE_PLAN=$(sed -n 's/^exposure_plan_module_order=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    [ "$RESULT_MODE" = "$EXPECTED_MODE" ] || {
        printf 'completed result has unexpected mode: %s\n' "$RESULT_MODE" >&2
        exit 1
    }
    if [ "$CAPTURE_ATTEMPTED" = "yes" ]; then
        [ "$RESULT_EXPOSURE_COUNT" = "$EXPECTED_EXPOSURE_COUNT" ] && \
            [ "$RESULT_EXPOSURE_ORDER" = "$EXPECTED_EXPOSURE_ORDER" ] && \
            [ "$RESULT_EXPOSURE_PLAN" = "$EXPECTED_EXPOSURE_PLAN" ] || {
                printf 'completed result has unexpected exposure manifest\n' >&2
                exit 1
            }
    fi
    if [ "$FINAL_STATUS" = "PASS" ]; then
        [ "$CAPTURE_ATTEMPTED" = "yes" ] && \
            [ "$NORMAL_REBOOT_REQUIRED" = "$PASS_REBOOT_REQUIRED" ] && \
            [ "$LCC_EXIT_STATUS" = "0" ] && [ "$CLEANUP_OK" = "yes" ] && \
            [ "$LCC_PROCESS_AFTER" = "no" ] && \
            [ "$SETTLED_CAMERA_CLIENTS" = "none" ] && \
            [ "$MEDIA_AFTER" = "running" ] && \
            [ "$LIGHTSVR_AFTER" = "running" ] || {
                printf 'PASS result lacks complete settled-cleanup postconditions\n' >&2
                exit 1
            }
        case "$MANUAL_CONTROL_AFTER" in
            *0x0) ;;
            *)
                printf 'PASS result lacks zero manual-control postcondition\n' >&2
                exit 1
                ;;
        esac
        if [ "$AUTOFOCUS_REQUIRED" = "yes" ]; then
            [ "$ASIC_RESET_ATTEMPTED" = "yes" ] && \
                [ "$ASIC_RESET_EXIT_STATUS" = "0" ] && \
                [ "$ASIC_READY_EXIT_STATUS" = "0" ] && \
                [ "$ASIC_READY_RESPONSE" = "ready_01" ] && \
                [ "$ASIC_POWER_OFF_EXIT_STATUS" = "0" ] && \
                [ "$AUTOFOCUS_ATTEMPTED" = "yes" ] && \
                [ "$AUTOFOCUS_EXIT_STATUS" = "0" ] && \
                [ "$AUTOFOCUS_RESPONSE" = "interrupt_received_status_zero" ] || {
                    printf 'center-AF PASS lacks verified reset, readiness, status-zero response, or power-off\n' >&2
                    exit 1
                }
        elif [ "$A1_AF_SHIM_REQUIRED" = "yes" ]; then
            [ "$ASIC_RESET_ATTEMPTED" = "no" ] && \
                [ "$AUTOFOCUS_ATTEMPTED" = "yes" ] && \
                [ "$AUTOFOCUS_EXIT_STATUS" = "0" ] && \
                [ "$AUTOFOCUS_RESPONSE" = \
                    "camera3_af_state_focused_locked_inline_hal_session" ] && \
                [ "$A1_AF_SHIM_STATUS" = "verified" ] || {
                    printf 'inline-AF PASS lacks a focused-locked same-session result or verified shim\n' >&2
                    exit 1
                }
        elif [ "$ASIC_RESET_ATTEMPTED" != "no" ] || \
            [ "$AUTOFOCUS_ATTEMPTED" != "no" ]; then
            printf 'non-AF PASS unexpectedly reports ASIC-reset or autofocus activity\n' >&2
            exit 1
        fi
        if [ "$ASYNC_SHIM_REQUIRED" = "yes" ] && \
            [ "$ASYNC_SHIM_STATUS" != "verified" ]; then
            printf 'async PASS lacks verified shim runtime markers\n' >&2
            exit 1
        fi
    elif [ "$FINAL_STATUS" = "FAIL" ]; then
        if [ "$ASIC_RESET_ATTEMPTED" = "yes" ] || \
            [ "$CAPTURE_ATTEMPTED" = "yes" ] || \
            [ "$AUTOFOCUS_ATTEMPTED" = "yes" ]; then
            [ "$NORMAL_REBOOT_REQUIRED" = "yes" ] || {
                printf 'attempted operation FAIL does not require reboot\n' >&2
                exit 1
            }
        elif [ "$ASIC_RESET_ATTEMPTED" = "no" ] && \
            [ "$CAPTURE_ATTEMPTED" = "no" ] && \
            [ "$AUTOFOCUS_ATTEMPTED" = "no" ]; then
            [ "$NORMAL_REBOOT_REQUIRED" = "no" ] || {
                printf 'preflight FAIL unexpectedly requires reboot\n' >&2
                exit 1
            }
        else
            printf 'malformed attempted-operation fields\n' >&2
            exit 1
        fi
    else
        printf 'malformed or inconsistent completed result\n' >&2
        exit 1
    fi
    DEVICE_WORKDIR=$(sed -n 's/^workdir=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    case "$DEVICE_WORKDIR" in
        "$REMOTE_WORK_PREFIX".*)
            WORK_PID=${DEVICE_WORKDIR#"$REMOTE_WORK_PREFIX".}
            case "$WORK_PID" in
                ""|*[!0-9]*)
                    printf 'refusing unexpected device workdir: %s\n' "$DEVICE_WORKDIR" >&2
                    exit 1
                    ;;
                *)
                    if "$ADB" pull "$DEVICE_WORKDIR" "$HOST_OUTPUT/device" \
                        >/dev/null
                    then
                        DEVICE_LOGS_PULLED=yes
                    else
                        printf 'failed to pull device diagnostic directory\n' >&2
                    fi
                    ;;
            esac
            ;;
        "") ;;
        *)
            printf 'refusing unexpected device workdir: %s\n' "$DEVICE_WORKDIR" >&2
            exit 1
            ;;
    esac
    if [ "$CAPTURE_ATTEMPTED" = "yes" ]; then
        pull_lri_artifact "$HOST_OUTPUT/result.txt"
    fi
    RESULT_PARSED=yes
else
    printf 'no result after %s seconds; capture state is unknown\n' \
        "$POLL_LIMIT" >&2
    "$ADB" pull "$REMOTE_RESULT" "$HOST_OUTPUT/result.partial.txt" \
        >/dev/null 2>&1 || true
fi

remove_remote_staging
REMOTE_FILES_CLEARED=yes

if [ "$CAPTURE_ATTEMPTED:$FINAL_STATUS:$NORMAL_REBOOT_REQUIRED" = \
    "yes:PASS:$PASS_REBOOT_REQUIRED" ] && \
    [ "$DEVICE_LOGS_PULLED" = "yes" ] && \
    [ "$LRI_PULLED" = "yes" ]
then
    if [ "$PROFILE" = "a1" ]; then
        SAFE_NO_REBOOT=yes
        printf 'Clean PASS and settled cleanup verified; no reboot requested.\n' >&2
        printf 'Logs saved under %s\n' "$HOST_OUTPUT" >&2
        exit 0
    fi
    printf '%s PASS artifacts pulled; requesting the mandatory normal reboot.\n' \
        "$PROFILE_LABEL" >&2
    if "$ADB" reboot; then
        REBOOT_SENT=yes
        printf 'Logs saved under %s\n' "$HOST_OUTPUT" >&2
        exit 0
    fi
    printf 'adb reboot failed; perform one normal hardware restart.\n' >&2
    printf 'Logs saved under %s\n' "$HOST_OUTPUT" >&2
    exit 1
fi

if [ "$ASIC_RESET_ATTEMPTED" = "yes" ] || \
    [ "$CAPTURE_ATTEMPTED" = "yes" ] || \
    [ "$AUTOFOCUS_ATTEMPTED" = "yes" ] || [ "$RESULT_SEEN" != "yes" ]; then
    printf 'Camera-operation outcome is not safe for continued uptime; requesting normal reboot.\n' >&2
    if "$ADB" reboot; then
        REBOOT_SENT=yes
    else
        printf 'adb reboot failed; perform one normal hardware restart.\n' >&2
    fi
    printf 'Logs saved under %s\n' "$HOST_OUTPUT" >&2
    exit 1
fi

printf 'Preflight stopped before lcc; no automatic reboot requested.\n' >&2
printf 'Logs saved under %s\n' "$HOST_OUTPUT" >&2
[ "$FINAL_STATUS" = "PASS" ] && exit 0
exit 1
