#!/bin/sh
# SPDX-License-Identifier: MIT
# Explicit entry point for the fixed all-16 profile.
set -eu

CONFIRM=--execute-fixed-all16-20ms-once-and-reboot
if [ "$#" -ne 1 ] || [ "$1" != "$CONFIRM" ]; then
    printf 'usage: %s %s\n' "$0" "$CONFIRM" >&2
    printf 'This performs one real 20 ms all-16 lcc attempt and always reboots.\n' >&2
    exit 2
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$SCRIPT_DIR/run_a1_capture_once.sh" "$CONFIRM"
