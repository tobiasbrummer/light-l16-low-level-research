#!/bin/sh
# SPDX-License-Identifier: MIT
# Build the async writer preload with the mmap-failure probe enabled.
#
# Same source as build_lcc_async_shim.sh; the probe is compiled in through
# L16_LOG_MMAP_FAILURES.  Without that define the build is bit-identical to
# the plain async shim, which is what keeps the existing profiles and their
# pinned hashes untouched.
#
# The probe is a diagnostic: it forwards every mmap unchanged and reports the
# errno that LccInterface::writeFile omits.  It does not patch the timeout.
set -eu

if [ "$#" -ne 1 ]; then
    printf 'usage: %s /absolute/output/liblcc_mmap_probe_shim.so\n' "$0" >&2
    exit 2
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(dirname "$SCRIPT_DIR")
SOURCE="$REPO_ROOT/shim/lcc_async_writer_shim.c"
OUTPUT=$1
OUTPUT_DIR=$(dirname "$OUTPUT")
OUTPUT_NAME=$(basename "$OUTPUT")
CLANG=${L16_CLANG:-clang}
LLD=${L16_LLD:-ld.lld}

case "$OUTPUT" in
    /*) ;;
    *)
        printf 'output path must be absolute\n' >&2
        exit 2
        ;;
esac

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR=$(CDPATH= cd -- "$OUTPUT_DIR" && pwd)
OUTPUT="$OUTPUT_DIR/$OUTPUT_NAME"
case "$OUTPUT" in
    "$REPO_ROOT"/*)
        printf 'refusing to place a generated binary inside the repository\n' >&2
        exit 2
        ;;
esac

[ -f "$SOURCE" ] || {
    printf 'missing source: %s\n' "$SOURCE" >&2
    exit 1
}
command -v "$CLANG" >/dev/null 2>&1 || {
    printf 'clang executable not found: %s\n' "$CLANG" >&2
    exit 1
}
[ -x "$LLD" ] || command -v "$LLD" >/dev/null 2>&1 || {
    printf 'LLD executable not found: %s\n' "$LLD" >&2
    exit 1
}

"$CLANG" \
    -DL16_LOG_MMAP_FAILURES=64u \
    --target=armv7a-linux-androideabi23 \
    --ld-path="$LLD" \
    -DL16_ANDROID_FREESTANDING \
    -std=c11 -Oz -fPIC -fvisibility=hidden \
    -fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables \
    -ffunction-sections -fdata-sections \
    -march=armv7-a -mthumb -mfloat-abi=softfp -mfpu=neon \
    -nostdlib -shared "$SOURCE" \
    -Wl,--gc-sections -Wl,--hash-style=sysv \
    -Wl,-z,now -Wl,-z,relro -Wl,-z,noexecstack \
    -Wl,--build-id=sha1 -Wl,-soname,liblcc_mmap_probe_shim.so \
    -o "$OUTPUT"

SIZE=$(wc -c < "$OUTPUT")
SHA1=$(sha1sum "$OUTPUT")
SHA1=${SHA1%% *}
SHA256=$(sha256sum "$OUTPUT")
SHA256=${SHA256%% *}
printf 'output=%s\nsize=%s\nsha1=%s\nsha256=%s\n' \
    "$OUTPUT" "$SIZE" "$SHA1" "$SHA256"
