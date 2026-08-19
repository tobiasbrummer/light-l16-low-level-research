#!/system/bin/sh
# SPDX-License-Identifier: MIT
# Fixed hostless supervisor for exactly one 24-capture all-16 dark frame
# series.
#
# This is deliberately not a general root bridge.  It accepts no arguments,
# verifies the exact reviewed child and async-writer payloads, invokes only the
# fixed dark frame series path, and requests a normal reboot after every
# possible camera attempt.  A clean child preflight failure that proves
# capture_attempted=no is the only path which stays up.
#
# The series itself does not reboot between its captures; the child settles the
# camera and stops at the first failed gate instead.  This single reboot at the
# end is what restores a known state after 24 all-16 sessions.

PATH=/sbin:/vendor/bin:/system/sbin:/system/bin:/system/xbin
export PATH

APP_DIR=/data/data/io.github.tobiasbrummer.lightl16.darkframe/files
SUPERVISOR=$APP_DIR/s.sh
APP_CHILD=$APP_DIR/c.sh
APP_ASYNC_SHIM=$APP_DIR/n.so
APP_RESULT=$APP_DIR/r.txt
APP_ARM=$APP_DIR/a
APP_ARM_VALUE=L16_HOSTLESS_DARK_FRAME_SERIES_SUPERVISOR_ONCE_V1

CHILD=/data/local/tmp/light_l16_dark_frame_series_once.sh
CHILD_RESULT=/data/local/tmp/light_l16_dark_frame_series.result
CHILD_ARM=/data/local/tmp/light_l16_dark_frame_series.armed
CHILD_ARM_VALUE=DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE
ASYNC_SHIM=/data/local/tmp/liblcc_async_writer_shim.so
EXPECTED_CHILD_SIZE=24542
EXPECTED_CHILD_SHA1=3cc7d997768acc0cb6c88de1f9acc8f686e04ffd
EXPECTED_ASYNC_SHIM_SIZE=9080
EXPECTED_ASYNC_SHIM_SHA1=0b93dc17a2c4219943293d96b7edda39be61613d
EXPECTED_MODE=DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE
EXPECTED_CAPTURES_REQUESTED=24
EXPECTED_IDENTITY='uid=0(root) gid=0(root) groups=0(root)'
EXPECTED_CONTEXT=u:r:qti_init_shell:s0

SUPERVISOR_STATUS=FAIL
SUPERVISOR_REASON=supervisor_did_not_finish
SUPERVISOR_DECISION=no_reboot_before_child
CHILD_STARTED=no
CHILD_EXIT_STATUS=not_run
CHILD_RESULT_PRESENT=no
CHILD_FINAL_STATUS=unknown
CHILD_FINAL_REASON=unknown
CHILD_WORKDIR=unknown
CAPTURE_ATTEMPTED=unknown
CHILD_REBOOT_REQUIRED=unknown
REBOOT_REQUIRED=no
REBOOT_COMMAND_RETURNED=no

clear_runner() {
    setprop persist.sys.fihop 0
    setprop persist.sys.fihop1 ""
    setprop persist.sys.fihop2 ""
    setprop persist.sys.fihop3 ""
    setprop persist.sys.fihop4 ""
    setprop persist.sys.fihop5 ""
}

result_field() {
    KEY=$1
    /system/bin/toybox sed -n "s/^$KEY=//p" "$CHILD_RESULT" 2>/dev/null \
        | /system/bin/toybox tail -n 1
}

valid_decimal() {
    case "$1" in
        ""|*[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

valid_sha1() {
    [ "${#1}" -eq 40 ] || return 1
    case "$1" in
        *[!0-9a-f]*) return 1 ;;
        *) return 0 ;;
    esac
}

valid_lri_path() {
    case "$1" in
        /sdcard/DCIM/camera/RDI_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9].lri)
            return 0
            ;;
        *) return 1 ;;
    esac
}

finish() {
    ORIGINAL_STATUS=$?
    trap - EXIT HUP INT TERM

    clear_runner
    rm -f "$CHILD_ARM" "$CHILD" "$ASYNC_SHIM"

    printf 'child_started=%s\n' "$CHILD_STARTED"
    printf 'child_exit_status=%s\n' "$CHILD_EXIT_STATUS"
    printf 'child_result_present=%s\n' "$CHILD_RESULT_PRESENT"
    printf 'child_final_status=%s\n' "$CHILD_FINAL_STATUS"
    printf 'child_final_reason=%s\n' "$CHILD_FINAL_REASON"
    printf 'child_workdir=%s\n' "$CHILD_WORKDIR"
    printf 'capture_attempted=%s\n' "$CAPTURE_ATTEMPTED"
    printf 'child_normal_reboot_required=%s\n' "$CHILD_REBOOT_REQUIRED"
    printf 'supervisor_reason=%s\n' "$SUPERVISOR_REASON"
    printf 'supervisor_decision=%s\n' "$SUPERVISOR_DECISION"
    printf 'supervisor_exit_status=%s\n' "$ORIGINAL_STATUS"
    printf 'supervisor_complete=%s\n' "$SUPERVISOR_STATUS"

    /system/bin/sync
    if [ "$REBOOT_REQUIRED" = "yes" ]; then
        # Let the app observe the completed manifest before Android terminates
        # it, then perform the same kind of normal reboot used by adb reboot.
        /system/bin/sleep 5
        /system/bin/reboot
        REBOOT_COMMAND_RETURNED=yes
        printf 'reboot_command_returned=yes\n'
        /system/bin/sync
        setprop sys.powerctl reboot
    fi
}

