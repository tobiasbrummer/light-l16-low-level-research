#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
OUTPUT_DIR="$PROJECT_ROOT/.build/dark-frame-series"
APK="$OUTPUT_DIR/light-l16-dark-frame-series-debug.apk"
SUPERVISOR="$PROJECT_ROOT/device/dark_frame_series_hostless_supervisor.sh"
CHILD="$PROJECT_ROOT/device/dark_frame_series_once.sh"
ASYNC_SHIM_BUILDER="$PROJECT_ROOT/host/build_lcc_async_shim.sh"
EXPECTED_SUPERVISOR_SIZE=13596
EXPECTED_SUPERVISOR_SHA256=c21385cc3b83f5e0abc342871916b3ad14e7f47b7f2120debedba1fd25847aad
EXPECTED_CHILD_SIZE=24542
EXPECTED_CHILD_SHA256=1ee205c65f56dec9291f5c188690dc9023e5eff6459af54c2edeb6dbc7127ff1
EXPECTED_ASYNC_SHIM_SIZE=9080
EXPECTED_ASYNC_SHIM_SHA256=f2da28cefc60027a884680ee9f4d0bf1966555982c7cacc9dda17ea65fa2be2b

find_sdk_root() {
    if [ -n "${ANDROID_SDK_ROOT:-}" ]; then
        printf '%s\n' "$ANDROID_SDK_ROOT"
        return
    fi
    if [ -n "${ANDROID_HOME:-}" ]; then
        printf '%s\n' "$ANDROID_HOME"
        return
    fi
    for candidate in \
        "$HOME/Android/Sdk" \
        "$HOME/android-sdk" \
        "$HOME/distrobox/android/home/android-sdk" \
        "$HOME/distrobox/android/home/.android/sdk"
    do
        if [ -d "$candidate/build-tools" ] && [ -d "$candidate/platforms" ]; then
            printf '%s\n' "$candidate"
            return
        fi
    done
    return 1
}

