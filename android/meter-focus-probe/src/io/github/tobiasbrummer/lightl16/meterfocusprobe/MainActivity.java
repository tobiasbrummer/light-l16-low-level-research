package io.github.tobiasbrummer.lightl16.meterfocusprobe;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.pm.PackageManager;
import android.graphics.Rect;
import android.graphics.SurfaceTexture;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.CaptureResult;
import android.hardware.camera2.TotalCaptureResult;
import android.hardware.camera2.params.MeteringRectangle;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.util.Size;
import android.view.Surface;
import android.view.TextureView;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.Arrays;
import java.util.Collections;
import java.util.Locale;

public final class MainActivity extends Activity {
    private static final int CAMERA_PERMISSION_REQUEST = 41;
    private static final long OPEN_TIMEOUT_MS = 8000L;
    private static final long AE_TIMEOUT_MS = 5000L;
    private static final long AF_TIMEOUT_MS = 8000L;

    private TextureView preview;
    private TextView output;
    private Button probeButton;
    private HandlerThread cameraThread;
    private Handler cameraHandler;
    private CameraDevice cameraDevice;
    private CameraCaptureSession captureSession;
    private CaptureRequest.Builder previewBuilder;
    private Surface previewSurface;
    private boolean running;
    private boolean meteringDone;
    private boolean meteringPassed;
    private boolean focusStarted;
    private long phaseDeadline;
    private String selectedCameraId = "";
    private long measuredExposureNs = -1L;
    private int measuredSensitivity = -1;
    private int lastAeState = -1;
    private int lastAfState = -1;
    private Rect activeArray;
    private float selectedFocalLength;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        int padding = dp(16);
        body.setPadding(padding, padding, padding, padding);

        TextView explanation = new TextView(this);
        explanation.setText(
            "Nur-lesender Camera2-Test: Preview öffnen, Mitte messen, danach "
                + "Autofokus auslösen und die HAL wieder vollständig schließen. "
                + "Kein Root, kein lcc, keine Aufnahme und kein Neustart."
        );
        body.addView(explanation);

