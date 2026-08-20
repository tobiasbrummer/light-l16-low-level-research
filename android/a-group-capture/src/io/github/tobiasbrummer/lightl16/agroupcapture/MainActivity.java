package io.github.tobiasbrummer.lightl16.agroupcapture;

import android.app.Activity;
import android.os.Bundle;
import android.os.Process;
import android.os.SystemClock;
import android.text.method.ScrollingMovementMethod;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

/**
 * Owner-controlled, one-install/one-shot A1-A5 capture for the Light L16.
 *
 * There is no command input or selectable camera parameter.  The only root
 * program, scripts, preload, module, exposure, gain, result path, and property
 * sequence are compile-time constants and all packaged payloads are hash pinned.
 */
public final class MainActivity extends Activity {
    private static final String TRIGGER = "persist.sys.fihop";
    private static final String ARG1 = "persist.sys.fihop1";
    private static final String ARG2 = "persist.sys.fihop2";
    private static final String ARG3 = "persist.sys.fihop3";
    private static final String ARG4 = "persist.sys.fihop4";
    private static final String ARG5 = "persist.sys.fihop5";
    private static final String[] RUNNER_PROPERTIES = {
        TRIGGER, ARG1, ARG2, ARG3, ARG4, ARG5
    };

    private static final String EXPECTED_BUILD = "00WW_1_351";
    private static final String EXPECTED_BUILD_TYPE = "user";
    private static final String EXPECTED_DEBUGGABLE = "0";
    private static final String EXPECTED_MODEL = "L16";
    private static final String EXPECTED_PRODUCT = "LFC_0002_FIH01";
    private static final String EXPECTED_KERNEL = "3.18.20-perf-g32d1d1c";
    private static final String EXPECTED_SELINUX_ENFORCE = "0";
    private static final String EXPECTED_BOOT_MODE = "unknown";
    private static final String EXPECTED_FIHOP_STATE = "stopped";
    private static final String EXPECTED_FIHOP_SHA256 =
        "6550cce118492e43c5285d469f7dc383e4d6c14c7cf766de1c82cb57fbaebe4f";
    private static final long EXPECTED_FIHOP_SIZE = 1649L;
    private static final String FIHOP_SCRIPT = "/system/etc/fihop.sh";
    private static final String SELINUX_ENFORCE_PATH = "/sys/fs/selinux/enforce";

    private static final String PRIVATE_DIR =
        "/data/data/io.github.tobiasbrummer.lightl16.agroupcapture/files";
    private static final String USER_ZERO_PRIVATE_DIR =
        "/data/user/0/io.github.tobiasbrummer.lightl16.agroupcapture/files";
    private static final String SUPERVISOR_PATH = PRIVATE_DIR + "/s.sh";
    private static final String CHILD_PATH = PRIVATE_DIR + "/c.sh";
    private static final String AF_SHIM_PATH = PRIVATE_DIR + "/f.so";
    private static final String RESULT_PATH = PRIVATE_DIR + "/r.txt";
    private static final String ARM_PATH = PRIVATE_DIR + "/a";
    private static final String SPENT_NAME = "spent";
    private static final String DISPLAY_REPORT_NAME =
        "light-l16-a-group-inline-af-last-display.txt";
    private static final String RUNNER_PROGRAM = "/system/bin/sh";

    private static final String SUPERVISOR_ASSET =
        "a_group_hostless_capture_supervisor.sh";
    private static final String CHILD_ASSET = "a1_capture_once.sh";
    private static final String AF_SHIM_ASSET =
        "liblcc_a1_focus_capture_shim.so";
    private static final long EXPECTED_SUPERVISOR_SIZE = 13959L;
    private static final String EXPECTED_SUPERVISOR_SHA256 =
        "301154b62ef8ef092cdc61a2e24a3ef68151e4ea3febdd7bc7516a962ab87075";
    private static final long EXPECTED_CHILD_SIZE = 61800L;
    private static final String EXPECTED_CHILD_SHA256 =
        "333eb660e88f278e7d42c60fe0656bc74bf6b8f678b88f462598887606c0ca1f";
    private static final long EXPECTED_AF_SHIM_SIZE = 13764L;
    private static final String EXPECTED_AF_SHIM_SHA256 =
        "72d1d05a6966cafbf92b7b5b45b82243d24da1a35a18b734097196357dc59ad6";
    private static final String ARM_VALUE =
        "L16_HOSTLESS_A_GROUP_INLINE_AF_CAPTURE_SUPERVISOR_ONCE_V1";
    private static final String SPENT_VALUE =
        "L16_HOSTLESS_A_GROUP_INLINE_AF_CAPTURE_SPENT_V1";