find_lld() {
    if [ -n "${L16_LLD:-}" ]; then
        printf '%s\n' "$L16_LLD"
        return
    fi
    if command -v ld.lld >/dev/null 2>&1; then
        command -v ld.lld
        return
    fi
    for candidate in \
        /usr/lib/llvm-20/bin/ld.lld \
        /usr/bin/ld.lld-20 \
        "$HOME"/.rustup/toolchains/*/lib/rustlib/*/bin/gcc-ld/ld.lld
    do
        if [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return
        fi
    done
    return 1
}

verify_source() {
    FILE=$1
    EXPECTED_SIZE=$2
    EXPECTED_SHA256=$3
    [ -f "$FILE" ] || {
        printf 'missing build input: %s\n' "$FILE" >&2
        exit 1
    }
    ACTUAL_SIZE=$(wc -c < "$FILE")
    ACTUAL_SHA256=$(sha256sum "$FILE")
    ACTUAL_SHA256=${ACTUAL_SHA256%% *}
    [ "$ACTUAL_SIZE" = "$EXPECTED_SIZE" ] && \
        [ "$ACTUAL_SHA256" = "$EXPECTED_SHA256" ] || {
            printf 'refusing changed payload: %s size=%s sha256=%s\n' \
                "$FILE" "$ACTUAL_SIZE" "$ACTUAL_SHA256" >&2
            exit 1
        }
    sh -n "$FILE"
}

verify_source "$SUPERVISOR" "$EXPECTED_SUPERVISOR_SIZE" \
    "$EXPECTED_SUPERVISOR_SHA256"
verify_source "$CHILD" "$EXPECTED_CHILD_SIZE" "$EXPECTED_CHILD_SHA256"
[ -x "$ASYNC_SHIM_BUILDER" ] || {
    printf 'missing executable shim builder: %s\n' "$ASYNC_SHIM_BUILDER" >&2
    exit 1
}

SDK_ROOT=$(find_sdk_root) || {
    printf '%s\n' 'Android SDK not found; set ANDROID_SDK_ROOT.' >&2
    exit 1
}
BUILD_TOOLS=$(
    find "$SDK_ROOT/build-tools" -mindepth 1 -maxdepth 1 -type d \
        | sort -V | tail -n 1
)
ANDROID_JAR=$(
    find "$SDK_ROOT/platforms" -mindepth 2 -maxdepth 2 -type f \
        -name android.jar | sort -V | tail -n 1
)
AAPT="$BUILD_TOOLS/aapt"
D8="$BUILD_TOOLS/d8"
ZIPALIGN="$BUILD_TOOLS/zipalign"
APKSIGNER="$BUILD_TOOLS/apksigner"
KEYSTORE=${LIGHT_L16_DEBUG_KEYSTORE:-"$HOME/.android/debug.keystore"}

for required in "$AAPT" "$D8" "$ZIPALIGN" "$APKSIGNER" "$ANDROID_JAR" "$KEYSTORE"; do
    [ -f "$required" ] || {
        printf 'missing build input: %s\n' "$required" >&2
        exit 1
    }
done
command -v javac >/dev/null 2>&1 || {
    printf '%s\n' 'javac not found' >&2
    exit 1
}

TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/light-l16-dark-frame-series.XXXXXX")
trap 'rm -rf "$TEMP_DIR"' EXIT HUP INT TERM
mkdir -p "$TEMP_DIR/classes" "$TEMP_DIR/dex" "$TEMP_DIR/assets" "$OUTPUT_DIR"
cp "$SUPERVISOR" "$TEMP_DIR/assets/dark_frame_series_hostless_supervisor.sh"
cp "$CHILD" "$TEMP_DIR/assets/dark_frame_series_once.sh"
ASYNC_SHIM="$TEMP_DIR/assets/liblcc_async_writer_shim.so"
LLD=$(find_lld) || {
    printf '%s\n' 'LLD not found; set L16_LLD.' >&2
    exit 1
}
L16_LLD="$LLD" "$ASYNC_SHIM_BUILDER" "$ASYNC_SHIM"
ASYNC_SHIM_SIZE=$(wc -c < "$ASYNC_SHIM")
ASYNC_SHIM_SHA256=$(sha256sum "$ASYNC_SHIM")
ASYNC_SHIM_SHA256=${ASYNC_SHIM_SHA256%% *}
[ "$ASYNC_SHIM_SIZE" = "$EXPECTED_ASYNC_SHIM_SIZE" ] && \
    [ "$ASYNC_SHIM_SHA256" = "$EXPECTED_ASYNC_SHIM_SHA256" ] || {
        printf 'refusing unexpected generated async shim: size=%s sha256=%s\n' \
            "$ASYNC_SHIM_SIZE" "$ASYNC_SHIM_SHA256" >&2
        exit 1
    }

"$AAPT" package -f \
    -M "$SCRIPT_DIR/AndroidManifest.xml" \
    -I "$ANDROID_JAR" \
    -A "$TEMP_DIR/assets" \
    -F "$TEMP_DIR/unsigned.apk"

javac -source 8 -target 8 \
    -bootclasspath "$ANDROID_JAR" \
    -d "$TEMP_DIR/classes" \
    "$SCRIPT_DIR/src/io/github/tobiasbrummer/lightl16/darkframe/MainActivity.java" \
    "$SCRIPT_DIR/src/io/github/tobiasbrummer/lightl16/darkframe/DarknessCheck.java"

find "$TEMP_DIR/classes" -type f -name '*.class' -print \
    | sort > "$TEMP_DIR/classes.list"
"$D8" --min-api 21 --lib "$ANDROID_JAR" \
    --output "$TEMP_DIR/dex" \
    $(cat "$TEMP_DIR/classes.list")

(
    cd "$TEMP_DIR/dex"
    "$AAPT" add "$TEMP_DIR/unsigned.apk" classes.dex >/dev/null
)
"$ZIPALIGN" -f 4 "$TEMP_DIR/unsigned.apk" "$TEMP_DIR/aligned.apk"
"$APKSIGNER" sign \
    --ks "$KEYSTORE" \
    --ks-pass pass:android \
    --key-pass pass:android \
    --out "$APK" \
    "$TEMP_DIR/aligned.apk"
"$APKSIGNER" verify --verbose "$APK" >/dev/null

printf 'apk=%s\n' "$APK"
sha256sum "$APK"