fail() {
    SUPERVISOR_STATUS=FAIL
    SUPERVISOR_REASON=$1
    exit 1
}

# Clear the persistent runner before any identity check or camera preflight.
clear_runner

# The app pre-creates this inode.  Truncating rather than replacing it keeps
# the app UID as owner so the result remains readable after the root process.
[ -f "$APP_RESULT" ] || exit 1
: > "$APP_RESULT" || exit 1
exec >> "$APP_RESULT" 2>&1

trap finish EXIT
trap 'SUPERVISOR_REASON=signal_hup; exit 129' HUP
trap 'SUPERVISOR_REASON=signal_int; exit 130' INT
trap 'SUPERVISOR_REASON=signal_term; exit 143' TERM

printf 'supervisor=L16_HOSTLESS_DARK_FRAME_SERIES_V1\n'
printf 'policy=single_fixed_24_capture_all16_dark_frame_series_then_reboot\n'

[ "$0" = "$SUPERVISOR" ] || fail unexpected_supervisor_path
[ -f "$APP_ARM" ] || fail app_arm_missing
APP_ARMED=$(cat "$APP_ARM" 2>/dev/null) || fail cannot_read_app_arm
rm -f "$APP_ARM" || fail cannot_consume_app_arm
[ "$APP_ARMED" = "$APP_ARM_VALUE" ] || fail wrong_app_arm_value
printf 'app_arm=accepted_and_consumed\n'

IDENTITY=$(id) || fail cannot_read_identity
printf 'identity=%s\n' "$IDENTITY"
case "$IDENTITY" in
    "$EXPECTED_IDENTITY"|"$EXPECTED_IDENTITY context=$EXPECTED_CONTEXT") ;;
    *) fail unexpected_root_identity ;;
esac

[ -r "$APP_CHILD" ] || fail packaged_child_missing
APP_CHILD_SIZE=$(/system/bin/toybox wc -c < "$APP_CHILD") || \
    fail cannot_size_packaged_child
APP_CHILD_SHA1=$(/system/bin/toybox sha1sum "$APP_CHILD") || \
    fail cannot_hash_packaged_child
APP_CHILD_SHA1=${APP_CHILD_SHA1%% *}
printf 'packaged_child_size=%s\n' "$APP_CHILD_SIZE"
printf 'packaged_child_sha1=%s\n' "$APP_CHILD_SHA1"
[ "$APP_CHILD_SIZE" = "$EXPECTED_CHILD_SIZE" ] || \
    fail unexpected_packaged_child_size
[ "$APP_CHILD_SHA1" = "$EXPECTED_CHILD_SHA1" ] || \
    fail unexpected_packaged_child_hash

[ -r "$APP_ASYNC_SHIM" ] || fail packaged_async_shim_missing
APP_ASYNC_SHIM_SIZE=$(/system/bin/toybox wc -c < "$APP_ASYNC_SHIM") || \
    fail cannot_size_packaged_async_shim
APP_ASYNC_SHIM_SHA1=$(/system/bin/toybox sha1sum "$APP_ASYNC_SHIM") || \
    fail cannot_hash_packaged_async_shim
APP_ASYNC_SHIM_SHA1=${APP_ASYNC_SHIM_SHA1%% *}
printf 'packaged_async_shim_size=%s\n' "$APP_ASYNC_SHIM_SIZE"
printf 'packaged_async_shim_sha1=%s\n' "$APP_ASYNC_SHIM_SHA1"
[ "$APP_ASYNC_SHIM_SIZE" = "$EXPECTED_ASYNC_SHIM_SIZE" ] || \
    fail unexpected_packaged_async_shim_size
[ "$APP_ASYNC_SHIM_SHA1" = "$EXPECTED_ASYNC_SHIM_SHA1" ] || \
    fail unexpected_packaged_async_shim_hash

rm -f "$CHILD" "$CHILD_ARM" "$CHILD_RESULT" "$ASYNC_SHIM"
cp "$APP_CHILD" "$CHILD" || fail cannot_stage_child
chmod 0700 "$CHILD" || fail cannot_make_child_executable
STAGED_CHILD_SIZE=$(/system/bin/toybox wc -c < "$CHILD") || \
    fail cannot_size_staged_child