    private static final long ARM_WINDOW_MS = 60000L;
    private static final long POLL_TIMEOUT_MS = 135000L;
    private static final long POLL_INTERVAL_MS = 250L;
    private static final long SETTLE_TIMEOUT_MS = 5000L;
    private static final long MAX_RESULT_SIZE = 16384L;

    private TextView output;
    private Button preflightButton;
    private Button captureButton;
    private boolean running;
    private boolean uiArmed;
    private long uiArmDeadline;

    private static final class PreflightResult {
        final boolean passed;
        final String report;

        PreflightResult(boolean passed, String report) {
            this.passed = passed;
            this.report = report;
        }
    }

    private static final class AssetInfo {
        final long size;
        final String sha256;

        AssetInfo(long size, String sha256) {
            this.size = size;
            this.sha256 = sha256;
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        int padding = dp(20);
        body.setPadding(padding, padding, padding, padding);

        TextView explanation = new TextView(this);
        explanation.setText(
            "Feste Same-Session-Aufnahme: Der eingebettete, fest begrenzte "
                + "Fokus-Hook fokussiert die Bildmitte, während die von lcc "
                + "für A1-A5 geöffnete HAL-Preview aktiv bleibt. Nur nach "
                + "bestätigtem FOCUSED_LOCKED werden die fünf A-Module mit "
                + "20 ms und Gain 1 ausgelöst, genau einmal pro "
                + "App-Installation.\n\n"
                + "Stufe 1 prüft Gerät, Root-Runner und die eingebauten "
                + "Skripte sowie den Fokus-Hook nur lesend. Stufe 2 löst eine "
                + "echte Aufnahme aus. "
                + "Sobald der Kamerapfad möglicherweise betreten wurde, folgt "
                + "absichtlich ein normaler Neustart. Das neue LRI bleibt unter "
                + "/sdcard/DCIM/camera erhalten.\n\n"
                + "Vorher die normale Kamera-App vollständig schließen."
        );
        body.addView(explanation);

        preflightButton = new Button(this);
        preflightButton.setText("1. VORPRÜFUNG & SCHARFSCHALTEN");
        preflightButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View ignored) {
                startPreflight();
            }
        });
        body.addView(preflightButton);

        captureButton = new Button(this);
        captureButton.setText("2. A1-A5 CENTER-AF + 20 MS AUSLÖSEN");
        captureButton.setEnabled(false);
        captureButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View ignored) {
                startCapture();
            }
        });
        body.addView(captureButton);

        output = new TextView(this);
        output.setTextIsSelectable(true);
        output.setMovementMethod(new ScrollingMovementMethod());
        setOutputText("Noch nicht geprüft.\n");
        body.addView(output);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(body);
        setContentView(scroll);

        showPersistentState();
    }

    private int dp(int value) {
        float density = getResources().getDisplayMetrics().density;
        return (int) (value * density + 0.5f);
    }

    private void setOutputText(String text) {
        output.setText(text);
        persistDisplayedReport(text);
    }

    private void persistDisplayedReport(String text) {
        File directory = getExternalFilesDir(null);
        if (directory == null) {
            return;
        }
        File report = new File(directory, DISPLAY_REPORT_NAME);
        try {
            FileOutputStream stream = new FileOutputStream(report, false);
            try {
                stream.write(text.getBytes(StandardCharsets.UTF_8));
                stream.getFD().sync();
            } finally {
                stream.close();
            }
        } catch (Throwable ignored) {
            // The diagnostic copy must never change capture or recovery policy.
        }
    }

    private void showPersistentState() {
        try {
            File spent = privateFile(SPENT_NAME);
            File result = privateFile("r.txt");
            if (!spent.exists()) {
                return;
            }
            preflightButton.setEnabled(false);
            captureButton.setEnabled(false);
            StringBuilder report = new StringBuilder();
            report.append("Diese Installation wurde bereits verbraucht.\n");
            if (result.exists() && result.length() > 0L) {
                String resultText = readAscii(result);
                report.append("\nLetztes Supervisor-Ergebnis:\n");
                report.append(resultText);
                if (validPassResult(resultText)) {
                    report.append("app_interpretation=PASS_MANIFEST_REBOOT_REQUESTED\n");
                } else if (validPreflightFailure(resultText)) {
                    report.append("app_interpretation=PREFLIGHT_REFUSED_NO_CAMERA_ATTEMPT\n");
                } else {
                    report.append("app_interpretation=AMBIGUOUS_DO_NOT_RETRY\n");
                }
            } else {
                report.append(
                    "Ergebnis fehlt oder war beim Neustart noch nicht sichtbar. "
                        + "Nicht erneut auslösen; erst normal neu starten und "
                        + "gegebenenfalls per ADB diagnostizieren.\n"
                );
            }
            report.append(
                "\nFür einen späteren bewussten Wiederholungstest muss die App "
                    + "deinstalliert und frisch installiert werden.\n"
            );
            setOutputText(report.toString());
        } catch (Throwable error) {
            preflightButton.setEnabled(false);
            captureButton.setEnabled(false);
            setOutputText(
                "Persistenter Zustand nicht lesbar: " + safeError(error) + "\n");
        }
    }

    private void startPreflight() {
        if (running || privateFile(SPENT_NAME).exists()) {
            return;
        }
        running = true;
        uiArmed = false;
        preflightButton.setEnabled(false);
        captureButton.setEnabled(false);
        setOutputText("Nur-lesende Vorprüfung läuft …\n");

        new Thread(new Runnable() {
            @Override
            public void run() {
                final PreflightResult result = runReadOnlyPreflight();
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        setOutputText(result.report);
                        running = false;
                        if (result.passed) {
                            uiArmed = true;
                            uiArmDeadline = SystemClock.elapsedRealtime() + ARM_WINDOW_MS;
                            captureButton.setEnabled(true);
                            preflightButton.setText("VORPRÜFUNG PASS – 60 S SCHARF");
                        } else {
                            preflightButton.setEnabled(true);
                            preflightButton.setText("VORPRÜFUNG WIEDERHOLEN");
                        }
                    }
                });
            }
        }, "l16-a-group-read-only-preflight").start();
    }

    private void startCapture() {
        if (running || !uiArmed || privateFile(SPENT_NAME).exists()) {
            return;
        }
        if (SystemClock.elapsedRealtime() > uiArmDeadline) {
            uiArmed = false;
            captureButton.setEnabled(false);
            preflightButton.setEnabled(true);
            preflightButton.setText("1. VORPRÜFUNG ERNEUT STARTEN");
            setOutputText("Scharfschaltung nach 60 Sekunden abgelaufen.\n");
            return;
        }
        running = true;
        uiArmed = false;
        preflightButton.setEnabled(false);
        captureButton.setEnabled(false);
        setOutputText(
            "Der feste Root-Ablauf startet lcc. Innerhalb derselben offenen "
                + "HAL-Sitzung wird Center-AF ausgeführt; nur bei "
                + "FOCUSED_LOCKED werden anschließend genau A1-A5 mit 20 ms "
                + "ausgelöst …\n"
        );
        new Thread(new Runnable() {
            @Override public void run() {
                final String report = runCaptureOnce();
                runOnUiThread(new Runnable() {
                    @Override public void run() {
                        setOutputText(report);
                        running = false;
                        if (!privateFile(SPENT_NAME).exists()) {
                            preflightButton.setEnabled(true);
                            preflightButton.setText("1. VORPRÜFUNG ERNEUT STARTEN");
                        }
                    }
                });
            }
        }, "l16-a-group-inline-focus-capture-once").start();
    }

    private PreflightResult runReadOnlyPreflight() {
        StringBuilder report = new StringBuilder();
        try {
            inspectTargetAndAssets(report, true);
            report.append("preflight=PASS\n");
            report.append("armed_for_seconds=60\n");
            report.append("camera_not_touched=yes\n");
            return new PreflightResult(true, report.toString());
        } catch (Throwable error) {
            report.append("preflight=REFUSED\nreason=")
                .append(safeError(error)).append('\n');
            report.append("camera_not_touched=yes\n");
            return new PreflightResult(false, report.toString());
        }
    }

    private String runCaptureOnce() {
        StringBuilder report = new StringBuilder();
        boolean propertiesTouched = false;
        boolean triggerAttempted = false;
        boolean completed = false;

        try {
            inspectTargetAndAssets(report, false);

            File supervisor = privateFile("s.sh");
            File child = privateFile("c.sh");
            File afShim = privateFile("f.so");
            File result = privateFile("r.txt");
            File arm = privateFile("a");
            File spent = privateFile(SPENT_NAME);
            if (supervisor.exists() || child.exists() || afShim.exists()
                    || result.exists()
                    || arm.exists() || spent.exists()) {
                throw new IllegalStateException("stale_or_spent_private_capture_state");
            }

            copyAssetToPrivateFile(SUPERVISOR_ASSET, supervisor);
            copyAssetToPrivateFile(CHILD_ASSET, child);
            copyAssetToPrivateFile(AF_SHIM_ASSET, afShim);
            writePrivateFile(result, new byte[0]);
            writePrivateFile(arm, (ARM_VALUE + "\n").getBytes(StandardCharsets.US_ASCII));

            verifyFile(supervisor, EXPECTED_SUPERVISOR_SIZE,
                EXPECTED_SUPERVISOR_SHA256, "staged_supervisor");
            verifyFile(child, EXPECTED_CHILD_SIZE,
                EXPECTED_CHILD_SHA256, "staged_child");
            verifyFile(afShim, EXPECTED_AF_SHIM_SIZE,
                EXPECTED_AF_SHIM_SHA256, "staged_a1_af_shim");
            if (!ARM_VALUE.equals(readFirstLine(arm))) {
                throw new IllegalStateException("app_arm_round_trip_failed");
            }
            report.append("private_staging=verified\n");

            propertiesTouched = true;
            setRunnerProperty(TRIGGER, "0");
            setRunnerProperty(ARG1, RUNNER_PROGRAM);
            setRunnerProperty(ARG2, SUPERVISOR_PATH);
            setRunnerProperty(ARG3, "");
            setRunnerProperty(ARG4, "");
            setRunnerProperty(ARG5, "");
            if (!"0".equals(getProperty(TRIGGER))
                    || !RUNNER_PROGRAM.equals(getProperty(ARG1))
                    || !SUPERVISOR_PATH.equals(getProperty(ARG2))
                    || !getProperty(ARG3).isEmpty()
                    || !getProperty(ARG4).isEmpty()
                    || !getProperty(ARG5).isEmpty()) {
                throw new IllegalStateException("runner_arguments_did_not_round_trip");
            }

            // Persist the one-install/one-shot lock before the only trigger.
            // Any ambiguous delivery therefore cannot be retried accidentally.
            writePrivateFile(spent,
                (SPENT_VALUE + "\n").getBytes(StandardCharsets.US_ASCII));
            if (!SPENT_VALUE.equals(readFirstLine(spent))) {
                throw new IllegalStateException("spent_marker_round_trip_failed");
            }

            report.append("trigger_attempt=once\n");
            triggerAttempted = true;
            setRunnerProperty(TRIGGER, "8");

            long deadline = SystemClock.elapsedRealtime() + POLL_TIMEOUT_MS;
            String resultText = "";
            while (SystemClock.elapsedRealtime() < deadline) {
                if (result.length() > 0L) {
                    resultText = readAscii(result);
                    if (hasCompleteMarker(resultText)) {
                        completed = true;
                        break;
                    }
                }
                SystemClock.sleep(POLL_INTERVAL_MS);
            }

            if (!resultText.isEmpty()) {
                report.append("supervisor_result_begin\n");
                report.append(resultText);
                if (resultText.charAt(resultText.length() - 1) != '\n') {
                    report.append('\n');
                }
                report.append("supervisor_result_end\n");
            }

            if (!completed) {
                report.append("result=UNKNOWN\n");
                report.append("reason=supervisor_result_timeout_or_reboot_in_progress\n");
                report.append("action=do_not_retry_use_normal_reboot_if_device_stays_up\n");
            } else if (validPassResult(resultText)) {
                report.append("result=PASS_REBOOT_EXPECTED\n");
                report.append("artifact=one_new_LRI_retained_in_DCIM_camera\n");
            } else if (validPreflightFailure(resultText)) {
                report.append("result=CHILD_PREFLIGHT_REFUSED_NO_REBOOT\n");
                report.append("action=inspect_child_result_over_ADB_before_any_retry\n");
            } else {
                report.append("result=FAIL_REBOOT_EXPECTED\n");
                report.append("reason=supervisor_reported_failure_or_inconsistent_result\n");
            }
        } catch (Throwable error) {
            report.append("result=ERROR\nexception=").append(safeError(error)).append('\n');
            if (triggerAttempted) {
                report.append("action=do_not_retry_use_normal_reboot_if_device_stays_up\n");
            }
        } finally {
            if (propertiesTouched) {
                try {
                    if (triggerAttempted && !completed) {
                        SystemClock.sleep(2000L);
                    }
                    clearRunnerProperties();
                } catch (Throwable cleanupError) {
                    report.append("runner_cleanup_exception=")
                        .append(safeError(cleanupError)).append('\n');
                }
            }
            try {
                String serviceState;
                boolean neutral;
                if (triggerAttempted) {
                    serviceState = waitForRunnerStoppedAndNeutral();
                    neutral = EXPECTED_FIHOP_STATE.equals(serviceState)
                        && runnerNeutral();
                } else {
                    serviceState = getProperty("init.svc.fihop");
                    neutral = runnerIdleBeforeTrigger(serviceState) && runnerNeutral();
                }
                report.append("fihop_final=").append(serviceState).append('\n');
                report.append("runner_final=")
                    .append(neutral ? "NEUTRAL" : "CHECK_REQUIRED").append('\n');
            } catch (Throwable cleanupError) {
                report.append("runner_final=CHECK_REQUIRED\n");
            }

            if (!triggerAttempted) {
                deleteQuietly(privateFile("a"));
                deleteQuietly(privateFile("s.sh"));
                deleteQuietly(privateFile("c.sh"));
                deleteQuietly(privateFile("f.so"));
                deleteQuietly(privateFile("r.txt"));
            }
            report.append("installation_spent=")
                .append(privateFile(SPENT_NAME).exists() ? "yes" : "no")
                .append('\n');
        }
        return report.toString();
    }

    private void inspectTargetAndAssets(StringBuilder report, boolean requireNoStaging)
            throws Exception {
        report.append("app_uid=").append(Process.myUid()).append('\n');
        if (Process.myUid() == 0) {
            throw new IllegalStateException("app_unexpectedly_root");
        }

        String privateDirectory = getFilesDir().getAbsolutePath();
        if (!PRIVATE_DIR.equals(privateDirectory)
                && !USER_ZERO_PRIVATE_DIR.equals(privateDirectory)) {
            throw new IllegalStateException("unexpected_private_directory");
        }
        if (privateFile(SPENT_NAME).exists()) {
            throw new IllegalStateException("installation_already_spent");
        }
        if (requireNoStaging && (privateFile("s.sh").exists()
                || privateFile("c.sh").exists()
                || privateFile("f.so").exists()
                || privateFile("r.txt").exists()
                || privateFile("a").exists())) {
            throw new IllegalStateException("stale_private_capture_state");
        }

        String build = getProperty("ro.build.version.incremental");
        String buildType = getProperty("ro.build.type");
        String debuggable = getProperty("ro.debuggable");
        String model = getProperty("ro.product.model");
        String product = getProperty("ro.product.name");
        String kernel = System.getProperty("os.version", "");
        String selinuxEnforce = readFirstLine(new File(SELINUX_ENFORCE_PATH));
        String bootCompleted = getProperty("sys.boot_completed");
        String bootMode = getProperty("ro.bootmode");
        String serviceState = getProperty("init.svc.fihop");
        report.append("build=").append(build).append('\n');
        report.append("build_type=").append(buildType).append('\n');
        report.append("debuggable=").append(debuggable).append('\n');
        report.append("model=").append(model).append('\n');
        report.append("product=").append(product).append('\n');
        report.append("kernel=").append(kernel).append('\n');
        report.append("selinux_enforce=").append(selinuxEnforce).append('\n');
        report.append("boot_completed=").append(bootCompleted).append('\n');
        report.append("bootmode=").append(bootMode).append('\n');
        report.append("fihop_before=").append(serviceState).append('\n');

        if (!EXPECTED_BUILD.equals(build)
                || !EXPECTED_BUILD_TYPE.equals(buildType)
                || !EXPECTED_DEBUGGABLE.equals(debuggable)
                || !EXPECTED_MODEL.equals(model)
                || !EXPECTED_PRODUCT.equals(product)
                || !EXPECTED_KERNEL.equals(kernel)
                || !EXPECTED_SELINUX_ENFORCE.equals(selinuxEnforce)) {
            throw new IllegalStateException("unexpected_device_identity");
        }
        if (!"1".equals(bootCompleted) || !EXPECTED_BOOT_MODE.equals(bootMode)) {
            throw new IllegalStateException("unexpected_boot_state");
        }
        if (!runnerIdleBeforeTrigger(serviceState)) {
            throw new IllegalStateException("runner_service_not_idle");
        }
        if (!runnerNeutral()) {
            throw new IllegalStateException("runner_properties_not_neutral");
        }

        File vendorScript = new File(FIHOP_SCRIPT);
        String vendorDigest = sha256(vendorScript);
        report.append("fihop_script_size=").append(vendorScript.length()).append('\n');
        report.append("fihop_script_sha256=").append(vendorDigest).append('\n');
        if (vendorScript.length() != EXPECTED_FIHOP_SIZE
                || !EXPECTED_FIHOP_SHA256.equals(vendorDigest)) {
            throw new IllegalStateException("unexpected_fihop_script");
        }

        AssetInfo supervisorAsset = inspectAsset(SUPERVISOR_ASSET);
        AssetInfo childAsset = inspectAsset(CHILD_ASSET);
        AssetInfo afShimAsset = inspectAsset(AF_SHIM_ASSET);
        report.append("supervisor_asset_size=").append(supervisorAsset.size).append('\n');
        report.append("supervisor_asset_sha256=")
            .append(supervisorAsset.sha256).append('\n');
        report.append("child_asset_size=").append(childAsset.size).append('\n');
        report.append("child_asset_sha256=").append(childAsset.sha256).append('\n');
        report.append("a1_af_shim_asset_size=").append(afShimAsset.size).append('\n');
        report.append("a1_af_shim_asset_sha256=")
            .append(afShimAsset.sha256).append('\n');
        if (supervisorAsset.size != EXPECTED_SUPERVISOR_SIZE
                || !EXPECTED_SUPERVISOR_SHA256.equals(supervisorAsset.sha256)) {
            throw new IllegalStateException("unexpected_supervisor_asset");
        }
        if (childAsset.size != EXPECTED_CHILD_SIZE
                || !EXPECTED_CHILD_SHA256.equals(childAsset.sha256)) {
            throw new IllegalStateException("unexpected_child_asset");
        }
        if (afShimAsset.size != EXPECTED_AF_SHIM_SIZE
                || !EXPECTED_AF_SHIM_SHA256.equals(afShimAsset.sha256)) {
            throw new IllegalStateException("unexpected_a1_af_shim_asset");
        }
    }

    private File privateFile(String name) {
        return new File(getFilesDir(), name);
    }

    private AssetInfo inspectAsset(String name) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        InputStream stream = getAssets().open(name);
        long size = 0L;
        try {
            byte[] buffer = new byte[4096];
            int count;
            while ((count = stream.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
                size += count;
            }
        } finally {
            stream.close();
        }
        return new AssetInfo(size, hex(digest.digest()));
    }

    private void copyAssetToPrivateFile(String asset, File file) throws Exception {
        InputStream input = getAssets().open(asset);
        FileOutputStream outputStream = new FileOutputStream(file, false);
        try {
            byte[] buffer = new byte[4096];
            int count;
            while ((count = input.read(buffer)) != -1) {
                outputStream.write(buffer, 0, count);
            }
            outputStream.getFD().sync();
        } finally {
            try {
                input.close();
            } finally {
                outputStream.close();
            }
        }
        restrictPrivateFile(file);
    }

    private static void verifyFile(File file, long size, String digest, String label)
            throws Exception {
        if (file.length() != size || !digest.equals(sha256(file))) {
            throw new IllegalStateException(label + "_digest_or_size_mismatch");
        }
    }

    private static void writePrivateFile(File file, byte[] contents) throws Exception {
        FileOutputStream stream = new FileOutputStream(file, false);
        try {
            stream.write(contents);
            stream.getFD().sync();
        } finally {
            stream.close();
        }
        restrictPrivateFile(file);
    }

    private static void restrictPrivateFile(File file) {
        if (!file.setReadable(false, false)
                || !file.setWritable(false, false)
                || !file.setExecutable(false, false)
                || !file.setReadable(true, true)
                || !file.setWritable(true, true)) {
            throw new IllegalStateException("cannot_restrict_private_file_mode");
        }
    }

    private static boolean runnerIdleBeforeTrigger(String serviceState) {
        return serviceState.isEmpty() || EXPECTED_FIHOP_STATE.equals(serviceState);
    }

    private static boolean runnerNeutral() throws Exception {
        if (!"0".equals(getProperty(TRIGGER))) {
            return false;
        }
        for (int index = 1; index < RUNNER_PROPERTIES.length; index++) {
            if (!getProperty(RUNNER_PROPERTIES[index]).isEmpty()) {
                return false;
            }
        }
        return true;
    }

    private static void clearRunnerProperties() throws Exception {
        setRunnerProperty(TRIGGER, "0");
        setRunnerProperty(ARG1, "");
        setRunnerProperty(ARG2, "");
        setRunnerProperty(ARG3, "");
        setRunnerProperty(ARG4, "");
        setRunnerProperty(ARG5, "");
    }

    private static String waitForRunnerStoppedAndNeutral() throws Exception {
        long deadline = SystemClock.elapsedRealtime() + SETTLE_TIMEOUT_MS;
        String serviceState;
        do {
            serviceState = getProperty("init.svc.fihop");
            if (EXPECTED_FIHOP_STATE.equals(serviceState) && runnerNeutral()) {
                return serviceState;
            }
            SystemClock.sleep(POLL_INTERVAL_MS);
        } while (SystemClock.elapsedRealtime() < deadline);
        return serviceState;
    }

    private static String getProperty(String key) throws Exception {
        Method get = Class.forName("android.os.SystemProperties")
            .getMethod("get", String.class, String.class);
        return (String) invoke(get, null, key, "");
    }

    private static void setRunnerProperty(String key, String value) throws Exception {
        boolean allowed = false;
        for (String property : RUNNER_PROPERTIES) {
            if (property.equals(key)) {
                allowed = true;
                break;
            }
        }
        if (!allowed) {
            throw new SecurityException("refusing non-runner property write");
        }
        if (TRIGGER.equals(key) && !("0".equals(value) || "8".equals(value))) {
            throw new SecurityException("refusing unexpected runner trigger");
        }
        if (ARG1.equals(key) && !(value.isEmpty() || RUNNER_PROGRAM.equals(value))) {
            throw new SecurityException("refusing unexpected runner program");
        }
        if (ARG2.equals(key) && !(value.isEmpty() || SUPERVISOR_PATH.equals(value))) {
            throw new SecurityException("refusing unexpected runner payload");
        }
        if ((ARG3.equals(key) || ARG4.equals(key) || ARG5.equals(key))
                && !value.isEmpty()) {
            throw new SecurityException("refusing nonempty extra runner argument");
        }
        Method set = Class.forName("android.os.SystemProperties")
            .getMethod("set", String.class, String.class);
        invoke(set, null, key, value);
    }

    private static Object invoke(Method method, Object receiver, Object... args)
            throws Exception {
        try {
            return method.invoke(receiver, args);
        } catch (InvocationTargetException wrapped) {
            Throwable cause = wrapped.getCause();
            if (cause instanceof Exception) {
                throw (Exception) cause;
            }
            if (cause instanceof Error) {
                throw (Error) cause;
            }
            throw wrapped;
        }
    }

    private static boolean hasCompleteMarker(String text) {
        String value = field(text, "supervisor_complete");
        return "PASS".equals(value) || "FAIL".equals(value)
            || "PREFLIGHT_FAIL".equals(value);
    }

    private static boolean validPassResult(String text) {
        return "L16_HOSTLESS_A_GROUP_INLINE_AF_CAPTURE_V1".equals(
                field(text, "supervisor"))
            && "PASS".equals(field(text, "supervisor_complete"))
            && "yes".equals(field(text, "child_started"))
            && "PASS".equals(field(text, "child_final_status"))
            && "yes".equals(field(text, "capture_attempted"))
            && "yes".equals(field(text, "autofocus_attempted"))
            && "0".equals(field(text, "autofocus_exit_status"))
            && "camera3_af_state_focused_locked_inline_hal_session".equals(
                field(text, "autofocus_response"))
            && "verified".equals(field(text, "a1_af_shim"))
            && "normal_reboot_after_hostless_capture_success".equals(
                field(text, "supervisor_decision"))
            && "1".equals(field(text, "lri_output_count"))
            && validLriPath(field(text, "lri_output_path"))
            && validDecimalAtLeast(field(text, "lri_output_size"), 32L)
            && field(text, "lri_output_sha1").matches("[0-9a-f]{40}");
    }

    private static boolean validPreflightFailure(String text) {
        return "L16_HOSTLESS_A_GROUP_INLINE_AF_CAPTURE_V1".equals(
                field(text, "supervisor"))
            && "PREFLIGHT_FAIL".equals(field(text, "supervisor_complete"))
            && "yes".equals(field(text, "child_started"))
            && "FAIL".equals(field(text, "child_final_status"))
            && "no".equals(field(text, "capture_attempted"))
            && "no".equals(field(text, "child_normal_reboot_required"))
            && "no_reboot_after_proven_preflight_failure".equals(
                field(text, "supervisor_decision"));
    }

    private static boolean validLriPath(String path) {
        return path.matches(
            "/sdcard/DCIM/camera/RDI_[0-9]{8}_[0-9]{6}_[0-9]{3}\\.lri"
        );
    }

    private static boolean validDecimalAtLeast(String value, long minimum) {
        if (!value.matches("[0-9]+")) {
            return false;
        }
        try {
            return Long.parseLong(value) >= minimum;
        } catch (NumberFormatException ignored) {
            return false;
        }
    }

    private static String field(String text, String key) {
        String prefix = key + "=";
        String found = "";
        boolean seen = false;
        for (String line : text.split("\\n", -1)) {
            if (line.startsWith(prefix)) {
                if (seen) {
                    return "";
                }
                seen = true;
                found = line.substring(prefix.length());
            }
        }
        return found;
    }

    private static String readAscii(File file) throws Exception {
        if (file.length() > MAX_RESULT_SIZE) {
            throw new IllegalStateException("result_too_large");
        }
        BufferedReader reader = new BufferedReader(new InputStreamReader(
            new FileInputStream(file), StandardCharsets.US_ASCII));
        StringBuilder value = new StringBuilder();
        try {
            String line;
            while ((line = reader.readLine()) != null) {
                value.append(line).append('\n');
            }
        } finally {
            reader.close();
        }
        return value.toString();
    }

    private static String readFirstLine(File file) throws Exception {
        BufferedReader reader = new BufferedReader(new InputStreamReader(
            new FileInputStream(file), StandardCharsets.US_ASCII));
        try {
            String line = reader.readLine();
            return line == null ? "" : line;
        } finally {
            reader.close();
        }
    }

    private static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        FileInputStream stream = new FileInputStream(file);
        try {
            byte[] buffer = new byte[4096];
            int count;
            while ((count = stream.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        } finally {
            stream.close();
        }
        return hex(digest.digest());
    }

    private static String hex(byte[] bytes) {
        StringBuilder value = new StringBuilder(bytes.length * 2);
        for (byte item : bytes) {
            value.append(String.format(Locale.US, "%02x", item & 0xff));
        }
        return value.toString();
    }

    private static void deleteQuietly(File file) {
        try {
            if (file.exists()) {
                file.delete();
            }
        } catch (Throwable ignored) {
            // A later preflight refuses any retained staging file.
        }
    }

    private static String safeError(Throwable error) {
        String message = error.getMessage();
        if (message == null || message.isEmpty()) {
            message = "<none>";
        }
        return error.getClass().getName() + ":"
            + message.replace('\n', ' ').replace('\r', ' ');
    }
}
