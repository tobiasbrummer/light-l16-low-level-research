#!/bin/sh
# SPDX-License-Identifier: MIT
# Explicit entry point for the fixed synchronous or reversible async all-16 profile.
set -eu

CONFIRM_SYNC=--execute-fixed-all16-20ms-once-and-reboot
CONFIRM_ASYNC=--execute-fixed-all16-async-shim-20ms-once-and-reboot
case "${1-}" in
    "$CONFIRM_SYNC"|"$CONFIRM_ASYNC")
        [ "$#" -eq 1 ] || exit 2
        ;;
    *)
        printf 'usage: %s {%s|%s}\n' "$0" "$CONFIRM_SYNC" "$CONFIRM_ASYNC" >&2
        printf 'Each performs one real 20 ms all-16 lcc attempt and always reboots.\n' >&2
        exit 2
        ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$SCRIPT_DIR/run_a1_capture_once.sh" "$1"
