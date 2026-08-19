from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "meter-focus-probe"
SOURCE = APP / "src/io/github/tobiasbrummer/lightl16/meterfocusprobe/MainActivity.java"


def test_probe_declares_only_camera_permission():
    manifest = (APP / "AndroidManifest.xml").read_text()
    assert 'android.permission.CAMERA' in manifest
    assert manifest.count("uses-permission") == 1
    assert 'android:debuggable="false"' in manifest


def test_probe_uses_bounded_ae_then_af_camera2_flow():
    source = SOURCE.read_text()
    assert "AE_TIMEOUT_MS = 5000L" in source
    assert "AF_TIMEOUT_MS = 8000L" in source
    assert "CONTROL_AE_REGIONS" in source
    assert "SENSOR_EXPOSURE_TIME" in source
    assert "CONTROL_AF_REGIONS" in source
    assert "CONTROL_AF_TRIGGER_START" in source
    assert source.index("startMetering();") < source.index("private void startFocus()")


def test_probe_has_no_root_or_low_level_control_surface():
    combined = "\n".join(
        path.read_text()
        for path in (APP / "AndroidManifest.xml", SOURCE, APP / "build_debug_apk.sh")
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


def test_probe_closes_camera_resources_on_all_terminal_paths():
    source = SOURCE.read_text()
    finish_start = source.index("private void finishProbe(")
    finish_end = source.index("private synchronized void closeCameraResources()")
    finish_body = source[finish_start:finish_end]
    assert "closeCameraResources();" in finish_body
    assert "captureSession.close()" in source
    assert "cameraDevice.close()" in source
    assert "cameraThread.quitSafely()" in source
