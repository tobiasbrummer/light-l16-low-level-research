#!/bin/sh
# SPDX-License-Identifier: MIT
# Explicit entry point for the fixed single-request, per-module HDR profile.
set -eu

CONFIRM=--execute-fixed-all16-hdr-async-shim-1p25-5-20ms-once-and-reboot

describe_profile() {
    printf '%s\n' 'Light L16 fixed single-request HDR profile'
    printf '%s\n' 'mask: FE FF 01 (A1-A5, B1-B5, C1-C6)'
    printf '%s\n' 'gain: 1.0 for all modules'
    printf '%-4s %-10s %-8s %s\n' module exposure role sensor
    printf '%-4s %-10s %-8s %s\n' A1 1.25ms short color
    printf '%-4s %-10s %-8s %s\n' A2 20ms long mono
    printf '%-4s %-10s %-8s %s\n' A3 5ms medium color
    printf '%-4s %-10s %-8s %s\n' A4 5ms medium color
    printf '%-4s %-10s %-8s %s\n' A5 20ms long color
    printf '%-4s %-10s %-8s %s\n' B1 20ms long color
    printf '%-4s %-10s %-8s %s\n' B2 5ms medium color
    printf '%-4s %-10s %-8s %s\n' B3 5ms medium color
    printf '%-4s %-10s %-8s %s\n' B4 1.25ms short color
    printf '%-4s %-10s %-8s %s\n' B5 20ms long color
    printf '%-4s %-10s %-8s %s\n' C1 20ms long color
    printf '%-4s %-10s %-8s %s\n' C2 5ms medium color
    printf '%-4s %-10s %-8s %s\n' C3 5ms medium color
    printf '%-4s %-10s %-8s %s\n' C4 20ms long color
    printf '%-4s %-10s %-8s %s\n' C5 1.25ms short color
    printf '%-4s %-10s %-8s %s\n' C6 20ms long mono
    printf '%s\n' 'capture: one lcc request, one original LRI, async writer shim, mandatory reboot'
    printf '%s\n' 'status: host/static validation only; this exposure profile has not run on a camera yet'
}

case "${1-}" in
    --describe)
        [ "$#" -eq 1 ] || exit 2
        describe_profile
        exit 0
        ;;
    "$CONFIRM")
        [ "$#" -eq 1 ] || exit 2
        ;;
    *)
        describe_profile >&2
        printf '\nusage:\n  %s --describe\n  %s %s\n' \
            "$0" "$0" "$CONFIRM" >&2
        printf '%s\n' 'No ADB or camera action was attempted.' >&2
        exit 2
        ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$SCRIPT_DIR/run_a1_capture_once.sh" "$CONFIRM"
