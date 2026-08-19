from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "stock-lri-capture"
SOURCE = APP / "src" / "io" / "github" / "tobiasbrummer" / "lightl16" / "stocklricapture" / "MainActivity.java"


def test_stock_path_app_is_non_rooting_and_fixed():
    source = SOURCE.read_text()
    assert "private static final int LIGHT_RAW10 = 48;" in source
    assert 'private static final String CAMERA_ID = "0";' in source
    assert "private static final float FIXED_FOCAL_LENGTH = 2.8f;" in source
    assert "private static final float FIXED_ZOOM_FACTOR = 1.0f;" in source
    assert "FOCUS_TYPE_USER_HW = 6" in source
    assert "EXPECTED_ACTIVE_WIDTH = 4160" in source
    assert "EXPECTED_ACTIVE_HEIGHT = 3120" in source
    assert "EXPECTED_RAW_STREAM_WIDTH = 3840" in source
    assert "EXPECTED_RAW_STREAM_HEIGHT = 2160" in source
    assert "TEMPLATE_STILL_CAPTURE" in source
    assert "getOutputSizes(LIGHT_RAW10)" in source
    assert '"co.light.stacked_capture_state"' in source
    assert '"co.light.zoom_factor"' in source
    assert '"co.light.focus_type"' in source
    assert "CaptureRequest.SCALER_CROP_REGION" in source
    assert '"co.light.stacked_capture_fw"' in source
    assert '"co.light.stacked_capture_total_size"' in source
    assert '"co.light.stacked_capture_num_transfers"' in source
    assert "unexpected_lri_payload" in source
    assert "MIN_LRI_BYTES" in source
    assert "MIN_FREE_BYTES = 512L * 1024L * 1024L" in source
    assert "fihop" not in source
    assert "Runtime.getRuntime" not in source
    assert "ProcessBuilder" not in source
    assert '"lcc"' not in source


def test_stock_path_manifest_has_only_required_permissions():
    manifest = (APP / "AndroidManifest.xml").read_text()
    assert "android.permission.CAMERA" in manifest
    assert "android.permission.WRITE_EXTERNAL_STORAGE" in manifest
    assert "INTERNET" not in manifest
    assert "REBOOT" not in manifest


def test_stock_path_docs_state_live_boundary():
    readme = (APP / "README.md").read_text()
    assert "no root runner" in readme.lower()
    assert "displayed `result=PASS`" in readme
    assert "transferred LRI now independently verifies" in readme
    assert "JPEG has not yet been transferred" in readme
    assert "format 48" in readme
    assert "3840 x 2160" in readme
    assert "4160 x 3120 sensor active array" in readme
    assert "No reboot is expected" in readme
