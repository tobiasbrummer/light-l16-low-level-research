package io.github.tobiasbrummer.lightl16.propertyprobe;

import android.app.Activity;
import android.os.Bundle;
import android.os.Process;
import android.text.method.ScrollingMovementMethod;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

/**
 * One-purpose permission probe for an owner-controlled Light L16.
 *
 * This activity never writes the fihop trigger.  It reads the trigger and the
 * other argument slots as safety preconditions, then attempts one
 * set/read/clear round trip on argument slot 5 only.  It has no Android
 * permissions and contains no camera, root-shell, network, or storage code.
 */
public final class MainActivity extends Activity {
    private static final String TRIGGER_PROPERTY = "persist.sys.fihop";
    private static final String[] OTHER_ARGUMENT_PROPERTIES = {
        "persist.sys.fihop1",
        "persist.sys.fihop2",
        "persist.sys.fihop3",
        "persist.sys.fihop4"
    };
    private static final String PROBE_PROPERTY = "persist.sys.fihop5";
    private static final String MARKER_PREFIX = "L16_LOCAL_PROPERTY_PROBE_";
    private static final String RUN_EXTRA = "run_property_probe";

    private TextView output;
    private Button runButton;
    private boolean running;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        int padding = dp(20);
        body.setPadding(padding, padding, padding, padding);

        TextView explanation = new TextView(this);
        explanation.setText(
            "Harmloser Berechtigungstest für die Light L16.\n\n"
                + "Der Test liest zuerst den fihop-Zustand. Nur wenn der Trigger 0 "
                + "und alle fünf Argumente leer sind, wird ausschließlich Slot 5 "
                + "kurz gesetzt, zurückgelesen und sofort wieder geleert. Es wird "
                + "kein Root-Dienst gestartet und keine Kamera angesprochen."
        );
        body.addView(explanation);

        runButton = new Button(this);
        runButton.setText("SET / GET / CLEAR TESTEN");
        runButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View ignored) {
                runProbe();
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

        if (getIntent() != null
                && getIntent().getBooleanExtra(RUN_EXTRA, false)) {
            runButton.post(new Runnable() {
                @Override
                public void run() {
                    runProbe();
                }
            });
        }
    }

    private int dp(int value) {
        float density = getResources().getDisplayMetrics().density;
        return (int) (value * density + 0.5f);
    }

    private void runProbe() {
        if (running) {
            return;
        }
        running = true;
        runButton.setEnabled(false);
        StringBuilder report = new StringBuilder();
        String marker = MARKER_PREFIX + Process.myPid();
        boolean markerObserved = false;

        try {
            String trigger = getProperty(TRIGGER_PROPERTY);
            report.append("trigger_before=").append(quoted(trigger)).append('\n');
            if (!"0".equals(trigger)) {
                report.append("result=REFUSED\nreason=trigger_not_exactly_zero\n");
                return;
            }

            for (String key : OTHER_ARGUMENT_PROPERTIES) {
                String value = getProperty(key);
                report.append(key).append("_before=").append(quoted(value)).append('\n');
                if (!value.isEmpty()) {
                    report.append("result=REFUSED\nreason=other_argument_not_empty\n");
                    return;
                }
            }

            String before = getProperty(PROBE_PROPERTY);
            report.append("probe_before=").append(quoted(before)).append('\n');
            if (!before.isEmpty()) {
                report.append("result=REFUSED\nreason=probe_argument_not_empty\n");
                return;
            }

            report.append("write_attempt=slot_5_only\n");
            setProperty(PROBE_PROPERTY, marker);
            String observed = getProperty(PROBE_PROPERTY);
            report.append("probe_after_set=").append(quoted(observed)).append('\n');
            markerObserved = marker.equals(observed);
            if (!markerObserved) {
                report.append("result=DENIED_OR_NOT_STORED\n");
                return;
            }

            setProperty(PROBE_PROPERTY, "");
            markerObserved = false;
            String afterClear = getProperty(PROBE_PROPERTY);
            report.append("probe_after_clear=").append(quoted(afterClear)).append('\n');
            if (!afterClear.isEmpty()) {
                report.append("result=FAIL\nreason=slot_5_not_empty_after_clear\n");
                return;
            }

            report.append("result=PASS\n");
            report.append("meaning=ordinary_app_can_write_required_system_property_class\n");
        } catch (Throwable error) {
            report.append("exception=")
                .append(error.getClass().getName())
                .append(':')
                .append(safeMessage(error))
                .append('\n');
            report.append("result=DENIED_OR_ERROR\n");
        } finally {
            // Never overwrite an unknown concurrent value.  Clear only our
            // exact marker if it is still present after an exception.
            try {
                String current = getProperty(PROBE_PROPERTY);
                if (markerObserved || marker.equals(current)) {
                    setProperty(PROBE_PROPERTY, "");
                }
                String finalValue = getProperty(PROBE_PROPERTY);
                report.append("probe_final=").append(quoted(finalValue)).append('\n');
                report.append("cleanup=")
                    .append(finalValue.isEmpty() ? "CLEAN" : "CHECK_REQUIRED")
                    .append('\n');
            } catch (Throwable cleanupError) {
                report.append("cleanup_exception=")
                    .append(cleanupError.getClass().getName())
                    .append(':')
                    .append(safeMessage(cleanupError))
                    .append('\n');
                report.append("cleanup=CHECK_REQUIRED\n");
            }
            output.setText(report.toString());
            runButton.setEnabled(true);
            running = false;
        }
    }

    private static String getProperty(String key) throws Exception {
        Method get = Class.forName("android.os.SystemProperties")
            .getMethod("get", String.class, String.class);
        return (String) invoke(get, null, key, "");
    }

    private static void setProperty(String key, String value) throws Exception {
        if (!PROBE_PROPERTY.equals(key)) {
            throw new SecurityException("refusing non-probe property write");
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

    private static String quoted(String value) {
        return value.isEmpty() ? "<empty>" : value;
    }

    private static String safeMessage(Throwable error) {
        String message = error.getMessage();
        if (message == null || message.isEmpty()) {
            return "<none>";
        }
        return message.replace('\n', ' ').replace('\r', ' ');
    }
}