        preview = new TextureView(this);
        body.addView(preview, new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, dp(280)));

        probeButton = new Button(this);
        probeButton.setText("METERING + FOKUS EINMAL TESTEN");
        probeButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View ignored) { startProbeWithPermission(); }
        });
        body.addView(probeButton);

        output = new TextView(this);
        output.setTextIsSelectable(true);
        output.setText("probe=NOT_STARTED\n");
        body.addView(output);
        setContentView(body);
    }

    @Override
    protected void onPause() {
        if (running) {
            finishProbe("ABORTED", "activity_paused");
        } else {
            closeCameraResources();
        }
        super.onPause();
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private void startProbeWithPermission() {
        if (running) return;
        if (checkSelfPermission(Manifest.permission.CAMERA)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] {Manifest.permission.CAMERA},
                CAMERA_PERMISSION_REQUEST);
            return;
        }
        startProbe();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions,
            int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == CAMERA_PERMISSION_REQUEST && grantResults.length == 1
                && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            startProbe();
        } else if (requestCode == CAMERA_PERMISSION_REQUEST) {
            output.setText("probe=REFUSED\nreason=camera_permission_denied\n");
        }
    }

    private void startProbe() {
        if (!preview.isAvailable()) {
            output.setText("probe=REFUSED\nreason=preview_surface_not_ready\n");
            return;
        }
        running = true;
        meteringDone = false;
        meteringPassed = false;
        focusStarted = false;
        measuredExposureNs = -1L;
        measuredSensitivity = -1;
        lastAeState = -1;
        lastAfState = -1;
        probeButton.setEnabled(false);
        output.setText("probe=RUNNING\nphase=opening_camera\n");
        cameraThread = new HandlerThread("l16-meter-focus-camera");
        cameraThread.start();
        cameraHandler = new Handler(cameraThread.getLooper());
        phaseDeadline = SystemClock.elapsedRealtime() + OPEN_TIMEOUT_MS;
        cameraHandler.postDelayed(new Runnable() {
            @Override public void run() {
                if (running && cameraDevice == null) {
                    finishProbe("FAIL", "camera_open_timeout");
                }
            }
        }, OPEN_TIMEOUT_MS);

        try {
            CameraManager manager = (CameraManager) getSystemService(Context.CAMERA_SERVICE);
            selectedCameraId = chooseCamera(manager);
            CameraCharacteristics characteristics = manager.getCameraCharacteristics(
                selectedCameraId);
            activeArray = characteristics.get(
                CameraCharacteristics.SENSOR_INFO_ACTIVE_ARRAY_SIZE);
            float[] focalLengths = characteristics.get(
                CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS);
            if (focalLengths == null || focalLengths.length == 0) {
                throw new IllegalStateException("no_available_focal_length");
            }
            selectedFocalLength = focalLengths[0];
            for (float focalLength : focalLengths) {
                if (focalLength < selectedFocalLength) selectedFocalLength = focalLength;
            }
            Integer hardwareLevel = characteristics.get(
                CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL);
            append("camera_id=" + selectedCameraId);
            append("hardware_level=" + value(hardwareLevel));
            append("active_array=" + rectValue(activeArray));
            append("available_focal_lengths=" + Arrays.toString(focalLengths));
            append("selected_focal_length=" + selectedFocalLength);
            manager.openCamera(selectedCameraId, deviceCallback, cameraHandler);
        } catch (Throwable error) {
            finishProbe("FAIL", "open_exception_" + safe(error));
        }
    }

    private String chooseCamera(CameraManager manager) throws CameraAccessException {
        String[] ids = manager.getCameraIdList();
        append("camera_ids=" + Arrays.toString(ids));
        for (String id : ids) {
            CameraCharacteristics c = manager.getCameraCharacteristics(id);
            StreamConfigurationMap map = c.get(
                CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            if (map != null && map.getOutputSizes(SurfaceTexture.class) != null
                    && map.getOutputSizes(SurfaceTexture.class).length > 0) {
                return id;
            }
        }
        throw new IllegalStateException("no_texture_camera");
    }

    private final CameraDevice.StateCallback deviceCallback =
            new CameraDevice.StateCallback() {
        @Override public void onOpened(CameraDevice camera) {
            if (!running) { camera.close(); return; }
            cameraDevice = camera;
            createPreviewSession();
        }
        @Override public void onDisconnected(CameraDevice camera) {
            camera.close();
            finishProbe("FAIL", "camera_disconnected");
        }
        @Override public void onError(CameraDevice camera, int error) {
            camera.close();
            finishProbe("FAIL", "camera_error_" + error);
        }
    };

    private void createPreviewSession() {
        try {
            CameraManager manager = (CameraManager) getSystemService(Context.CAMERA_SERVICE);
            CameraCharacteristics c = manager.getCameraCharacteristics(selectedCameraId);
            StreamConfigurationMap map = c.get(
                CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            Size size = choosePreviewSize(map.getOutputSizes(SurfaceTexture.class));
            SurfaceTexture texture = preview.getSurfaceTexture();
            texture.setDefaultBufferSize(size.getWidth(), size.getHeight());
            previewSurface = new Surface(texture);
            previewBuilder = cameraDevice.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW);
            previewBuilder.addTarget(previewSurface);
            previewBuilder.set(CaptureRequest.CONTROL_MODE,
                CaptureRequest.CONTROL_MODE_AUTO);
            previewBuilder.set(CaptureRequest.CONTROL_AE_MODE,
                CaptureRequest.CONTROL_AE_MODE_ON);
            previewBuilder.set(CaptureRequest.CONTROL_AF_MODE,
                CaptureRequest.CONTROL_AF_MODE_AUTO);
            previewBuilder.set(CaptureRequest.LENS_FOCAL_LENGTH, selectedFocalLength);
            cameraDevice.createCaptureSession(Collections.singletonList(previewSurface),
                sessionCallback, cameraHandler);
            append("preview_size=" + size.getWidth() + "x" + size.getHeight());
        } catch (Throwable error) {
            finishProbe("FAIL", "preview_exception_" + safe(error));
        }
    }

    private static Size choosePreviewSize(Size[] sizes) {
        Size best = sizes[0];
        long bestArea = 0L;
        for (Size size : sizes) {
            long area = (long) size.getWidth() * size.getHeight();
            if (area <= 1920L * 1080L && area > bestArea) {
                best = size;
                bestArea = area;
            }
        }
        return best;
    }

    private final CameraCaptureSession.StateCallback sessionCallback =
            new CameraCaptureSession.StateCallback() {
        @Override public void onConfigured(CameraCaptureSession session) {
            if (!running) { session.close(); return; }
            captureSession = session;
            startMetering();
        }
        @Override public void onConfigureFailed(CameraCaptureSession session) {
            finishProbe("FAIL", "capture_session_configuration_failed");
        }
    };

    private void startMetering() {
        try {
            MeteringRectangle roi = centerRoi(activeArray);
            previewBuilder.set(CaptureRequest.CONTROL_AF_TRIGGER,
                CaptureRequest.CONTROL_AF_TRIGGER_IDLE);
            previewBuilder.set(CaptureRequest.CONTROL_AE_REGIONS,
                new MeteringRectangle[] {roi});
            previewBuilder.set(CaptureRequest.CONTROL_AF_REGIONS, null);
            phaseDeadline = SystemClock.elapsedRealtime() + AE_TIMEOUT_MS;
            append("metering_roi=" + roi.getRect().flattenToString());
            append("phase=metering");
            captureSession.setRepeatingRequest(previewBuilder.build(), resultCallback,
                cameraHandler);
        } catch (Throwable error) {
            finishProbe("FAIL", "metering_request_exception_" + safe(error));
        }
    }

    private static MeteringRectangle centerRoi(Rect active) {
        if (active == null || active.width() < 4 || active.height() < 4) {
            throw new IllegalStateException("invalid_active_array");
        }
        int width = active.width() / 2;
        int height = active.height() / 2;
        int left = active.left + (active.width() - width) / 2;
        int top = active.top + (active.height() - height) / 2;
        return new MeteringRectangle(new Rect(left, top, left + width, top + height),
            MeteringRectangle.METERING_WEIGHT_MAX);
    }

    private final CameraCaptureSession.CaptureCallback resultCallback =
            new CameraCaptureSession.CaptureCallback() {
        @Override public void onCaptureCompleted(CameraCaptureSession session,
                CaptureRequest request, TotalCaptureResult result) {
            if (!running) return;
            Long exposure = result.get(CaptureResult.SENSOR_EXPOSURE_TIME);
            Integer sensitivity = result.get(CaptureResult.SENSOR_SENSITIVITY);
            Integer ae = result.get(CaptureResult.CONTROL_AE_STATE);
            Integer af = result.get(CaptureResult.CONTROL_AF_STATE);
            if (exposure != null) measuredExposureNs = exposure;
            if (sensitivity != null) measuredSensitivity = sensitivity;
            if (ae != null) lastAeState = ae;
            if (af != null) lastAfState = af;

            long now = SystemClock.elapsedRealtime();
            if (!meteringDone) {
                boolean converged = ae != null && (ae == CaptureResult.CONTROL_AE_STATE_CONVERGED
                    || ae == CaptureResult.CONTROL_AE_STATE_LOCKED
                    || ae == CaptureResult.CONTROL_AE_STATE_FLASH_REQUIRED);
                if (converged || now >= phaseDeadline) {
                    meteringDone = true;
                    meteringPassed = converged && measuredExposureNs > 0;
                    append("metering=" + (meteringPassed ? "PASS" : "TIMEOUT"));
                    append("ae_state=" + lastAeState);
                    append("sensor_exposure_time_ns=" + measuredExposureNs);
                    append("sensor_sensitivity=" + measuredSensitivity);
                    startFocus();
                }
                return;
            }
            if (focusStarted) {
                if (af != null && af == CaptureResult.CONTROL_AF_STATE_FOCUSED_LOCKED) {
                    append("focus=PASS");
                    append("af_state=" + af);
                    finishProbe(meteringPassed ? "PASS" : "PARTIAL",
                        meteringPassed ? "metering_and_focus_completed"
                            : "focus_completed_metering_not_converged");
                } else if (af != null
                        && af == CaptureResult.CONTROL_AF_STATE_NOT_FOCUSED_LOCKED) {
                    append("focus=NOT_FOCUSED_LOCKED");
                    append("af_state=" + af);
                    finishProbe(meteringPassed ? "PASS" : "PARTIAL",
                        meteringPassed
                            ? "metering_completed_focus_transaction_completed"
                            : "focus_transaction_completed_metering_not_converged");
                } else if (now >= phaseDeadline) {
                    append("focus=TIMEOUT");
                    append("af_state=" + lastAfState);
                    finishProbe("FAIL", "focus_timeout");
                }
            }
        }
    };

    private void startFocus() {
        try {
            focusStarted = true;
            phaseDeadline = SystemClock.elapsedRealtime() + AF_TIMEOUT_MS;
            MeteringRectangle roi = centerRoi(activeArray);
            CaptureRequest.Builder focus = cameraDevice.createCaptureRequest(
                CameraDevice.TEMPLATE_PREVIEW);
            focus.addTarget(previewSurface);
            focus.set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO);
            focus.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON);
            focus.set(CaptureRequest.CONTROL_AE_REGIONS, null);
            focus.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_AUTO);
            focus.set(CaptureRequest.LENS_FOCAL_LENGTH, selectedFocalLength);
            focus.set(CaptureRequest.CONTROL_AF_REGIONS,
                new MeteringRectangle[] {roi});
            focus.set(CaptureRequest.CONTROL_AF_TRIGGER,
                CaptureRequest.CONTROL_AF_TRIGGER_START);
            append("focus_roi=" + roi.getRect().flattenToString());
            append("phase=focus");
            captureSession.capture(focus.build(), resultCallback, cameraHandler);
            cameraHandler.postDelayed(new Runnable() {
                @Override public void run() {
                    if (running && focusStarted
                            && SystemClock.elapsedRealtime() >= phaseDeadline) {
                        append("focus=TIMEOUT");
                        append("af_state=" + lastAfState);
                        finishProbe("FAIL", "focus_timeout_no_terminal_result");
                    }
                }
            }, AF_TIMEOUT_MS + 100L);
        } catch (Throwable error) {
            finishProbe("FAIL", "focus_request_exception_" + safe(error));
        }
    }

    private void finishProbe(final String status, final String reason) {
        if (!running) return;
        running = false;
        closeCameraResources();
        runOnUiThread(new Runnable() {
            @Override public void run() {
                append("reason=" + reason);
                append("camera_closed=yes");
                append("probe=" + status);
                probeButton.setEnabled(true);
            }
        });
    }

    private synchronized void closeCameraResources() {
        try { if (captureSession != null) captureSession.close(); } catch (Throwable ignored) {}
        captureSession = null;
        try { if (cameraDevice != null) cameraDevice.close(); } catch (Throwable ignored) {}
        cameraDevice = null;
        try { if (previewSurface != null) previewSurface.release(); } catch (Throwable ignored) {}
        previewSurface = null;
        if (cameraThread != null) {
            cameraThread.quitSafely();
            cameraThread = null;
            cameraHandler = null;
        }
    }

    private void append(final String line) {
        runOnUiThread(new Runnable() {
            @Override public void run() { output.append(line + "\n"); }
        });
    }

    private static String value(Object object) {
        return object == null ? "unknown" : object.toString();
    }

    private static String rectValue(Rect rect) {
        return rect == null ? "unknown" : rect.flattenToString();
    }

    private static String safe(Throwable error) {
        String name = error.getClass().getSimpleName();
        String message = error.getMessage();
        if (message == null || message.isEmpty()) return name;
        return (name + "_" + message).replaceAll("[^A-Za-z0-9_.-]+", "_");
    }
}
