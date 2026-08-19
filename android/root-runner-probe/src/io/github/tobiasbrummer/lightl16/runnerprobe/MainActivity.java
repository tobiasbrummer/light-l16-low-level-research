package io.github.tobiasbrummer.lightl16.runnerprobe;

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
import java.io.InputStreamReader;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

/**
 * One-purpose, owner-controlled test of the LightOS fihop root runner.
 *
 * There is no command input: the only allowed program, argument, payload,
 * result format, and property sequence are compile-time constants.
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

    // The short, fixed private path stays within Android's legacy property
    // value limit on the examined build.
    private static final String PRIVATE_DIR =
        "/data/data/io.github.tobiasbrummer.lightl16.runnerprobe/files";
    private static final String USER_ZERO_PRIVATE_DIR =
        "/data/user/0/io.github.tobiasbrummer.lightl16.runnerprobe/files";
    private static final String PAYLOAD_PATH = PRIVATE_DIR + "/p.sh";
    private static final String RESULT_PATH = PRIVATE_DIR + "/r.txt";
    private static final String ARM_PATH = PRIVATE_DIR + "/a";
    private static final String RUNNER_PROGRAM = "/system/bin/sh";
    private static final String ARM_VALUE = "L16_APP_ROOT_PROBE_ONCE_V1";
    private static final String COMPLETE_MARKER = "probe_complete=L16_APP_ROOT_PROBE_V1";
    private static final String EXPECTED_IDENTITY_BASE =
        "uid=0(root) gid=0(root) groups=0(root)";
    private static final String EXPECTED_CONTEXT = "u:r:qti_init_shell:s0";
    private static final long POLL_TIMEOUT_MS = 5000L;
    private static final long POLL_INTERVAL_MS = 100L;
    private static final long SETTLE_TIMEOUT_MS = 3000L;
    private static final String SELINUX_ENFORCE_PATH = "/sys/fs/selinux/enforce";

    private static final String PAYLOAD =
        "#!/system/bin/sh\n"
            + "OUT=" + RESULT_PATH + "\n"
            + "ARM=" + ARM_PATH + "\n"
            + "TOKEN=" + ARM_VALUE + "\n"
            + "clear_runner() {\n"
            + "  setprop persist.sys.fihop 0\n"
            + "  setprop persist.sys.fihop1 \"\"\n"
            + "  setprop persist.sys.fihop2 \"\"\n"
            + "  setprop persist.sys.fihop3 \"\"\n"
            + "  setprop persist.sys.fihop4 \"\"\n"
            + "  setprop persist.sys.fihop5 \"\"\n"
            + "}\n"
            + "fail() {\n"
            + "  clear_runner\n"
            + "  rm -f \"$ARM\"\n"
            + "  printf 'probe_error=%s\\n' \"$1\" > \"$OUT\"\n"
            + "  exit 1\n"
            + "}\n"
            + "[ -f \"$ARM\" ] || fail arm_missing\n"
            + "[ \"$(cat \"$ARM\" 2>/dev/null)\" = \"$TOKEN\" ] || fail arm_mismatch\n"
            + "rm -f \"$ARM\" || fail arm_remove_failed\n"
            + "clear_runner\n"
            + "{\n"
            + "  id\n"
            + "  printf 'context='\n"
            + "  cat /proc/self/attr/current\n"
            + "  printf 'bootmode=%s\\n' \"$(getprop ro.bootmode)\"\n"
            + "  printf '" + COMPLETE_MARKER + "\\n'\n"
            + "} > \"$OUT\" || exit 1\n";

    private TextView output;
    private Button runButton;
    private boolean running;
    private boolean attempted;

    private static final class ProbeRefusedException extends Exception {
        private static final long serialVersionUID = 1L;
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
            "Einmaliger, begrenzter App→Root-Test für die Light L16.\n\n"
                + "Die App prüft Firmware, Vendor-Skript und neutralen Runner, "
                + "startet dann ausschließlich ein fest eingebautes Diagnose-Skript. "
                + "Dieses leert den Runner vor dem Auslesen von UID und Kontext. "
                + "Kamera, Treiber und Partitionen werden nicht angesprochen."
        );
        body.addView(explanation);

        runButton = new Button(this);
        runButton.setText("APP → ROOT EINMAL TESTEN");
        runButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View ignored) {
                startProbe();
            }
        });
        body.addView(runButton);

        output = new TextView(this);
        output.setTextIsSelectable(true);
        output.setMovementMethod(new ScrollingMovementMethod());
        output.setText("Noch nicht ausgeführt.\n");
        body.addView(output);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(body);
        setContentView(scroll);
    }

    private int dp(int value) {
        float density = getResources().getDisplayMetrics().density;
        return (int) (value * density + 0.5f);
    }

    private void startProbe() {
        if (running || attempted) {
            return;
        }
        running = true;
        attempted = true;
        runButton.setEnabled(false);
        output.setText("Preflight läuft …\n");

        new Thread(new Runnable() {
            @Override
            public void run() {
                final String report = runProbe();
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        output.setText(report);
                        runButton.setText("TEST BEENDET");
                        running = false;
                    }
                });
            }
        }, "l16-root-runner-probe").start();
    }

    private String runProbe() {
        StringBuilder report = new StringBuilder();
        boolean armed = false;
        boolean triggerAttempted = false;
        boolean privateFilesTouched = false;
        boolean targetConfirmed = false;
        boolean runnerFinalNeutral = false;

        try {
            report.append("app_uid=").append(Process.myUid()).append('\n');
            if (Process.myUid() == 0) {
                throw refused(report, "app_unexpectedly_root");
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
                throw refused(report, "unexpected_device_identity");
            }
            if (!"1".equals(bootCompleted) || !EXPECTED_BOOT_MODE.equals(bootMode)) {
                throw refused(report, "unexpected_boot_state");
            }
            if (!runnerIdleBeforeTrigger(serviceState)) {
                throw refused(report, "runner_service_not_idle");
            }
            targetConfirmed = true;
            if (!runnerNeutral()) {
                throw refused(report, "runner_properties_not_neutral");
            }

            File vendorScript = new File(FIHOP_SCRIPT);
            report.append("fihop_script_size=").append(vendorScript.length()).append('\n');
            String vendorDigest = sha256(vendorScript);
            report.append("fihop_script_sha256=").append(vendorDigest).append('\n');
            if (vendorScript.length() != EXPECTED_FIHOP_SIZE
                    || !EXPECTED_FIHOP_SHA256.equals(vendorDigest)) {
                throw refused(report, "unexpected_fihop_script");
            }

            File filesDir = getFilesDir();
            String privateDirectory = filesDir.getAbsolutePath();
            if (!PRIVATE_DIR.equals(privateDirectory)
                    && !USER_ZERO_PRIVATE_DIR.equals(privateDirectory)) {
                throw refused(report, "unexpected_private_directory");
            }
            File payload = new File(PAYLOAD_PATH);
            File result = new File(RESULT_PATH);
            File arm = new File(ARM_PATH);
            if (payload.exists() || result.exists() || arm.exists()) {
                throw refused(report, "stale_private_probe_file");
            }

            byte[] payloadBytes = PAYLOAD.getBytes(StandardCharsets.US_ASCII);
            privateFilesTouched = true;
            writePrivateFile(payload, payloadBytes);
            String expectedPayloadDigest = sha256(payloadBytes);
            String actualPayloadDigest = sha256(payload);
            report.append("payload_sha256=").append(actualPayloadDigest).append('\n');
            if (!expectedPayloadDigest.equals(actualPayloadDigest)) {
                deleteQuietly(payload);
                throw refused(report, "payload_digest_mismatch");
            }

            writePrivateFile(arm, (ARM_VALUE + "\n").getBytes(StandardCharsets.US_ASCII));
            armed = true;
            writePrivateFile(result, new byte[0]);

            setRunnerProperty(TRIGGER, "0");
            setRunnerProperty(ARG1, RUNNER_PROGRAM);
            setRunnerProperty(ARG2, PAYLOAD_PATH);
            setRunnerProperty(ARG3, "");
            setRunnerProperty(ARG4, "");
            setRunnerProperty(ARG5, "");
            if (!"0".equals(getProperty(TRIGGER))
                    || !RUNNER_PROGRAM.equals(getProperty(ARG1))
                    || !PAYLOAD_PATH.equals(getProperty(ARG2))
                    || !getProperty(ARG3).isEmpty()
                    || !getProperty(ARG4).isEmpty()
                    || !getProperty(ARG5).isEmpty()) {
                clearRunnerProperties();
                deleteQuietly(arm);
                deleteQuietly(payload);
                throw refused(report, "runner_arguments_did_not_round_trip");
            }

            report.append("trigger_attempt=once\n");
            triggerAttempted = true;
            setRunnerProperty(TRIGGER, "8");

            long deadline = SystemClock.elapsedRealtime() + POLL_TIMEOUT_MS;
            String resultText = "";
            while (SystemClock.elapsedRealtime() < deadline) {
                if (result.length() > 0L) {
                    resultText = readAscii(result);
                    if (validPayloadResult(resultText)
                            || !firstLineWithPrefix(resultText, "probe_error=").isEmpty()) {
                        break;
                    }
                }
                SystemClock.sleep(POLL_INTERVAL_MS);
            }
            if (!resultText.isEmpty()) {
                report.append("payload_result_begin\n");
                report.append(resultText);
                if (resultText.charAt(resultText.length() - 1) != '\n') {
                    report.append('\n');
                }
                report.append("payload_result_end\n");
            }

            String payloadError = firstLineWithPrefix(resultText, "probe_error=");
            if (!payloadError.isEmpty()) {
                report.append("result=FAIL\nreason=").append(payloadError).append('\n');
            } else if (!validPayloadResult(resultText)) {
                report.append("result=FAIL\nreason=missing_or_unexpected_payload_result\n");
            } else {
                report.append("result=PASS\n");
                report.append("identity=").append(firstLine(resultText)).append('\n');
            }
        } catch (ProbeRefusedException ignored) {
            // refused() already recorded the exact reason. Continue through
            // the common final-state reporting below.
        } catch (Throwable error) {
            report.append("result=ERROR\nexception=")
                .append(error.getClass().getName()).append(':')
                .append(safeMessage(error)).append('\n');
        } finally {
            if (armed || triggerAttempted) {
                try {
                    clearRunnerProperties();
                } catch (Throwable cleanupError) {
                    report.append("runner_cleanup_exception=")
                        .append(cleanupError.getClass().getName()).append(':')
                        .append(safeMessage(cleanupError)).append('\n');
                }
            }
            if (targetConfirmed) {
                try {
                    String serviceState;
                    if (triggerAttempted) {
                        serviceState = waitForRunnerStoppedAndNeutral();
                        runnerFinalNeutral = EXPECTED_FIHOP_STATE.equals(serviceState)
                            && runnerNeutral();
                    } else {
                        serviceState = getProperty("init.svc.fihop");
                        runnerFinalNeutral = runnerIdleBeforeTrigger(serviceState)
                            && runnerNeutral();
                    }
                    report.append("fihop_final=").append(serviceState).append('\n');
                    report.append("runner_final=")
                        .append(runnerFinalNeutral ? "NEUTRAL" : "CHECK_REQUIRED")
                        .append('\n');
                } catch (Throwable cleanupError) {
                    report.append("runner_final=CHECK_REQUIRED\n");
                }
            } else {
                report.append("runner_final=NOT_TOUCHED\n");
            }
            if (privateFilesTouched || armed || triggerAttempted) {
                // If delivery was ambiguous, retain the fixed self-clearing
                // payload until the one-shot service is definitely stopped.
                if (!triggerAttempted || runnerFinalNeutral) {
                    deleteQuietly(new File(ARM_PATH));
                    deleteQuietly(new File(PAYLOAD_PATH));
                    deleteQuietly(new File(RESULT_PATH));
                }
                boolean filesClean = !new File(ARM_PATH).exists()
                    && !new File(PAYLOAD_PATH).exists()
                    && !new File(RESULT_PATH).exists();
                report.append("files_final=")
                    .append(filesClean ? "CLEAN" : "PRESERVED_CHECK_REQUIRED")
                    .append('\n');
            } else {
                report.append("files_final=NOT_TOUCHED\n");
            }
        }
        return report.toString();
    }

    private static ProbeRefusedException refused(
            StringBuilder report, String reason) {
        report.append("result=REFUSED\nreason=").append(reason).append('\n');
        return new ProbeRefusedException();
    }

    private static boolean runnerIdleBeforeTrigger(String serviceState) {
        // A disabled one-shot service may not have an init.svc.* property at
        // all until its first transition. Once it has run, "stopped" is the
        // only accepted idle state.
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
        if (ARG2.equals(key) && !(value.isEmpty() || PAYLOAD_PATH.equals(value))) {
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

    private static void writePrivateFile(File file, byte[] contents) throws Exception {
        FileOutputStream stream = new FileOutputStream(file, false);
        try {
            stream.write(contents);
            stream.getFD().sync();
        } finally {
            stream.close();
        }
        if (!file.setReadable(false, false)
                || !file.setWritable(false, false)
                || !file.setExecutable(false, false)
                || !file.setReadable(true, true)
                || !file.setWritable(true, true)) {
            throw new IllegalStateException("cannot restrict private file mode");
        }
    }

    private static String readAscii(File file) throws Exception {
        if (file.length() > 2048L) {
            throw new IllegalStateException("result too large");
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

    private static String sha256(byte[] contents) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        return hex(digest.digest(contents));
    }

    private static String hex(byte[] bytes) {
        StringBuilder value = new StringBuilder(bytes.length * 2);
        for (byte item : bytes) {
            value.append(String.format(Locale.US, "%02x", item & 0xff));
        }
        return value.toString();
    }

    private static String firstLineWithPrefix(String text, String prefix) {
        for (String line : text.split("\\n")) {
            if (line.startsWith(prefix)) {
                return line;
            }
        }
        return "";
    }

    private static String firstLine(String text) {
        int newline = text.indexOf('\n');
        return newline == -1 ? text : text.substring(0, newline);
    }

    private static boolean validPayloadResult(String text) {
        String[] lines = text.split("\\n", -1);
        if (lines.length != 5 || !lines[4].isEmpty()) {
            return false;
        }
        String identity = lines[0];
        if (!(EXPECTED_IDENTITY_BASE.equals(identity)
                || (EXPECTED_IDENTITY_BASE + " context=" + EXPECTED_CONTEXT)
                    .equals(identity))) {
            return false;
        }
        return ("context=" + EXPECTED_CONTEXT).equals(lines[1])
            && ("bootmode=" + EXPECTED_BOOT_MODE).equals(lines[2])
            && COMPLETE_MARKER.equals(lines[3]);
    }

    private static void deleteQuietly(File file) {
        try {
            if (file.exists()) {
                file.delete();
            }
        } catch (Throwable ignored) {
            // The final file-state check makes a failed deletion visible.
        }
    }

    private static String safeMessage(Throwable error) {
        String message = error.getMessage();
        if (message == null || message.isEmpty()) {
            return "<none>";
        }
        return message.replace('\n', ' ').replace('\r', ' ');
    }
}