STAGED_CHILD_SHA1=$(/system/bin/toybox sha1sum "$CHILD") || \
    fail cannot_hash_staged_child
STAGED_CHILD_SHA1=${STAGED_CHILD_SHA1%% *}
[ "$STAGED_CHILD_SIZE" = "$EXPECTED_CHILD_SIZE" ] || \
    fail staged_child_size_mismatch
[ "$STAGED_CHILD_SHA1" = "$EXPECTED_CHILD_SHA1" ] || \
    fail staged_child_hash_mismatch
printf 'staged_child_sha1=%s\n' "$STAGED_CHILD_SHA1"

cp "$APP_ASYNC_SHIM" "$ASYNC_SHIM" || fail cannot_stage_async_shim
chmod 0400 "$ASYNC_SHIM" || fail cannot_restrict_staged_async_shim
STAGED_ASYNC_SHIM_SIZE=$(/system/bin/toybox wc -c < "$ASYNC_SHIM") || \
    fail cannot_size_staged_async_shim
STAGED_ASYNC_SHIM_SHA1=$(/system/bin/toybox sha1sum "$ASYNC_SHIM") || \
    fail cannot_hash_staged_async_shim
STAGED_ASYNC_SHIM_SHA1=${STAGED_ASYNC_SHIM_SHA1%% *}
[ "$STAGED_ASYNC_SHIM_SIZE" = "$EXPECTED_ASYNC_SHIM_SIZE" ] || \
    fail staged_async_shim_size_mismatch
[ "$STAGED_ASYNC_SHIM_SHA1" = "$EXPECTED_ASYNC_SHIM_SHA1" ] || \
    fail staged_async_shim_hash_mismatch
printf 'staged_async_shim_sha1=%s\n' "$STAGED_ASYNC_SHIM_SHA1"

printf '%s\n' "$CHILD_ARM_VALUE" > "$CHILD_ARM" || fail cannot_arm_child
chmod 0600 "$CHILD_ARM" || fail cannot_restrict_child_arm
CHILD_ARMED=$(cat "$CHILD_ARM" 2>/dev/null) || fail cannot_read_child_arm
[ "$CHILD_ARMED" = "$CHILD_ARM_VALUE" ] || fail child_arm_round_trip_failed
printf 'child_arm=verified\n'

# From this assignment onward, a camera attempt is possible.  Missing,
# malformed, timed-out, or successful results all lead to a normal reboot.
CHILD_STARTED=yes
REBOOT_REQUIRED=yes
SUPERVISOR_DECISION=normal_reboot_after_possible_camera_attempt
# 24 captures at their own 60 s ceiling already need 24 minutes, so the
# outer bound is 40 minutes rather than the single-capture 2 minutes.
/system/bin/timeout -k 10s 2400s /system/bin/sh "$CHILD"
CHILD_EXIT_STATUS=$?
printf 'child_process_returned=%s\n' "$CHILD_EXIT_STATUS"

if [ -f "$CHILD_RESULT" ] && \
    /system/bin/toybox grep -q '^final_status=' "$CHILD_RESULT" 2>/dev/null
then
    CHILD_RESULT_PRESENT=yes
    CHILD_FINAL_STATUS=$(result_field final_status)
    CHILD_FINAL_REASON=$(result_field final_reason)
    CHILD_WORKDIR=$(result_field workdir)
    CAPTURE_ATTEMPTED=$(result_field capture_attempted)
    CHILD_REBOOT_REQUIRED=$(result_field normal_reboot_required)
fi

# A complete, internally consistent preflight refusal proves that lcc was
# never entered.  Only that exact case cancels the conservative reboot.
if [ "$CHILD_RESULT_PRESENT" = "yes" ] && \
    [ "$CHILD_FINAL_STATUS" = "FAIL" ] && \
    [ "$CAPTURE_ATTEMPTED" = "no" ] && \
    [ "$CHILD_REBOOT_REQUIRED" = "no" ]
then
    REBOOT_REQUIRED=no
    SUPERVISOR_STATUS=PREFLIGHT_FAIL
    SUPERVISOR_REASON=child_preflight_stopped_before_camera_attempt
    SUPERVISOR_DECISION=no_reboot_after_proven_preflight_failure
    exit 1
fi

[ "$CHILD_RESULT_PRESENT" = "yes" ] || fail child_result_missing_or_incomplete
# A series that stopped early but returned verified frames is a usable result,
# so PARTIAL is accepted here and reported as PARTIAL rather than collapsed
# into either PASS or FAIL.
case "$CHILD_FINAL_STATUS" in
    PASS|PARTIAL) ;;
    *) fail child_series_failed ;;
