from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "hdr-meter-probe"
PACKAGE_PATH = APP / "src/io/github/tobiasbrummer/lightl16/hdrmeterprobe"
SOURCE = PACKAGE_PATH / "MainActivity.java"
MATH = PACKAGE_PATH / "HdrMath.java"


def test_hdr_meter_is_camera_only_and_has_no_root_surface() -> None:
    manifest = (APP / "AndroidManifest.xml").read_text()
    assert 'package="io.github.tobiasbrummer.lightl16.hdrmeterprobe"' in manifest
    assert manifest.count("uses-permission") == 1
    assert "android.permission.CAMERA" in manifest
    assert 'android:debuggable="false"' in manifest
    combined = "\n".join(
        path.read_text()
        for path in (APP / "AndroidManifest.xml", SOURCE, MATH,
                     APP / "build_debug_apk.sh")
    )
    for forbidden in (
        "persist.sys.fihop",
        "/system/etc/lcc",
        "prog_app_p2",
        "manual_control",
        "Runtime.getRuntime().exec",
        "ProcessBuilder",
    ):
        assert forbidden not in combined


def test_hdr_meter_uses_ae_anchor_and_continuous_yuv_only() -> None:
    source = SOURCE.read_text()
    assert "SENSOR_EXPOSURE_TIME" in source
    assert "SENSOR_SENSITIVITY" in source
    assert "iso100Equivalent" in source
    assert "ImageFormat.YUV_420_888" in source
    assert "MEASUREMENT_FRAME_COUNT = 8" in source
    assert "SETTLE_FRAME_COUNT = 3" in source
    assert "CONTROL_AE_LOCK" in source
    assert "CONTROL_AWB_LOCK" in source
    assert "CONTROL_AE_EXPOSURE_COMPENSATION" in source
    assert "PHASE_HIGHLIGHT_WAIT_AE" in source
    assert "HIGHLIGHT_FRAME_COUNT = 4" in source
    assert "ImageFormat.RAW_SENSOR" not in source
    assert "SENSOR_EXPOSURE_TIME," not in source
    assert "raw_still_requested=no" in source


def test_hdr_meter_measures_highlights_and_temporal_shadow_snr() -> None:
    source = SOURCE.read_text()
    math = MATH.read_text()
    assert "9999, 10000" in source
    assert "shadow_selection=yuv_mean_p1_to_p5" in source
    assert "shadow_temporal_snr_proxy" in source
    assert "highlight_p99_99_below_white" in source
    assert "highlight_still_clipped_at_min_ae_compensation" in source
    assert "squaredSums" in source
    assert "TARGET_HIGHLIGHT_LINEAR_FRACTION = 0.70" in math
    assert "TARGET_SHADOW_SNR = 8.0" in math
    assert "ASSUMED_YUV_GAMMA = 2.2" in math
    assert "YUV_GAMMA_AND_TEMPORAL_SNR_PROXY" in source


def test_hdr_meter_outputs_adaptive_four_bayer_plan_without_execution() -> None:
    source = SOURCE.read_text()
    math = MATH.read_text()
    assert "logarithmicFour" in math
    assert "PROVEN_PILOT_MAX_EXPOSURE_NS = 20000000L" in math
    assert "ideal_A1_exposure_ns=" in source
    assert "ideal_A3_exposure_ns=" in source
    assert "ideal_A4_exposure_ns=" in source
    assert "ideal_A5_exposure_ns=" in source
    assert "pilot_A2_exposure_ns=" in source
    assert "A2_calibration_status=NEEDS_PAN_TO_BAYER_RESPONSE_CALIBRATION" in source
    assert "root_capture_plan_status=UNVERIFIED_NOT_EXECUTED" in source
    assert "yuv_to_lcc_response_transfer=UNVERIFIED_REQUIRES_PAIRED_LRI" in source


def test_hdr_meter_persists_display_and_closes_every_camera_resource() -> None:
    source = SOURCE.read_text()
    assert '"light-l16-hdr-meter-last-display.txt"' in source
    assert "getExternalFilesDir(null)" in source
    assert "persistDisplayedReport(snapshot)" in source
    assert "captureSession.close()" in source
    assert "cameraDevice.close()" in source
    assert "yuvReader.close()" in source
    assert "previewSurface.release()" in source
    assert "cameraThread.quitSafely()" in source
    assert "root_or_lcc_invoked=no" in source


def test_hdr_math_reference_cases(tmp_path: Path) -> None:
    javac = shutil.which("javac")
    java = shutil.which("java")
    if javac is None or java is None:
        pytest.skip("JDK not installed")
    harness = tmp_path / "HdrMathHarness.java"
    harness.write_text(
        """
package io.github.tobiasbrummer.lightl16.hdrmeterprobe;

public final class HdrMathHarness {
    private static void require(boolean value, String name) {
        if (!value) throw new AssertionError(name);
    }
    private static void close(double actual, double expected, String name) {
        if (Math.abs(actual - expected) > 0.000001) throw new AssertionError(name);
    }
    public static void main(String[] args) {
        require(HdrMath.iso100Equivalent(8333333L, 100) == 8333333L, "iso100");
        require(HdrMath.iso100Equivalent(2000000L, 400) == 8000000L,
            "iso400_equivalent");
        close(HdrMath.gammaDecode(0.5), Math.pow(0.5, 2.2), "gamma");
        close(HdrMath.snrAtIso100Equivalent(4.0, 400), 8.0, "snr_equivalent");
        long[] histogram = new long[] {1L, 2L, 3L, 4L};
        require(HdrMath.percentileBin(histogram, 10L, 9, 10) == 3, "p90");
        long[] geometric = HdrMath.logarithmicFour(1000000L, 8000000L);
        require(geometric[0] == 1000000L, "geo0");
        require(geometric[1] == 2000000L, "geo1");
        require(geometric[2] == 4000000L, "geo2");
        require(geometric[3] == 8000000L, "geo3");
        HdrMath.Plan flat = HdrMath.makeAdaptivePlan(
            2000000L, 0.70, 2000000L, 8.0, 10000L, 30000000L);
        require(flat.idealBayerNs[0] == 2000000L, "flat_short");
        require(flat.idealBayerNs[3] == 2000000L, "flat_long");
        require(!flat.pilotRangeClamped, "flat_unclamped");
        HdrMath.Plan capped = HdrMath.makeAdaptivePlan(
            5000000L, 0.70, 5000000L, 2.0, 10000L, 30000000L);
        require(capped.idealBayerNs[0] == 5000000L, "capped_short");
        require(capped.idealBayerNs[3] == 30000000L, "sensor_long_cap");
        require(capped.shadowEndpointClamped, "shadow_clamped");
        require(capped.pilotBayerNs[3] == 20000000L, "pilot_long_cap");
        require(capped.provisionalA2Ns == capped.pilotBayerNs[0], "a2_safe");
        require(capped.pilotRangeClamped, "pilot_clamped");
    }
}
""".strip()
        + "\n"
    )
    subprocess.run(
        [javac, "-d", str(tmp_path), str(MATH), str(harness)], check=True
    )
    subprocess.run(
        [java, "-cp", str(tmp_path),
         "io.github.tobiasbrummer.lightl16.hdrmeterprobe.HdrMathHarness"],
        check=True,
    )
