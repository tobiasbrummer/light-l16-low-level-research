package io.github.tobiasbrummer.lightl16.stocklricapture;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
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
import android.media.Image;
import android.media.ImageReader;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.text.method.ScrollingMovementMethod;
import android.util.Size;
import android.view.Surface;
import android.view.TextureView;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Constructor;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/** Fixed, non-rooting reproduction of the stock same-session LRI path. */
public final class MainActivity extends Activity {
    private static final int PERMISSION_REQUEST = 43;
    private static final int LIGHT_RAW10 = 48;
    private static final int JPEG = 256;
    private static final String CAMERA_ID = "0";
    private static final int EXPECTED_ACTIVE_WIDTH = 4160;
    private static final int EXPECTED_ACTIVE_HEIGHT = 3120;
    private static final int EXPECTED_RAW_STREAM_WIDTH = 3840;
    private static final int EXPECTED_RAW_STREAM_HEIGHT = 2160;
    private static final float FIXED_FOCAL_LENGTH = 2.8f;
    private static final float FIXED_ZOOM_FACTOR = 1.0f;
    private static final int FOCUS_TYPE_USER_HW = 6;
    private static final long OPEN_TIMEOUT_MS = 8000L;
    private static final long AE_TIMEOUT_MS = 6000L;
    private static final long AF_TIMEOUT_MS = 9000L;
    private static final long ARM_WINDOW_MS = 15000L;
    private static final long CAPTURE_TIMEOUT_MS = 60000L;
    private static final long MIN_LRI_BYTES = 1024L * 1024L;
    private static final long MIN_FREE_BYTES = 512L * 1024L * 1024L;

    private final Object stateLock = new Object();
    private final StringBuilder report = new StringBuilder();
    private TextureView preview;
    private TextView output;
    private Button prepareButton;
    private Button captureButton;
    private HandlerThread cameraThread;
    private Handler cameraHandler;
    private CameraDevice cameraDevice;
    private CameraCaptureSession captureSession;
    private ImageReader rawReader;
    private ImageReader jpegReader;
    private Surface previewSurface;
    private CaptureRequest.Builder previewBuilder;
    private Rect activeArray;
    private boolean running;
    private boolean meteringDone;
    private boolean focusStarted;
    private boolean armed;
    private boolean captureIssued;
    private boolean captureCompleted;
    private boolean rawSaved;
    private boolean jpegSaved;
    private boolean terminal;
    private long armDeadline;
    private long measuredExposureNs = -1L;
    private int measuredSensitivity = -1;
    private int lastAeState = -1;
    private int lastAfState = -1;
    private File outputDirectory;
    private File lriFile;
    private File jpegFile;
    private File reportFile;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        int padding = dp(18);
        body.setPadding(padding, padding, padding, padding);

        TextView explanation = new TextView(this);
        explanation.setText(
            "No-Root-Test des Stock-Aufnahmepfads. Stufe 1 prüft das "
                + "Light-Format 48, öffnet Preview, JPEG und LRI gemeinsam und "
                + "fokussiert die Bildmitte. Die Camera2-Session bleibt danach "
                + "offen. Stufe 2 löst genau eine nicht-gestackte Aufnahme aus.\n\n"
                + "Kein lcc, kein Root, kein Service-Stopp und kein Neustart. "
                + "Vorher die normale Kamera-App vollständig schließen."
        );
        body.addView(explanation);

