#!/system/bin/sh
# SPDX-License-Identifier: MIT
# Fixed hostless supervisor for exactly one same-session A1 center-AF followed
# by one A1 20 ms / gain 1 capture.
#
# This is deliberately not a general root bridge.  It accepts no arguments,
# verifies the exact reviewed child and preload payloads, invokes only the
# fixed inline-AF A1 path, and requests a normal reboot after every possible
# camera attempt.  A clean child preflight failure that proves
# capture_attempted=no is the only path which stays up.

PATH=/sbin:/vendor/bin:/system/sbin:/system/bin:/system/xbin
export PATH

APP_DIR=/data/data/io.github.tobiasbrummer.lightl16.a1capture/files
SUPERVISOR=$APP_DIR/s.sh
APP_CHILD=$APP_DIR/c.sh
APP_AF_SHIM=$APP_DIR/f.so
APP_RESULT=$APP_DIR/r.txt
APP_ARM=$APP_DIR/a
APP_ARM_VALUE=L16_HOSTLESS_A1_INLINE_AF_CAPTURE_SUPERVISOR_ONCE_V1

CHILD=/data/local/tmp/light_l16_a1_inline_af_capture_once.sh
CHILD_RESULT=/data/local/tmp/light_l16_a1_inline_af_capture.result
CHILD_ARM=/data/local/tmp/light_l16_a1_inline_af_capture.armed
CHILD_ARM_VALUE=A1_INLINE_AF_CAPTURE_20000000NS_GAIN_1.0_ONCE
AF_SHIM=/data/local/tmp/liblcc_a1_focus_capture_shim.so
EXPECTED_CHILD_SIZE=61800
EXPECTED_CHILD_SHA1=9ea68ed71d9354b43aacf6f19b5c959baea93221
EXPECTED_AF_SHIM_SIZE=13764
EXPECTED_AF_SHIM_SHA1=67647b71767ab2b68a214fae87578e24eb3433b2
EXPECTED_MODE=A1_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE
EXPECTED_EXPOSURE_COUNT=1
EXPECTED_EXPOSURE_ORDER=common_for_selected_modules
EXPECTED_EXPOSURE_PLAN=selected:20000000
EXPECTED_AUTOFOCUS_RESPONSE=camera3_af_state_focused_locked_inline_hal_session
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
    rm -f "$CHILD_ARM" "$CHILD" "$AF_SHIM"

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

printf 'supervisor=L16_HOSTLESS_A1_INLINE_AF_CAPTURE_V1\n'
printf 'policy=single_fixed_same_session_A1_center_AF_then_20ms_gain_1_capture_and_reboot\n'

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

[ -r "$APP_AF_SHIM" ] || fail packaged_a1_af_shim_missing
APP_AF_SHIM_SIZE=$(/system/bin/toybox wc -c < "$APP_AF_SHIM") || \
    fail cannot_size_packaged_a1_af_shim
APP_AF_SHIM_SHA1=$(/system/bin/toybox sha1sum "$APP_AF_SHIM") || \
    fail cannot_hash_packaged_a1_af_shim
APP_AF_SHIM_SHA1=${APP_AF_SHIM_SHA1%% *}
printf 'packaged_a1_af_shim_size=%s\n' "$APP_AF_SHIM_SIZE"
printf 'packaged_a1_af_shim_sha1=%s\n' "$APP_AF_SHIM_SHA1"
[ "$APP_AF_SHIM_SIZE" = "$EXPECTED_AF_SHIM_SIZE" ] || \
    fail unexpected_packaged_a1_af_shim_size
[ "$APP_AF_SHIM_SHA1" = "$EXPECTED_AF_SHIM_SHA1" ] || \
    fail unexpected_packaged_a1_af_shim_hash

rm -f "$CHILD" "$CHILD_ARM" "$CHILD_RESULT" "$AF_SHIM"
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

cp "$APP_AF_SHIM" "$AF_SHIM" || fail cannot_stage_a1_af_shim
chmod 0400 "$AF_SHIM" || fail cannot_restrict_staged_a1_af_shim
STAGED_AF_SHIM_SIZE=$(/system/bin/toybox wc -c < "$AF_SHIM") || \
    fail cannot_size_staged_a1_af_shim
STAGED_AF_SHIM_SHA1=$(/system/bin/toybox sha1sum "$AF_SHIM") || \
    fail cannot_hash_staged_a1_af_shim
STAGED_AF_SHIM_SHA1=${STAGED_AF_SHIM_SHA1%% *}
[ "$STAGED_AF_SHIM_SIZE" = "$EXPECTED_AF_SHIM_SIZE" ] || \
    fail staged_a1_af_shim_size_mismatch
[ "$STAGED_AF_SHIM_SHA1" = "$EXPECTED_AF_SHIM_SHA1" ] || \
    fail staged_a1_af_shim_hash_mismatch
printf 'staged_a1_af_shim_sha1=%s\n' "$STAGED_AF_SHIM_SHA1"

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
/system/bin/timeout -k 10s 120s /system/bin/sh "$CHILD"
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
[ "$CHILD_FINAL_STATUS" = "PASS" ] || fail child_capture_failed
[ "$CAPTURE_ATTEMPTED" = "yes" ] || fail child_pass_without_capture_attempt