esac
[ "$CAPTURE_ATTEMPTED" = "yes" ] || fail child_pass_without_capture_attempt

RESULT_MODE=$(result_field mode)
CAPTURES_REQUESTED=$(result_field captures_requested)
CAPTURES_COMPLETED=$(result_field captures_completed)
SERIES_ABORTED_AT=$(result_field series_aborted_at)
SERIES_ABORT_REASON=$(result_field series_abort_reason)
ASYNC_SHIM_STATUS=$(result_field async_shim_status)
CLEANUP_OK=$(result_field cleanup_ok)
MANUAL_AFTER=$(result_field manual_control_after)
LCC_PROCESS_AFTER=$(result_field lcc_process_after)
SETTLED_CAMERA_CLIENTS=$(result_field settled_camera_clients)
MEDIA_AFTER=$(result_field media_after)
LIGHTSVR_AFTER=$(result_field lightsvr_after)
WORKDIR=$(result_field workdir)

printf 'mode=%s\n' "$RESULT_MODE"
printf 'captures_requested=%s\n' "$CAPTURES_REQUESTED"
printf 'captures_completed=%s\n' "$CAPTURES_COMPLETED"
printf 'series_aborted_at=%s\n' "$SERIES_ABORTED_AT"
printf 'series_abort_reason=%s\n' "$SERIES_ABORT_REASON"
printf 'async_shim_status=%s\n' "$ASYNC_SHIM_STATUS"
printf 'cleanup_ok=%s\n' "$CLEANUP_OK"
printf 'manual_control_after=%s\n' "$MANUAL_AFTER"
printf 'lcc_process_after=%s\n' "$LCC_PROCESS_AFTER"
printf 'settled_camera_clients=%s\n' "$SETTLED_CAMERA_CLIENTS"
printf 'media_after=%s\n' "$MEDIA_AFTER"
printf 'lightsvr_after=%s\n' "$LIGHTSVR_AFTER"
printf 'workdir=%s\n' "$WORKDIR"

[ "$RESULT_MODE" = "$EXPECTED_MODE" ] || fail unexpected_child_mode
[ "$CAPTURES_REQUESTED" = "$EXPECTED_CAPTURES_REQUESTED" ] || \
    fail unexpected_captures_requested
valid_decimal "$CAPTURES_COMPLETED" || fail invalid_captures_completed
[ "$CAPTURES_COMPLETED" -ge 1 ] || \
    fail child_series_produced_no_verified_capture
[ "$CAPTURES_COMPLETED" -le "$EXPECTED_CAPTURES_REQUESTED" ] || \
    fail more_captures_completed_than_requested
[ "$CLEANUP_OK" = "yes" ] || fail child_cleanup_not_verified
case "$MANUAL_AFTER" in
    *0x0) ;;
    *) fail child_manual_control_not_zero ;;
esac
[ "$LCC_PROCESS_AFTER" = "no" ] || fail child_lcc_process_remains
[ "$SETTLED_CAMERA_CLIENTS" = "none" ] || fail child_camera_clients_not_settled
[ "$MEDIA_AFTER" = "running" ] || fail child_media_not_running
[ "$LIGHTSVR_AFTER" = "running" ] || fail child_lightsvr_not_running
case "$WORKDIR" in
    /data/local/tmp/light_l16_dark_frame_series_run.*)
        WORK_PID=${WORKDIR#/data/local/tmp/light_l16_dark_frame_series_run.}
        case "$WORK_PID" in
            ""|*[!0-9]*) fail child_workdir_invalid ;;
        esac
        ;;
    *) fail child_workdir_invalid ;;
esac

# Mirror the child's per-capture manifest into the app-readable result.  The
# app cannot pull and hash 24 files itself, so this list of index, exposure,
# gain, size, and SHA-1 is what survives the reboot.  A copy failure must not
# change capture or reboot policy, so it is reported and otherwise ignored.
if [ -f "$WORKDIR/series.manifest" ]; then
    printf 'manifest_begin\n'
    /system/bin/toybox cat "$WORKDIR/series.manifest" 2>/dev/null || \
        printf 'manifest_copy_failed\n'
    printf 'manifest_end\n'
else
    printf 'manifest_absent\n'
fi

if [ "$CHILD_FINAL_STATUS" = "PASS" ] && \
    [ "$CAPTURES_COMPLETED" = "$EXPECTED_CAPTURES_REQUESTED" ]
then
    SUPERVISOR_STATUS=PASS
    SUPERVISOR_REASON=full_dark_frame_series_recorded_and_child_cleanup_verified
else
    SUPERVISOR_STATUS=PARTIAL
    SUPERVISOR_REASON=partial_dark_frame_series_recorded_and_child_cleanup_verified
fi
SUPERVISOR_DECISION=normal_reboot_after_dark_frame_series
exit 0
