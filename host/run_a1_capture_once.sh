#!/bin/sh
# SPDX-License-Identifier: MIT
# Host supervisor for the fixed A1 device payload. This performs a real capture
# attempt and always requests a normal reboot if the payload reached lcc.
set -eu

CONFIRM=--execute-fixed-a1-once-and-reboot
if [ "$#" -ne 1 ] || [ "$1" != "$CONFIRM" ]; then
    printf 'usage: %s %s\n' "$0" "$CONFIRM" >&2
    printf 'This performs one real A1 lcc attempt and normally reboots the camera.\n' >&2
    exit 2
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(dirname "$SCRIPT_DIR")
PAYLOAD="$REPO_ROOT/device/a1_capture_once.sh"
ADB=${LIGHT_L16_ADB:-adb}
REMOTE_PAYLOAD=/data/local/tmp/light_l16_a1_capture_once.sh
REMOTE_RESULT=/data/local/tmp/light_l16_a1_capture.result
REMOTE_ARM=/data/local/tmp/light_l16_a1_capture.armed
ARM_VALUE=A1_CAPTURE_2609592NS_GAIN_1.0_ONCE
RUN_STAMP=$(date -u '+%Y%m%dT%H%M%SZ')
OUTPUT_ROOT=${LIGHT_L16_OUTPUT_ROOT:-"$REPO_ROOT/output"}
HOST_OUTPUT="$OUTPUT_ROOT/a1-capture-$RUN_STAMP"
RESULT_SEEN=no
RESULT_PARSED=no
CAPTURE_ATTEMPTED=unknown
FINAL_STATUS=unknown
PROPERTIES_CLEARED=no
REMOTE_FILES_CLEARED=no
TRIGGER_SENT=no
REBOOT_SENT=no

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
        printf 'remote_path=%s\n' "$REMOTE_LRI"
        printf 'local_file=%s\n' "$LRI_NAME"
        printf 'size=%s\n' "$LOCAL_LRI_SIZE"
        printf 'sha1=%s\n' "$LOCAL_LRI_SHA1"
        printf 'remote_file_retained=yes\n'
    } > "$PIXEL_DIR/manifest.txt"
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
        "$ADB" shell "rm -f '$REMOTE_PAYLOAD' '$REMOTE_ARM'" \
            >/dev/null 2>&1 || true
    fi
    if [ "$REBOOT_SENT" != "yes" ] && \
        { [ "$CAPTURE_ATTEMPTED" = "yes" ] || \
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
"$ADB" push "$PAYLOAD" "$REMOTE_PAYLOAD" >/dev/null
"$ADB" shell \
    "chmod 0700 '$REMOTE_PAYLOAD'; rm -f '$REMOTE_RESULT' '$REMOTE_ARM'"

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
while [ "$ATTEMPT" -lt 90 ]; do
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
    FINAL_STATUS=$(sed -n 's/^final_status=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    case "$CAPTURE_ATTEMPTED:$FINAL_STATUS" in
        yes:PASS|yes:FAIL|no:FAIL) ;;
        *)
            printf 'malformed or inconsistent completed result\n' >&2
            exit 1
            ;;
    esac
    DEVICE_WORKDIR=$(sed -n 's/^workdir=//p' "$HOST_OUTPUT/result.txt" | tail -n 1)
    case "$DEVICE_WORKDIR" in
        /data/local/tmp/light_l16_a1_capture_run.*)
            WORK_PID=${DEVICE_WORKDIR#/data/local/tmp/light_l16_a1_capture_run.}
            case "$WORK_PID" in
                ""|*[!0-9]*)
                    printf 'refusing unexpected device workdir: %s\n' "$DEVICE_WORKDIR" >&2
                    ;;
                *)
                    "$ADB" pull "$DEVICE_WORKDIR" "$HOST_OUTPUT/device" \
                        >/dev/null || true
                    ;;
            esac
            ;;
        "") ;;
        *)
            printf 'refusing unexpected device workdir: %s\n' "$DEVICE_WORKDIR" >&2
            ;;
    esac
    if [ "$CAPTURE_ATTEMPTED" = "yes" ]; then
        pull_lri_artifact "$HOST_OUTPUT/result.txt"
    fi
    RESULT_PARSED=yes
else
    printf 'no result after 90 seconds; capture state is unknown\n' >&2
    "$ADB" pull "$REMOTE_RESULT" "$HOST_OUTPUT/result.partial.txt" \
        >/dev/null 2>&1 || true
fi

"$ADB" shell "rm -f '$REMOTE_PAYLOAD' '$REMOTE_ARM'" >/dev/null 2>&1 || true
REMOTE_FILES_CLEARED=yes

if [ "$CAPTURE_ATTEMPTED" = "yes" ] || [ "$RESULT_SEEN" != "yes" ]; then
    printf 'A capture may have reached lcc; requesting mandatory normal reboot.\n' >&2
    if "$ADB" reboot; then
        REBOOT_SENT=yes
    else
        printf 'adb reboot failed; perform one normal hardware restart.\n' >&2
    fi
    printf 'Logs saved under %s\n' "$HOST_OUTPUT" >&2
    [ "$FINAL_STATUS" = "PASS" ] && exit 0
    exit 1
fi

printf 'Preflight stopped before lcc; no automatic reboot requested.\n' >&2
printf 'Logs saved under %s\n' "$HOST_OUTPUT" >&2
[ "$FINAL_STATUS" = "PASS" ] && exit 0
exit 1