RESULT_MODE=$(result_field mode)
RESULT_EXPOSURE_COUNT=$(result_field exposure_argument_count)
RESULT_EXPOSURE_ORDER=$(result_field exposure_argument_module_order)
RESULT_EXPOSURE_PLAN=$(result_field exposure_plan_module_order)
AUTOFOCUS_ATTEMPTED=$(result_field autofocus_attempted)
AUTOFOCUS_EXIT_STATUS=$(result_field autofocus_exit_status)
AUTOFOCUS_RESPONSE=$(result_field autofocus_response)
A1_AF_SHIM_STATUS=$(result_field a1_af_shim)
LCC_EXIT_STATUS=$(result_field lcc_exit_status)
CLEANUP_OK=$(result_field cleanup_ok)
MANUAL_AFTER=$(result_field manual_control_after)
LCC_PROCESS_AFTER=$(result_field lcc_process_after)
SETTLED_CAMERA_CLIENTS=$(result_field settled_camera_clients)
MEDIA_AFTER=$(result_field media_after)
LIGHTSVR_AFTER=$(result_field lightsvr_after)
LRI_COUNT=$(result_field lri_output_count)
LRI_PATH=$(result_field lri_output_path)
LRI_SIZE=$(result_field lri_output_size)
LRI_SHA1=$(result_field lri_output_sha1)
WORKDIR=$(result_field workdir)

printf 'mode=%s\n' "$RESULT_MODE"
printf 'exposure_argument_count=%s\n' "$RESULT_EXPOSURE_COUNT"
printf 'exposure_argument_module_order=%s\n' "$RESULT_EXPOSURE_ORDER"
printf 'exposure_plan_module_order=%s\n' "$RESULT_EXPOSURE_PLAN"
printf 'autofocus_attempted=%s\n' "$AUTOFOCUS_ATTEMPTED"
printf 'autofocus_exit_status=%s\n' "$AUTOFOCUS_EXIT_STATUS"
printf 'autofocus_response=%s\n' "$AUTOFOCUS_RESPONSE"
printf 'a1_af_shim=%s\n' "$A1_AF_SHIM_STATUS"
printf 'lcc_exit_status=%s\n' "$LCC_EXIT_STATUS"
printf 'cleanup_ok=%s\n' "$CLEANUP_OK"
printf 'manual_control_after=%s\n' "$MANUAL_AFTER"
printf 'lcc_process_after=%s\n' "$LCC_PROCESS_AFTER"
printf 'settled_camera_clients=%s\n' "$SETTLED_CAMERA_CLIENTS"
printf 'media_after=%s\n' "$MEDIA_AFTER"
printf 'lightsvr_after=%s\n' "$LIGHTSVR_AFTER"
printf 'lri_output_count=%s\n' "$LRI_COUNT"
printf 'lri_output_path=%s\n' "$LRI_PATH"
printf 'lri_output_size=%s\n' "$LRI_SIZE"
printf 'lri_output_sha1=%s\n' "$LRI_SHA1"
printf 'workdir=%s\n' "$WORKDIR"

[ "$RESULT_MODE" = "$EXPECTED_MODE" ] || fail unexpected_child_mode
[ "$RESULT_EXPOSURE_COUNT" = "$EXPECTED_EXPOSURE_COUNT" ] || \
    fail unexpected_exposure_count
[ "$RESULT_EXPOSURE_ORDER" = "$EXPECTED_EXPOSURE_ORDER" ] || \
    fail unexpected_exposure_order
[ "$RESULT_EXPOSURE_PLAN" = "$EXPECTED_EXPOSURE_PLAN" ] || \
    fail unexpected_exposure_plan
[ "$AUTOFOCUS_ATTEMPTED" = "yes" ] || fail child_autofocus_not_attempted
[ "$AUTOFOCUS_EXIT_STATUS" = "0" ] || fail child_autofocus_nonzero
[ "$AUTOFOCUS_RESPONSE" = "$EXPECTED_AUTOFOCUS_RESPONSE" ] || \
    fail child_autofocus_response_unexpected
[ "$A1_AF_SHIM_STATUS" = "verified" ] || fail child_a1_af_shim_not_verified
[ "$LCC_EXIT_STATUS" = "0" ] || fail child_lcc_nonzero
[ "$CLEANUP_OK" = "yes" ] || fail child_cleanup_not_verified
case "$MANUAL_AFTER" in
    *0x0) ;;
    *) fail child_manual_control_not_zero ;;
esac
[ "$LCC_PROCESS_AFTER" = "no" ] || fail child_lcc_process_remains
[ "$SETTLED_CAMERA_CLIENTS" = "none" ] || fail child_camera_clients_not_settled
[ "$MEDIA_AFTER" = "running" ] || fail child_media_not_running
[ "$LIGHTSVR_AFTER" = "running" ] || fail child_lightsvr_not_running
[ "$LRI_COUNT" = "1" ] || fail child_lri_count_not_one
valid_lri_path "$LRI_PATH" || fail child_lri_path_invalid
valid_decimal "$LRI_SIZE" || fail child_lri_size_invalid
[ "$LRI_SIZE" -ge 32 ] || fail child_lri_too_small
valid_sha1 "$LRI_SHA1" || fail child_lri_sha1_invalid
case "$WORKDIR" in
    /data/local/tmp/light_l16_a1_inline_af_capture_run.*)
        WORK_PID=${WORKDIR#/data/local/tmp/light_l16_a1_inline_af_capture_run.}
        case "$WORK_PID" in
            ""|*[!0-9]*) fail child_workdir_invalid ;;
        esac
        ;;
    *) fail child_workdir_invalid ;;
esac

# Unlike the adb wrapper, the hostless app cannot pull and independently hash
# the output and diagnostics before deciding to remain up.  Therefore even a
# clean PASS deliberately ends in a normal reboot; the LRI itself is retained.
SUPERVISOR_STATUS=PASS
SUPERVISOR_REASON=same_session_a1_focus_and_capture_recorded_and_child_cleanup_verified
SUPERVISOR_DECISION=normal_reboot_after_hostless_capture_success
exit 0