        preview = new TextureView(this);
        body.addView(preview, new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, dp(280)));

        prepareButton = new Button(this);
        prepareButton.setText("1. PIPELINE PRÜFEN + FOKUS");
        prepareButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View ignored) { startWithPermissions(); }
        });
        body.addView(prepareButton);

        captureButton = new Button(this);
        captureButton.setText("2. FOKUSIERTES LRI AUFNEHMEN");
        captureButton.setEnabled(false);
        captureButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View ignored) { issueStillCapture(); }
        });
        body.addView(captureButton);

        output = new TextView(this);
        output.setTextIsSelectable(true);
        output.setMovementMethod(new ScrollingMovementMethod());
        output.setText("pipeline=NOT_STARTED\n");
        body.addView(output);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(body);
        setContentView(scroll);
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private void startWithPermissions() {
        if (running) return;
        ArrayList<String> missing = new ArrayList<String>();
        if (checkSelfPermission(Manifest.permission.CAMERA)
                != PackageManager.PERMISSION_GRANTED) {
            missing.add(Manifest.permission.CAMERA);
        }
        if (checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                != PackageManager.PERMISSION_GRANTED) {
            missing.add(Manifest.permission.WRITE_EXTERNAL_STORAGE);
        }
        if (!missing.isEmpty()) {
            requestPermissions(missing.toArray(new String[missing.size()]),
                PERMISSION_REQUEST);
            return;
        }
        startPipeline();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions,
            int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != PERMISSION_REQUEST) return;
        for (int result : grantResults) {
            if (result != PackageManager.PERMISSION_GRANTED) {
                setOutput("result=REFUSED\nreason=required_permission_denied\n");
                return;
            }
        }
        startPipeline();
    }

    private void startPipeline() {
        if (running) return;
        if (!preview.isAvailable()) {
            setOutput("result=REFUSED\nreason=preview_surface_not_ready\n");
            return;
        }
        resetRunState();
        running = true;
        prepareButton.setEnabled(false);
        captureButton.setEnabled(false);
        line("pipeline=RUNNING");
        line("phase=opening_camera");
        cameraThread = new HandlerThread("l16-stock-lri-camera");
        cameraThread.start();
        cameraHandler = new Handler(cameraThread.getLooper());
        cameraHandler.postDelayed(new Runnable() {
            @Override public void run() {
                if (running && cameraDevice == null) fail("camera_open_timeout");
            }
        }, OPEN_TIMEOUT_MS);

        try {
            CameraManager manager = (CameraManager) getSystemService(Context.CAMERA_SERVICE);
            String[] ids = manager.getCameraIdList();
            line("camera_ids=" + Arrays.toString(ids));
            if (ids.length != 1 || !CAMERA_ID.equals(ids[0])) {
                throw new IllegalStateException("unexpected_camera_id_set");
            }
            CameraCharacteristics c = manager.getCameraCharacteristics(CAMERA_ID);
            Integer level = c.get(CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL);
            activeArray = c.get(CameraCharacteristics.SENSOR_INFO_ACTIVE_ARRAY_SIZE);
            float[] focalLengths = c.get(
                CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS);
            line("hardware_level=" + value(level));
            line("active_array=" + rectValue(activeArray));
            line("available_focal_lengths=" + Arrays.toString(focalLengths));
            line("requested_lens_focal_length=" + FIXED_FOCAL_LENGTH);
            line("requested_zoom_factor=" + FIXED_ZOOM_FACTOR);
            if (level == null
                    || level != CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_FULL
                    || activeArray == null
                    || activeArray.width() != EXPECTED_ACTIVE_WIDTH
                    || activeArray.height() != EXPECTED_ACTIVE_HEIGHT
                    || !containsFocalLength(focalLengths, FIXED_FOCAL_LENGTH)) {
                throw new IllegalStateException("unexpected_camera_characteristics");
            }
            StreamConfigurationMap map = c.get(
                CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            if (map == null) throw new IllegalStateException("missing_stream_map");
            Size[] rawSizes = map.getOutputSizes(LIGHT_RAW10);
            Size[] jpegSizes = map.getOutputSizes(JPEG);
            Size[] previewSizes = map.getOutputSizes(SurfaceTexture.class);
            line("format_48_sizes=" + Arrays.toString(rawSizes));
            Size rawSize = largest(rawSizes);
            Size jpegSize = largest(jpegSizes);
            Size previewSize = choosePreviewSize(previewSizes);
            if (rawSize.getWidth() != EXPECTED_RAW_STREAM_WIDTH
                    || rawSize.getHeight() != EXPECTED_RAW_STREAM_HEIGHT) {
                throw new IllegalStateException("unexpected_format_48_size");
            }
            line("selected_raw_size=" + rawSize);
            line("selected_jpeg_size=" + jpegSize);
            line("selected_preview_size=" + previewSize);
            prepareOutputDirectory();
            createReaders(rawSize, jpegSize);
            configurePreviewSurface(previewSize);
            manager.openCamera(CAMERA_ID, deviceCallback, cameraHandler);
        } catch (Throwable error) {
            fail("preflight_exception_" + safe(error));
        }
    }

    private void resetRunState() {
        synchronized (stateLock) {
            report.setLength(0);
            meteringDone = false;
            focusStarted = false;
            armed = false;
            captureIssued = false;
            captureCompleted = false;
            rawSaved = false;
            jpegSaved = false;
            terminal = false;
            measuredExposureNs = -1L;
            measuredSensitivity = -1;
            lastAeState = -1;
            lastAfState = -1;
            lriFile = null;
            jpegFile = null;
            reportFile = null;
        }
        setOutput("");
    }

    private void prepareOutputDirectory() {
        File dcim = Environment.getExternalStoragePublicDirectory(
            Environment.DIRECTORY_DCIM);
        outputDirectory = new File(dcim, "camera");
        if ((!outputDirectory.exists() && !outputDirectory.mkdirs())
                || !outputDirectory.isDirectory() || !outputDirectory.canWrite()) {
            throw new IllegalStateException("output_directory_not_writable");
        }
        long usable = outputDirectory.getUsableSpace();
        line("output_usable_bytes=" + usable);
        if (usable < MIN_FREE_BYTES) {
            throw new IllegalStateException("insufficient_output_space");
        }
    }

    private void createReaders(Size rawSize, Size jpegSize) {
        rawReader = ImageReader.newInstance(rawSize.getWidth(), rawSize.getHeight(),
            LIGHT_RAW10, 2);
        jpegReader = ImageReader.newInstance(jpegSize.getWidth(), jpegSize.getHeight(),
            JPEG, 2);
        rawReader.setOnImageAvailableListener(rawListener, cameraHandler);
        jpegReader.setOnImageAvailableListener(jpegListener, cameraHandler);
    }

    private void configurePreviewSurface(Size size) {
        SurfaceTexture texture = preview.getSurfaceTexture();
        if (texture == null) throw new IllegalStateException("missing_surface_texture");
        texture.setDefaultBufferSize(size.getWidth(), size.getHeight());
        previewSurface = new Surface(texture);
    }

    private final CameraDevice.StateCallback deviceCallback =
            new CameraDevice.StateCallback() {
        @Override public void onOpened(CameraDevice camera) {
            if (!running) { camera.close(); return; }
            cameraDevice = camera;
            createSession();
        }
        @Override public void onDisconnected(CameraDevice camera) {
            camera.close();
            fail("camera_disconnected");
        }
        @Override public void onError(CameraDevice camera, int error) {
            camera.close();
            fail("camera_error_" + error);
        }
    };

    private void createSession() {
        try {
            previewBuilder = cameraDevice.createCaptureRequest(
                CameraDevice.TEMPLATE_PREVIEW);
            previewBuilder.addTarget(previewSurface);
            applyAutoSettings(previewBuilder, false);
            List<Surface> surfaces = new ArrayList<Surface>();
            surfaces.add(previewSurface);
            surfaces.add(jpegReader.getSurface());
            surfaces.add(rawReader.getSurface());
            cameraDevice.createCaptureSession(surfaces, sessionCallback, cameraHandler);
            line("session_surface_count=3");
        } catch (Throwable error) {
            fail("session_create_exception_" + safe(error));
        }
    }

    private final CameraCaptureSession.StateCallback sessionCallback =
            new CameraCaptureSession.StateCallback() {
        @Override public void onConfigured(CameraCaptureSession session) {
            if (!running) { session.close(); return; }
            captureSession = session;
            line("session_configured=yes");
            startMetering();
        }
        @Override public void onConfigureFailed(CameraCaptureSession session) {
            fail("session_configuration_failed");
        }
    };

    private void startMetering() {
        try {
            MeteringRectangle roi = centerRoi();
            previewBuilder.set(CaptureRequest.CONTROL_AF_TRIGGER,
                CaptureRequest.CONTROL_AF_TRIGGER_IDLE);
            previewBuilder.set(CaptureRequest.CONTROL_AE_REGIONS,
                new MeteringRectangle[] {roi});
            previewBuilder.set(CaptureRequest.CONTROL_AF_REGIONS, null);
            line("metering_roi=" + roi.getRect().flattenToString());
            line("phase=metering");
            captureSession.setRepeatingRequest(previewBuilder.build(), resultCallback,
                cameraHandler);
            cameraHandler.postDelayed(new Runnable() {
                @Override public void run() {
                    if (running && !meteringDone) fail("metering_timeout");
                }
            }, AE_TIMEOUT_MS);
        } catch (Throwable error) {
            fail("metering_exception_" + safe(error));
        }
    }

    private final CameraCaptureSession.CaptureCallback resultCallback =
            new CameraCaptureSession.CaptureCallback() {
        @Override public void onCaptureCompleted(CameraCaptureSession session,
                CaptureRequest request, TotalCaptureResult result) {
            if (!running) return;
            updateResultValues(result);
            if (!meteringDone && (lastAeState == CaptureResult.CONTROL_AE_STATE_CONVERGED
                    || lastAeState == CaptureResult.CONTROL_AE_STATE_LOCKED)
                    && measuredExposureNs > 0L && measuredSensitivity > 0) {
                meteringDone = true;
                line("metering=PASS");
                line("ae_state=" + lastAeState);
                line("sensor_exposure_time_ns=" + measuredExposureNs);
                line("sensor_sensitivity=" + measuredSensitivity);
                startFocus();
                return;
            }
            if (focusStarted && !armed && !captureIssued
                    && (lastAfState == CaptureResult.CONTROL_AF_STATE_FOCUSED_LOCKED
                        || lastAfState
                            == CaptureResult.CONTROL_AF_STATE_NOT_FOCUSED_LOCKED)) {
                line("af_state=" + lastAfState);
                if (lastAfState == CaptureResult.CONTROL_AF_STATE_FOCUSED_LOCKED) {
                    armCapture();
                } else {
                    line("focus=FAIL");
                    fail("focus_not_focused_locked");
                }
            }
        }

        @Override public void onCaptureFailed(CameraCaptureSession session,
                CaptureRequest request,
                android.hardware.camera2.CaptureFailure failure) {
            fail("capture_request_failed_" + failure.getReason());
        }
    };

    private void updateResultValues(CaptureResult result) {
        Long exposure = result.get(CaptureResult.SENSOR_EXPOSURE_TIME);
        Integer sensitivity = result.get(CaptureResult.SENSOR_SENSITIVITY);
        Integer ae = result.get(CaptureResult.CONTROL_AE_STATE);
        Integer af = result.get(CaptureResult.CONTROL_AF_STATE);
        if (exposure != null) measuredExposureNs = exposure;
        if (sensitivity != null) measuredSensitivity = sensitivity;
        if (ae != null) lastAeState = ae;
        if (af != null) lastAfState = af;
    }

    private void startFocus() {
        try {
            focusStarted = true;
            MeteringRectangle roi = centerRoi();
            CaptureRequest.Builder focus = cameraDevice.createCaptureRequest(
                CameraDevice.TEMPLATE_PREVIEW);
            focus.addTarget(previewSurface);
            applyAutoSettings(focus, true);
            focus.set(CaptureRequest.CONTROL_AE_REGIONS, null);
            focus.set(CaptureRequest.CONTROL_AF_REGIONS,
                new MeteringRectangle[] {roi});
            focus.set(CaptureRequest.CONTROL_AF_TRIGGER,
                CaptureRequest.CONTROL_AF_TRIGGER_START);
            setVendorKey(focus, "co.light.focus_type", Integer.TYPE,
                Integer.valueOf(FOCUS_TYPE_USER_HW));
            line("focus_roi=" + roi.getRect().flattenToString());
            line("focus_type=" + FOCUS_TYPE_USER_HW);
            line("phase=focus");
            captureSession.capture(focus.build(), resultCallback, cameraHandler);
            cameraHandler.postDelayed(new Runnable() {
                @Override public void run() {
                    if (running && focusStarted && !armed && !captureIssued) {
                        fail("focus_timeout");
                    }
                }
            }, AF_TIMEOUT_MS);
        } catch (Throwable error) {
            fail("focus_exception_" + safe(error));
        }
    }

    private void armCapture() {
        armed = true;
        armDeadline = SystemClock.elapsedRealtime() + ARM_WINDOW_MS;
        line("focus=PASS");
        line("pipeline=ARMED");
        line("arm_window_ms=" + ARM_WINDOW_MS);
        runOnUiThread(new Runnable() {
            @Override public void run() { captureButton.setEnabled(true); }
        });
        cameraHandler.postDelayed(new Runnable() {
            @Override public void run() {
                if (running && armed && !captureIssued) fail("capture_arm_timeout");
            }
        }, ARM_WINDOW_MS);
    }

    private void issueStillCapture() {
        if (!running || !armed || captureIssued || captureSession == null) return;
        if (SystemClock.elapsedRealtime() > armDeadline) {
            fail("capture_arm_expired");
            return;
        }
        armed = false;
        captureIssued = true;
        captureButton.setEnabled(false);
        String stamp = new SimpleDateFormat("yyyyMMdd_HHmmss_SSS", Locale.US)
            .format(new Date());
        lriFile = new File(outputDirectory, "RDI_STOCK_" + stamp + ".lri");
        jpegFile = new File(outputDirectory, "IMG_STOCK_" + stamp + ".jpg");
        reportFile = new File(outputDirectory, "RDI_STOCK_" + stamp + ".txt");
        line("phase=still_capture");
        line("stacked_capture=false");
        try {
            CaptureRequest.Builder still = cameraDevice.createCaptureRequest(
                CameraDevice.TEMPLATE_STILL_CAPTURE);
            still.addTarget(jpegReader.getSurface());
            still.addTarget(rawReader.getSurface());
            applyAutoSettings(still, true);
            still.set(CaptureRequest.CONTROL_AE_REGIONS, null);
            still.set(CaptureRequest.CONTROL_AF_REGIONS, null);
            still.set(CaptureRequest.CONTROL_AF_TRIGGER,
                CaptureRequest.CONTROL_AF_TRIGGER_IDLE);
            still.set(CaptureRequest.JPEG_ORIENTATION, Integer.valueOf(0));
            captureSession.capture(still.build(), stillCallback, cameraHandler);
            cameraHandler.postDelayed(new Runnable() {
                @Override public void run() {
                    if (running && captureIssued && !terminal) {
                        fail("still_capture_timeout");
                    }
                }
            }, CAPTURE_TIMEOUT_MS);
        } catch (Throwable error) {
            fail("still_capture_exception_" + safe(error));
        }
    }

    private final CameraCaptureSession.CaptureCallback stillCallback =
            new CameraCaptureSession.CaptureCallback() {
        @Override public void onCaptureStarted(CameraCaptureSession session,
                CaptureRequest request, long timestamp, long frameNumber) {
            line("still_started=yes");
            line("still_frame_number=" + frameNumber);
        }
        @Override public void onCaptureCompleted(CameraCaptureSession session,
                CaptureRequest request, TotalCaptureResult result) {
            updateResultValues(result);
            captureCompleted = true;
            line("still_capture_result=PASS");
            line("still_ae_state=" + lastAeState);
            line("still_af_state=" + lastAfState);
            line("still_exposure_time_ns=" + measuredExposureNs);
            line("still_sensitivity=" + measuredSensitivity);
            line("vendor_stacked_capture_fw=" + vendorResultValue(result,
                "co.light.stacked_capture_fw", Byte.TYPE));
            line("vendor_stacked_capture_total_size=" + vendorResultValue(result,
                "co.light.stacked_capture_total_size", Integer.TYPE));
            line("vendor_stacked_capture_num_transfers=" + vendorResultValue(result,
                "co.light.stacked_capture_num_transfers", Integer.TYPE));
            maybeFinishPass();
        }
        @Override public void onCaptureFailed(CameraCaptureSession session,
                CaptureRequest request,
                android.hardware.camera2.CaptureFailure failure) {
            fail("still_capture_failed_" + failure.getReason());
        }
    };

    private final ImageReader.OnImageAvailableListener rawListener =
            new ImageReader.OnImageAvailableListener() {
        @Override public void onImageAvailable(ImageReader reader) {
            final Image image;
            try {
                image = reader.acquireNextImage();
            } catch (Throwable error) {
                fail("raw_acquire_exception_" + safe(error));
                return;
            }
            if (image == null) {
                fail("raw_image_missing");
                return;
            }
            line("raw_image_available=yes");
            new Thread(new Runnable() {
                @Override public void run() { saveRawImage(image); }
            }, "l16-lri-writer").start();
        }
    };

    private final ImageReader.OnImageAvailableListener jpegListener =
            new ImageReader.OnImageAvailableListener() {
        @Override public void onImageAvailable(ImageReader reader) {
            final Image image;
            try {
                image = reader.acquireNextImage();
            } catch (Throwable error) {
                fail("jpeg_acquire_exception_" + safe(error));
                return;
            }
            if (image == null) {
                fail("jpeg_image_missing");
                return;
            }
            line("jpeg_image_available=yes");
            new Thread(new Runnable() {
                @Override public void run() { saveJpegImage(image); }
            }, "l16-jpeg-writer").start();
        }
    };

    private void saveRawImage(Image image) {
        File partial = new File(lriFile.getAbsolutePath() + ".partial");
        boolean imageClosed = false;
        try {
            ByteBuffer buffer = firstPlaneBuffer(image);
            int remaining = buffer.remaining();
            if (remaining < MIN_LRI_BYTES || buffer.get(buffer.position()) != 'L'
                    || buffer.get(buffer.position() + 1) != 'E'
                    || buffer.get(buffer.position() + 2) != 'L'
                    || buffer.get(buffer.position() + 3) != 'R') {
                throw new IllegalStateException("unexpected_lri_payload");
            }
            String sha256 = writeBuffer(partial, buffer);
            if (!partial.renameTo(lriFile)) {
                throw new IllegalStateException("lri_rename_failed");
            }
            image.close();
            imageClosed = true;
            rawSaved = true;
            line("lri_path=" + lriFile.getAbsolutePath());
            line("lri_size=" + lriFile.length());
            line("lri_sha256=" + sha256);
            scanFile(lriFile);
            maybeFinishPass();
        } catch (Throwable error) {
            if (partial.exists()) partial.delete();
            fail("lri_write_exception_" + safe(error));
        } finally {
            if (!imageClosed) image.close();
        }
    }

    private void saveJpegImage(Image image) {
        File partial = new File(jpegFile.getAbsolutePath() + ".partial");
        boolean imageClosed = false;
        try {
            ByteBuffer buffer = firstPlaneBuffer(image);
            if (buffer.remaining() < 1024
                    || (buffer.get(buffer.position()) & 0xff) != 0xff
                    || (buffer.get(buffer.position() + 1) & 0xff) != 0xd8) {
                throw new IllegalStateException("unexpected_jpeg_payload");
            }
            String sha256 = writeBuffer(partial, buffer);
            if (!partial.renameTo(jpegFile)) {
                throw new IllegalStateException("jpeg_rename_failed");
            }
            image.close();
            imageClosed = true;
            jpegSaved = true;
            line("jpeg_path=" + jpegFile.getAbsolutePath());
            line("jpeg_size=" + jpegFile.length());
            line("jpeg_sha256=" + sha256);
            scanFile(jpegFile);
            maybeFinishPass();
        } catch (Throwable error) {
            if (partial.exists()) partial.delete();
            fail("jpeg_write_exception_" + safe(error));
        } finally {
            if (!imageClosed) image.close();
        }
    }

    private static ByteBuffer firstPlaneBuffer(Image image) {
        Image.Plane[] planes = image.getPlanes();
        if (planes == null || planes.length < 1) {
            throw new IllegalStateException("image_has_no_plane");
        }
        ByteBuffer buffer = planes[0].getBuffer();
        if (buffer == null) throw new IllegalStateException("plane_has_no_buffer");
        buffer.position(0);
        return buffer;
    }

    private static String writeBuffer(File file, ByteBuffer buffer) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        FileOutputStream stream = new FileOutputStream(file);
        try {
            byte[] chunk = new byte[64 * 1024];
            while (buffer.hasRemaining()) {
                int count = Math.min(buffer.remaining(), chunk.length);
                buffer.get(chunk, 0, count);
                stream.write(chunk, 0, count);
                digest.update(chunk, 0, count);
            }
            stream.getFD().sync();
        } finally {
            stream.close();
        }
        return hex(digest.digest());
    }

    private void maybeFinishPass() {
        synchronized (stateLock) {
            if (terminal || !captureCompleted || !rawSaved || !jpegSaved) return;
            terminal = true;
        }
        line("result=PASS");
        line("reason=focused_same_session_lri_and_jpeg_saved");
        closeResources();
        writeReportBestEffort();
        runOnUiThread(new Runnable() {
            @Override public void run() {
                prepareButton.setText("AUFNAHME ABGESCHLOSSEN");
                prepareButton.setEnabled(false);
                captureButton.setEnabled(false);
            }
        });
    }

    private void fail(String reason) {
        synchronized (stateLock) {
            if (terminal) return;
            terminal = true;
        }
        line("result=FAIL");
        line("reason=" + reason);
        line("still_attempted=" + (captureIssued ? "yes" : "no"));
        closeResources();
        writeReportBestEffort();
        runOnUiThread(new Runnable() {
            @Override public void run() {
                prepareButton.setText("TEST FEHLGESCHLAGEN");
                prepareButton.setEnabled(false);
                captureButton.setEnabled(false);
            }
        });
    }

    private void closeResources() {
        running = false;
        armed = false;
        try { if (captureSession != null) captureSession.stopRepeating(); }
        catch (Throwable ignored) {}
        try { if (captureSession != null) captureSession.close(); }
        catch (Throwable ignored) {}
        captureSession = null;
        try { if (cameraDevice != null) cameraDevice.close(); }
        catch (Throwable ignored) {}
        cameraDevice = null;
        try { if (rawReader != null) rawReader.close(); }
        catch (Throwable ignored) {}
        rawReader = null;
        try { if (jpegReader != null) jpegReader.close(); }
        catch (Throwable ignored) {}
        jpegReader = null;
        try { if (previewSurface != null) previewSurface.release(); }
        catch (Throwable ignored) {}
        previewSurface = null;
        HandlerThread oldThread = cameraThread;
        cameraThread = null;
        cameraHandler = null;
        if (oldThread != null) oldThread.quitSafely();
        line("camera_closed=yes");
    }

    private void applyAutoSettings(CaptureRequest.Builder builder, boolean locked)
            throws Exception {
        builder.set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO);
        builder.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON);
        builder.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_AUTO);
        builder.set(CaptureRequest.CONTROL_AWB_MODE,
            CaptureRequest.CONTROL_AWB_MODE_AUTO);
        builder.set(CaptureRequest.CONTROL_AE_LOCK, Boolean.valueOf(locked));
        builder.set(CaptureRequest.CONTROL_AWB_LOCK, Boolean.valueOf(locked));
        builder.set(CaptureRequest.LENS_FOCAL_LENGTH,
            Float.valueOf(FIXED_FOCAL_LENGTH));
        builder.set(CaptureRequest.SCALER_CROP_REGION, new Rect(activeArray));
        setVendorKey(builder, "co.light.zoom_factor", Float.TYPE,
            Float.valueOf(FIXED_ZOOM_FACTOR));
        setVendorKey(builder, "co.light.stacked_capture_state", Byte.TYPE,
            Byte.valueOf((byte) 0));
        setVendorKey(builder, "co.light.iso_range_min", Integer.TYPE,
            Integer.valueOf(0));
        setVendorKey(builder, "co.light.iso_range_max", Integer.TYPE,
            Integer.valueOf(0));
        setVendorKey(builder, "co.light.shutter_range_min", Long.TYPE,
            Long.valueOf(0L));
        setVendorKey(builder, "co.light.shutter_range_max", Long.TYPE,
            Long.valueOf(0L));
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static <T> void setVendorKey(CaptureRequest.Builder builder,
            String name, Class<T> type, T value) throws Exception {
        Constructor<CaptureRequest.Key> constructor =
            CaptureRequest.Key.class.getConstructor(String.class, Class.class);
        CaptureRequest.Key<T> key = (CaptureRequest.Key<T>) constructor.newInstance(
            name, type);
        builder.set(key, value);
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static <T> String vendorResultValue(CaptureResult result,
            String name, Class<T> type) {
        try {
            Constructor<CaptureResult.Key> constructor =
                CaptureResult.Key.class.getConstructor(String.class, Class.class);
            CaptureResult.Key<T> key = (CaptureResult.Key<T>) constructor.newInstance(
                name, type);
            return value(result.get(key));
        } catch (Throwable error) {
            return "unavailable_" + safe(error);
        }
    }

    private MeteringRectangle centerRoi() {
        int width = activeArray.width() / 2;
        int height = activeArray.height() / 2;
        int left = activeArray.left + (activeArray.width() - width) / 2;
        int top = activeArray.top + (activeArray.height() - height) / 2;
        return new MeteringRectangle(new Rect(left, top, left + width, top + height),
            MeteringRectangle.METERING_WEIGHT_MAX);
    }

    private static boolean containsFocalLength(float[] values, float expected) {
        if (values == null) return false;
        for (float value : values) {
            if (Math.abs(value - expected) < 0.01f) return true;
        }
        return false;
    }

    private static Size largest(Size[] sizes) {
        if (sizes == null || sizes.length == 0) {
            throw new IllegalStateException("required_output_format_missing");
        }
        Size best = sizes[0];
        for (Size size : sizes) {
            if ((long) size.getWidth() * size.getHeight()
                    > (long) best.getWidth() * best.getHeight()) best = size;
        }
        return best;
    }

    private static Size choosePreviewSize(Size[] sizes) {
        if (sizes == null || sizes.length == 0) {
            throw new IllegalStateException("preview_output_missing");
        }
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

    private void scanFile(File file) {
        sendBroadcast(new Intent(Intent.ACTION_MEDIA_SCANNER_SCAN_FILE,
            Uri.fromFile(file)));
    }

    private void writeReportBestEffort() {
        if (reportFile == null || outputDirectory == null) return;
        try {
            FileOutputStream stream = new FileOutputStream(reportFile);
            try {
                stream.write(snapshotReport().getBytes("UTF-8"));
                stream.getFD().sync();
            } finally {
                stream.close();
            }
            scanFile(reportFile);
        } catch (Throwable error) {
            line("report_write_error=" + safe(error));
        }
    }

    private void line(String value) {
        synchronized (stateLock) { report.append(value).append('\n'); }
        final String text = snapshotReport();
        runOnUiThread(new Runnable() {
            @Override public void run() { output.setText(text); }
        });
    }

    private String snapshotReport() {
        synchronized (stateLock) { return report.toString(); }
    }

    private void setOutput(final String text) {
        runOnUiThread(new Runnable() {
            @Override public void run() { output.setText(text); }
        });
    }

    private static String safe(Throwable error) {
        String message = error.getMessage();
        String value = error.getClass().getSimpleName()
            + (message == null ? "" : "_" + message);
        return value.replaceAll("[^A-Za-z0-9_.-]+", "_");
    }

    private static String value(Object value) {
        return value == null ? "null" : String.valueOf(value);
    }

    private static String rectValue(Rect rect) {
        return rect == null ? "null" : rect.flattenToString();
    }

    private static String hex(byte[] bytes) {
        StringBuilder value = new StringBuilder(bytes.length * 2);
        for (byte item : bytes) value.append(String.format(Locale.US, "%02x", item));
        return value.toString();
    }

    @Override
    protected void onPause() {
        if (running && !terminal) fail("activity_paused");
        super.onPause();
    }
}
