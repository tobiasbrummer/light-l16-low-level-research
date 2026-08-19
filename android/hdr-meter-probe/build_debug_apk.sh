#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
OUTPUT_DIR="$PROJECT_ROOT/.build/hdr-meter-probe"
APK="$OUTPUT_DIR/light-l16-hdr-meter-probe-debug.apk"

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

TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/light-l16-hdr-meter.XXXXXX")
trap 'rm -rf "$TEMP_DIR"' EXIT HUP INT TERM
mkdir -p "$TEMP_DIR/classes" "$TEMP_DIR/dex" "$OUTPUT_DIR"

"$AAPT" package -f \
    -M "$SCRIPT_DIR/AndroidManifest.xml" \
    -I "$ANDROID_JAR" \
    -F "$TEMP_DIR/unsigned.apk"

find "$SCRIPT_DIR/src" -type f -name '*.java' -print \
    | sort > "$TEMP_DIR/sources.list"
javac -source 8 -target 8 \
    -bootclasspath "$ANDROID_JAR" \
    -d "$TEMP_DIR/classes" \
    @"$TEMP_DIR/sources.list"

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
