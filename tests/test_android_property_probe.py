from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "android" / "property-probe"
SOURCE = PROBE / "src" / "io" / "github" / "tobiasbrummer" / "lightl16" / "propertyprobe" / "MainActivity.java"


def test_probe_manifest_requests_no_permissions() -> None:
    manifest = (PROBE / "AndroidManifest.xml").read_text()
    assert "<uses-permission" not in manifest
    assert 'android:debuggable="true"' in manifest


def test_probe_setter_has_exact_one_property_allowlist() -> None:
    source = SOURCE.read_text()
    assert 'PROBE_PROPERTY = "persist.sys.fihop5"' in source
    assert "if (!PROBE_PROPERTY.equals(key))" in source
    assert 'throw new SecurityException("refusing non-probe property write")' in source

    body_before_declaration = source.split(
        "private static void setProperty(String key, String value)", 1
    )[0]
    call_arguments = re.findall(r"setProperty\(([^,]+),", body_before_declaration)
    assert call_arguments
    assert set(call_arguments) == {"PROBE_PROPERTY"}


def test_probe_never_writes_runner_trigger_or_other_arguments() -> None:
    source = SOURCE.read_text()
    assert 'TRIGGER_PROPERTY = "persist.sys.fihop"' in source
    assert "getProperty(TRIGGER_PROPERTY)" in source
    assert "setProperty(TRIGGER_PROPERTY" not in source
    assert "setProperty(key" not in source
    assert "Runtime.getRuntime" not in source
    assert "ProcessBuilder" not in source


def test_probe_requires_neutral_runner_and_clears_marker() -> None:
    source = SOURCE.read_text()
    assert 'if (!"0".equals(trigger))' in source
    assert "for (String key : OTHER_ARGUMENT_PROPERTIES)" in source
    assert 'setProperty(PROBE_PROPERTY, "")' in source
    assert 'append("cleanup=")' in source


def test_probe_has_no_sensitive_android_permissions_or_apis() -> None:
    combined = "\n".join(
        [
            (PROBE / "AndroidManifest.xml").read_text(),
            SOURCE.read_text(),
        ]
    )
    forbidden = (
        "android.permission.CAMERA",
        "android.permission.INTERNET",
        "android.permission.READ_EXTERNAL_STORAGE",
        "android.permission.WRITE_EXTERNAL_STORAGE",
        "android.hardware.Camera",
        "android.hardware.camera2",
        "java.net.",
        "Runtime.getRuntime",
        "ProcessBuilder",
        "setprop ",
    )
    for value in forbidden:
        assert value not in combined
