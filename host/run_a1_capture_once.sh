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
    if [ "$REMOTE_FILES_CLEARED" != "yes" ]; then
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
"$ADB" shell 'setprop persist.sys.fihop 8'
TRIGGER_SENT=yes

ATTEMPT=0
while [ "$ATTEMPT" -lt 90 ]; do
    if "$ADB" shell "grep -q '^final_status=' '$REMOTE_RESULT'" >/dev/null 2>&1; then
        RESULT_SEEN=yes
        break
    fi
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
