#!/bin/sh
# SPDX-License-Identifier: MIT
# Explicit entry point for the fixed same-session A1-A5 center-AF profile.
set -eu

CONFIRM=--execute-fixed-a-group-inline-af-then-20ms-capture-once-and-reboot

case "${1-}" in
    --describe)
        [ "$#" -eq 1 ] || exit 2
        printf '%s\n' 'Light L16 fixed same-session A1-A5 focus capture'
        printf '%s\n' 'mask: 3E 00 00 (A1-A5; no movable mirrors)'
        printf '%s\n' 'focus: Camera3 AUTO, center-half ROI, exact FOCUSED_LOCKED gate'
        printf '%s\n' 'capture: one RAW10 surface per A module, 20 ms, gain 1.0'
        printf '%s\n' 'safety: fixed profile, one attempt, mandatory normal reboot'
        printf '%s\n' 'status: physical A1-A5 LRI and matching hostless supervisor PASS verified'
        exit 0
        ;;
    "$CONFIRM")
        [ "$#" -eq 1 ] || exit 2
        ;;
    *)
        printf 'usage: %s {--describe|%s}\n' "$0" "$CONFIRM" >&2
        printf '%s\n' 'No ADB or camera action was attempted.' >&2
        exit 2
        ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$SCRIPT_DIR/run_a1_capture_once.sh" "$CONFIRM"
