package io.github.tobiasbrummer.lightl16.adaptiveagroupcapture;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.ImageFormat;
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
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.text.method.ScrollingMovementMethod;
import android.util.Range;
import android.util.Rational;
import android.util.Size;
import android.view.Surface;
import android.view.TextureView;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.File;
import java.io.BufferedReader;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/** Preview meter and deliberate launcher for one adaptive A1-A5 root capture. */
public final class MainActivity extends Activity {
    private static final int CAMERA_PERMISSION_REQUEST = 51;
    private static final String REPORT_NAME =
        "light-l16-adaptive-a-group-meter-last-display.txt";
    private static final String CAPTURE_REPORT_NAME =
        "light-l16-adaptive-a-group-capture-last-display.txt";
    private static final String PLAN_NAME = "p.txt";
    private static final String UI_LAUNCH_ARM_NAME = "u";
    private static final String SPENT_NAME = "spent";
    private static final String PLAN_VERSION = "L16_ADAPTIVE_A_GROUP_PLAN_V1";
    private static final String UI_LAUNCH_ARM_VALUE =
        "L16_ADAPTIVE_A_GROUP_CAPTURE_UI_LAUNCH_V1";
    private static final long CAPTURE_PLAN_WINDOW_MS = 60000L;
    private static final long ROOT_MIN_EXPOSURE_NS = 10000L;
    private static final long MAX_RECOVERY_RESULT_SIZE = 16384L;
    private static final double MIN_USEFUL_PILOT_SPAN_EV = 0.5;
    private static final long OPEN_TIMEOUT_MS = 8000L;
    private static final long MEASUREMENT_TIMEOUT_MS = 8000L;
    private static final int SETTLE_FRAME_COUNT = 3;
    private static final int MEASUREMENT_FRAME_COUNT = 8;
    private static final int HIGHLIGHT_FRAME_COUNT = 4;
    private static final int LUMA_SAMPLE_STEP = 2;
    private static final float PREFERRED_FOCAL_LENGTH = 2.8f;
    private static final double MAX_RESOLVED_HIGHLIGHT_CLIPPED_FRACTION = 0.001;
    private static final int PHASE_IDLE = 0;
    private static final int PHASE_SHADOW_SETTLE = 1;
    private static final int PHASE_SHADOW_COLLECT = 2;
    private static final int PHASE_HIGHLIGHT_WAIT_AE = 3;
    private static final int PHASE_HIGHLIGHT_SETTLE = 4;
    private static final int PHASE_HIGHLIGHT_COLLECT = 5;
    private static final int PHASE_ANALYZING = 6;

    private final Object reportLock = new Object();
    private final StringBuilder report = new StringBuilder();
    private TextureView preview;
    private TextView output;
    private Button previewButton;
    private Button measureButton;
    private Button captureButton;
    private HandlerThread cameraThread;
    private Handler cameraHandler;
    private CameraDevice cameraDevice;
    private CameraCaptureSession captureSession;
    private CaptureRequest.Builder previewBuilder;
    private Surface previewSurface;
    private ImageReader yuvReader;
    private String selectedCameraId;
    private float selectedFocalLength;
    private Rect activeArray;
    private Range<Long> exposureRange;
    private Range<Integer> sensitivityRange;
    private Range<Integer> aeCompensationRange;
    private Rational aeCompensationStep;
    private int highlightCompensationUnits;
    private boolean aeLockAvailable;
    private boolean awbLockAvailable;
    private volatile boolean running;
    private volatile boolean previewReady;
    private volatile boolean aeReady;
    private volatile boolean measuring;
    private volatile boolean terminal;
    private volatile int measurementPhase;
    private volatile long latestAeExposureNs = -1L;
    private volatile int latestAeSensitivity = -1;
    private volatile int latestAeState = -1;
    private int settleFramesRemaining;
    private long shadowAnchorExposureNs;
    private int shadowAnchorSensitivity;
    private long shadowIso100EquivalentNs;
    private long highlightAnchorExposureNs;
    private int highlightAnchorSensitivity;
    private long highlightIso100EquivalentNs;
    private long shadowExposureMinNs;
    private long shadowExposureMaxNs;
    private int shadowSensitivityMin;
    private int shadowSensitivityMax;
    private long highlightExposureMinNs;
    private long highlightExposureMaxNs;
    private int highlightSensitivityMin;
    private int highlightSensitivityMax;
    private LumaAccumulator shadowAccumulator;
    private LumaAccumulator highlightAccumulator;
    private volatile long[] pendingCapturePlan;
    private volatile long capturePlanDeadlineMs;

    private static final class YuvStats {
        final int width;
        final int height;
        final int sampleStep;
        final int sampleCount;
        final int frameCount;
        final long firstTimestampNs;
        final long lastTimestampNs;
        final String rangeAssumption;
        final int blackCode;
        final int whiteCode;
        final int p001;
        final int p01;
        final int p05;
        final int p50;
        final int p999;
        final int p9999;
        final int shadowSelectedCount;
        final double shadowMeanCode;
        final double shadowTemporalSnr;
        final double temporalInstabilityFraction;
        final double highlightNormalizedCode;
        final double highlightLinearFraction;
        final double clippedFraction;

        YuvStats(int width, int height, int sampleStep, int sampleCount,
                int frameCount, long firstTimestampNs, long lastTimestampNs,
                String rangeAssumption, int blackCode, int whiteCode, int p001,
                int p01, int p05, int p50, int p999, int p9999,
                int shadowSelectedCount, double shadowMeanCode,
                double shadowTemporalSnr, double temporalInstabilityFraction,
                double highlightNormalizedCode, double highlightLinearFraction,
                double clippedFraction) {
            this.width = width;
            this.height = height;
            this.sampleStep = sampleStep;
            this.sampleCount = sampleCount;
            this.frameCount = frameCount;
            this.firstTimestampNs = firstTimestampNs;
            this.lastTimestampNs = lastTimestampNs;
            this.rangeAssumption = rangeAssumption;
            this.blackCode = blackCode;
            this.whiteCode = whiteCode;
            this.p001 = p001;
            this.p01 = p01;
            this.p05 = p05;
            this.p50 = p50;
            this.p999 = p999;
            this.p9999 = p9999;
            this.shadowSelectedCount = shadowSelectedCount;
            this.shadowMeanCode = shadowMeanCode;
            this.shadowTemporalSnr = shadowTemporalSnr;
            this.temporalInstabilityFraction = temporalInstabilityFraction;
            this.highlightNormalizedCode = highlightNormalizedCode;
            this.highlightLinearFraction = highlightLinearFraction;
            this.clippedFraction = clippedFraction;
        }
    }

    private static final class LumaAccumulator {
        final int width;
        final int height;
        final int step;
        final int sampledWidth;
        final int sampledHeight;
        final long[] sums;
        final long[] squaredSums;
        int frames;
        long firstTimestampNs = -1L;
        long lastTimestampNs = -1L;

        LumaAccumulator(Image image, int step) {
            width = image.getWidth();
            height = image.getHeight();
            this.step = step;
            sampledWidth = (width + step - 1) / step;
            sampledHeight = (height + step - 1) / step;
            sums = new long[sampledWidth * sampledHeight];
            squaredSums = new long[sums.length];
        }

        void add(Image image) {
            if (image.getFormat() != ImageFormat.YUV_420_888
                    || image.getWidth() != width || image.getHeight() != height
                    || image.getPlanes().length < 1) {
                throw new IllegalStateException("unexpected_yuv_layout");
            }
            Image.Plane yPlane = image.getPlanes()[0];
            int rowStride = yPlane.getRowStride();
            int pixelStride = yPlane.getPixelStride();
            if (pixelStride <= 0 || rowStride <= 0) {
                throw new IllegalStateException("invalid_yuv_stride");
            }
            ByteBuffer buffer = yPlane.getBuffer().duplicate();
            int base = buffer.position();
            int limit = buffer.limit();
            int index = 0;
            for (int row = 0; row < height; row += step) {
                int rowOffset = base + row * rowStride;
                for (int column = 0; column < width; column += step) {
                    int offset = rowOffset + column * pixelStride;
                    if (offset < base || offset >= limit) {
                        throw new IllegalStateException("yuv_buffer_too_short");
                    }
                    int value = buffer.get(offset) & 0xff;
                    sums[index] += value;
                    squaredSums[index] += (long) value * value;
                    index++;
                }
            }
            if (index != sums.length) {
                throw new IllegalStateException("yuv_sample_count_mismatch");
            }
            if (frames == 0) firstTimestampNs = image.getTimestamp();
            lastTimestampNs = image.getTimestamp();
            frames++;
        }

        YuvStats analyze() {
            if (frames < 2) throw new IllegalStateException("too_few_yuv_frames");
            long[] histogram = new long[256];
            double[] means = new double[sums.length];
            double[] sigmas = new double[sums.length];
            for (int i = 0; i < sums.length; i++) {
                double mean = sums[i] / (double) frames;
                double centered = squaredSums[i] - sums[i] * mean;
                double variance = Math.max(0.0, centered / (frames - 1.0));
                means[i] = mean;
                sigmas[i] = Math.sqrt(variance);
                int bin = Math.max(0, Math.min(255, (int) Math.round(mean)));
                histogram[bin]++;
            }

            int p001 = HdrMath.percentileBin(histogram, sums.length, 1, 1000);
            int p01 = HdrMath.percentileBin(histogram, sums.length, 1, 100);
            int p05 = HdrMath.percentileBin(histogram, sums.length, 5, 100);
            int p50 = HdrMath.percentileBin(histogram, sums.length, 1, 2);
            int p999 = HdrMath.percentileBin(histogram, sums.length, 999, 1000);
            int p9999 = HdrMath.percentileBin(histogram, sums.length, 9999, 10000);

            boolean likelyLimitedRange = p001 >= 12 && p9999 <= 240;
            int black = likelyLimitedRange ? 16 : 0;
            int white = likelyLimitedRange ? 235 : 255;
            String range = likelyLimitedRange
                ? "INFERRED_LIMITED_16_235" : "INFERRED_FULL_0_255";
            // Use the same percentile as the explicit 0.1 % clipping budget.
            // p99.99 made a handful of unavoidable specular pixels veto an
            // otherwise valid exposure even though the clipping-fraction gate
            // deliberately allowed up to 0.1 %.
            double normalizedHighlight = clamp01(
                (p999 - black) / (double) (white - black));
            double linearHighlight = HdrMath.gammaDecode(normalizedHighlight);

            int shadowLow = Math.max(black + 1, p01);
            int shadowHigh = Math.max(shadowLow, p05);
            double[] shadowSnrs = new double[sums.length];
            int shadowCount = 0;
            double shadowCodeSum = 0.0;
            long unstableCount = 0L;
            long clippedCount = 0L;
            for (int i = 0; i < means.length; i++) {
                double mean = means[i];
                if (mean >= white - 1.0) clippedCount++;
                if (sigmas[i] > 2.0) unstableCount++;
                if (mean >= shadowLow && mean <= shadowHigh) {
                    double signal = mean - black;
                    if (signal > 0.0) {
                        shadowSnrs[shadowCount++] = signal
                            / Math.max(0.5, sigmas[i]);
                        shadowCodeSum += mean;
                    }
                }
            }
            if (shadowCount < 64) {
                throw new IllegalStateException("insufficient_shadow_samples");
            }
            Arrays.sort(shadowSnrs, 0, shadowCount);
            double shadowSnr = shadowSnrs[shadowCount / 2];
            return new YuvStats(width, height, step, sums.length, frames,
                firstTimestampNs, lastTimestampNs, range, black, white, p001,
                p01, p05, p50, p999, p9999, shadowCount,
                shadowCodeSum / shadowCount, shadowSnr,
                unstableCount / (double) sums.length, normalizedHighlight,
                linearHighlight, clippedCount / (double) sums.length);
        }

        private static double clamp01(double value) {
            return Math.max(0.0, Math.min(1.0, value));
        }
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        int padding = dp(16);
        body.setPadding(padding, padding, padding, padding);

        TextView explanation = new TextView(this);
        explanation.setText(
            "Zuerst Preview und Bildausschnitt festlegen. Danach wertet die "
                + "App eine normale sowie eine um -2 EV korrigierte, jeweils "
                + "verriegelte YUV-Phase aus: Highlights über p99,9 und "
                + "Schatten über ihr zeitliches Signal-Rausch-Verhältnis. "
                + "Nur bei stabiler Messung und aufgelöstem Highlight-Endpunkt "
                + "wird für 60 Sekunden eine dritte Taste freigegeben. Sie "
                + "schließt Camera2, prüft den begrenzten Root-Weg und nimmt "
                + "A1-A5 mit den angezeigten Werten und Gain 1 auf. Nach einem "
                + "möglichen Kamerazugriff folgt absichtlich ein Neustart."
        );
        body.addView(explanation);

        preview = new TextureView(this);
        body.addView(preview, new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, dp(280)));

        previewButton = new Button(this);
        previewButton.setText("1. PREVIEW + BELICHTUNGSMESSUNG STARTEN");
        previewButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View ignored) { startWithPermission(); }
        });
        body.addView(previewButton);

        measureButton = new Button(this);
        measureButton.setText("2. HIGHLIGHTS + SCHATTEN MESSEN");
        measureButton.setEnabled(false);
        measureButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View ignored) { startYuvMeasurement(); }
        });
        body.addView(measureButton);

        captureButton = new Button(this);
        captureButton.setText("3. A1-A5 MIT DIESEN WERTEN AUFNEHMEN");
        captureButton.setEnabled(false);
        captureButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View ignored) { startRootCapture(); }
        });
        body.addView(captureButton);

        output = new TextView(this);
        output.setTextIsSelectable(true);
        output.setMovementMethod(new ScrollingMovementMethod());
        body.addView(output);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(body);
        setContentView(scroll);
        if (privateFile(SPENT_NAME).exists()) {
            previewButton.setEnabled(false);
            measureButton.setEnabled(false);
            captureButton.setEnabled(false);
            showSpentCaptureResult();
        } else {
            resetReport("probe=NOT_STARTED\n");
        }
    }

    private void showSpentCaptureResult() {
        StringBuilder recovered = new StringBuilder();
        recovered.append("probe=RECOVERY_DISPLAY_ONLY\n");
        recovered.append("installation_spent=yes\n");
        recovered.append("camera_touched_by_recovery=no\n");
        recovered.append("root_or_lcc_invoked_by_recovery=no\n");
        File result = privateFile("r.txt");
        try {
            if (!result.isFile() || result.length() < 1L) {
                recovered.append("supervisor_result=missing_or_empty\n");
            } else {
                recovered.append("supervisor_result_begin\n");
                recovered.append(readBoundedAscii(result));
                recovered.append("supervisor_result_end\n");
            }
        } catch (Throwable error) {
            recovered.append("supervisor_result_read_error=")
                .append(safe(error)).append('\n');
        }
        recovered.append(
            "action=preserve_this_report_before_uninstalling_the_app\n");
        String text = recovered.toString();
        resetReport(text);
        persistRecoveryCaptureReport(text);
    }

    @Override
    protected void onPause() {
        if (running) finishProbe("ABORTED", "activity_paused");
        else closeCameraResources();
        super.onPause();
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private void startWithPermission() {
        if (running || privateFile(SPENT_NAME).exists()) return;
        if (checkSelfPermission(Manifest.permission.CAMERA)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] {Manifest.permission.CAMERA},
                CAMERA_PERMISSION_REQUEST);
            return;
        }
        startPreviewPipeline();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions,
            int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == CAMERA_PERMISSION_REQUEST && grantResults.length == 1
                && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            startPreviewPipeline();
        } else if (requestCode == CAMERA_PERMISSION_REQUEST) {
            resetReport("probe=REFUSED\nreason=camera_permission_denied\n");
        }
    }

    private void startPreviewPipeline() {
        if (!preview.isAvailable()) {
            resetReport("probe=REFUSED\nreason=preview_surface_not_ready\n");
            return;
        }
        resetRunState();
        running = true;
        previewButton.setEnabled(false);
        measureButton.setEnabled(false);
        captureButton.setEnabled(false);
        resetReport("");
        line("probe=RUNNING");
        line("phase=opening_camera");
        File reportFile = reportFile();
        line("display_report_path="
            + (reportFile == null ? "unavailable" : reportFile.getAbsolutePath()));

        cameraThread = new HandlerThread("l16-hdr-meter-camera");
        cameraThread.start();
        cameraHandler = new Handler(cameraThread.getLooper());
        cameraHandler.postDelayed(new Runnable() {
            @Override public void run() {
                if (running && cameraDevice == null) fail("camera_open_timeout");
            }
        }, OPEN_TIMEOUT_MS);

        try {
            CameraManager manager = (CameraManager) getSystemService(Context.CAMERA_SERVICE);
            selectedCameraId = chooseCamera(manager);
            CameraCharacteristics c = manager.getCameraCharacteristics(selectedCameraId);
            inspectCharacteristics(c);
            configureStreams(c);
            manager.openCamera(selectedCameraId, deviceCallback, cameraHandler);
        } catch (Throwable error) {
            fail("open_exception_" + safe(error));
        }
    }

    private void resetRunState() {
        pendingCapturePlan = null;
        capturePlanDeadlineMs = 0L;
        deleteQuietly(privateFile(PLAN_NAME));
        deleteQuietly(privateFile(UI_LAUNCH_ARM_NAME));
        previewReady = false;
        aeReady = false;
        measuring = false;
        terminal = false;
        measurementPhase = PHASE_IDLE;
        latestAeExposureNs = -1L;
        latestAeSensitivity = -1;
        latestAeState = -1;
        shadowAccumulator = null;
        highlightAccumulator = null;
    }

    private String chooseCamera(CameraManager manager) throws CameraAccessException {
        String[] ids = manager.getCameraIdList();
        line("camera_ids=" + Arrays.toString(ids));
        for (String id : ids) {
            CameraCharacteristics c = manager.getCameraCharacteristics(id);
            StreamConfigurationMap map = c.get(
                CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            if (map != null && hasSizes(map.getOutputSizes(SurfaceTexture.class))
                    && hasSizes(map.getOutputSizes(ImageFormat.YUV_420_888))) {
                return id;
            }
        }
        throw new IllegalStateException("no_preview_yuv_camera");
    }

    private void inspectCharacteristics(CameraCharacteristics c) {
        Integer level = c.get(CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL);
        int[] capabilities = c.get(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES);
        activeArray = c.get(CameraCharacteristics.SENSOR_INFO_ACTIVE_ARRAY_SIZE);
        exposureRange = c.get(CameraCharacteristics.SENSOR_INFO_EXPOSURE_TIME_RANGE);
        sensitivityRange = c.get(CameraCharacteristics.SENSOR_INFO_SENSITIVITY_RANGE);
        aeCompensationRange = c.get(
            CameraCharacteristics.CONTROL_AE_COMPENSATION_RANGE);
        aeCompensationStep = c.get(
            CameraCharacteristics.CONTROL_AE_COMPENSATION_STEP);
        Boolean aeLock = c.get(CameraCharacteristics.CONTROL_AE_LOCK_AVAILABLE);
        Boolean awbLock = c.get(CameraCharacteristics.CONTROL_AWB_LOCK_AVAILABLE);
        float[] focalLengths = c.get(
            CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS);
        if (activeArray == null || exposureRange == null || sensitivityRange == null
                || aeCompensationRange == null || aeCompensationStep == null
                || !hasFocalLengths(focalLengths)) {
            throw new IllegalStateException("required_characteristic_missing");
        }
        aeLockAvailable = Boolean.TRUE.equals(aeLock);
        awbLockAvailable = Boolean.TRUE.equals(awbLock);
        highlightCompensationUnits = aeCompensationRange.getLower();
        if (highlightCompensationUnits >= 0
                || aeCompensationStep.doubleValue() <= 0.0) {
            throw new IllegalStateException("negative_ae_compensation_missing");
        }
        selectedFocalLength = closestFocalLength(focalLengths, PREFERRED_FOCAL_LENGTH);
        line("camera_id=" + selectedCameraId);
        line("hardware_level=" + value(level));
        line("capabilities=" + Arrays.toString(capabilities));
        line("active_array=" + activeArray.flattenToString());
        line("available_focal_lengths=" + Arrays.toString(focalLengths));
        line("selected_focal_length=" + selectedFocalLength);
        line("sensor_exposure_range_ns=" + exposureRange);
        line("sensor_sensitivity_range=" + sensitivityRange);
        line("ae_lock_available=" + yesNo(aeLockAvailable));
        line("awb_lock_available=" + yesNo(awbLockAvailable));
        line("ae_compensation_range=" + aeCompensationRange);
        line("ae_compensation_step_ev=" + decimal(aeCompensationStep.doubleValue()));
        line("highlight_compensation_units=" + highlightCompensationUnits);
        line("highlight_compensation_ev=" + decimal(
            highlightCompensationUnits * aeCompensationStep.doubleValue()));
    }

    private void configureStreams(CameraCharacteristics c) {
        StreamConfigurationMap map = c.get(
            CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
        if (map == null) throw new IllegalStateException("stream_map_missing");
        Size previewSize = choosePreviewSize(map.getOutputSizes(SurfaceTexture.class));
        Size yuvSize = chooseMeasurementSize(map.getOutputSizes(ImageFormat.YUV_420_888));
        SurfaceTexture texture = preview.getSurfaceTexture();
        if (texture == null) throw new IllegalStateException("surface_texture_missing");
        texture.setDefaultBufferSize(previewSize.getWidth(), previewSize.getHeight());
        previewSurface = new Surface(texture);
        yuvReader = ImageReader.newInstance(yuvSize.getWidth(), yuvSize.getHeight(),
            ImageFormat.YUV_420_888, 3);
        yuvReader.setOnImageAvailableListener(yuvListener, cameraHandler);
        line("preview_size=" + previewSize);
        line("measurement_format=YUV_420_888");
        line("measurement_yuv_size=" + yuvSize);
        line("measurement_sample_step=" + LUMA_SAMPLE_STEP);
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
            previewBuilder.addTarget(yuvReader.getSurface());
            applyAutoPreviewSettings();
            List<Surface> surfaces = new ArrayList<Surface>();
            surfaces.add(previewSurface);
            surfaces.add(yuvReader.getSurface());
            cameraDevice.createCaptureSession(surfaces, sessionCallback, cameraHandler);
            line("session_surface_count=2");
        } catch (Throwable error) {
            fail("session_create_exception_" + safe(error));
        }
    }

    private void applyAutoPreviewSettings() {
        previewBuilder.set(CaptureRequest.CONTROL_MODE,
            CaptureRequest.CONTROL_MODE_AUTO);
        previewBuilder.set(CaptureRequest.CONTROL_AE_MODE,
            CaptureRequest.CONTROL_AE_MODE_ON);
        previewBuilder.set(CaptureRequest.CONTROL_AE_REGIONS,
            new MeteringRectangle[] {centerRoi(activeArray)});
        previewBuilder.set(CaptureRequest.CONTROL_AE_EXPOSURE_COMPENSATION,
            Integer.valueOf(0));
        previewBuilder.set(CaptureRequest.CONTROL_AF_MODE,
            CaptureRequest.CONTROL_AF_MODE_AUTO);
        previewBuilder.set(CaptureRequest.CONTROL_AF_TRIGGER,
            CaptureRequest.CONTROL_AF_TRIGGER_IDLE);
        previewBuilder.set(CaptureRequest.CONTROL_AWB_MODE,
            CaptureRequest.CONTROL_AWB_MODE_AUTO);
        previewBuilder.set(CaptureRequest.LENS_FOCAL_LENGTH, selectedFocalLength);
    }

    private final CameraCaptureSession.StateCallback sessionCallback =
            new CameraCaptureSession.StateCallback() {
        @Override public void onConfigured(CameraCaptureSession session) {
            if (!running) { session.close(); return; }
            captureSession = session;
            try {
                captureSession.setRepeatingRequest(previewBuilder.build(),
                    previewCallback, cameraHandler);
                previewReady = true;
                line("preview_ready=yes");
                line("metering_roi=" + centerRoi(activeArray).getRect().flattenToString());
                line("phase=preview_ae");
            } catch (Throwable error) {
                fail("preview_request_exception_" + safe(error));
            }
        }
        @Override public void onConfigureFailed(CameraCaptureSession session) {
            fail("session_configuration_failed");
        }
    };

    private final CameraCaptureSession.CaptureCallback previewCallback =
            new CameraCaptureSession.CaptureCallback() {
        @Override public void onCaptureCompleted(CameraCaptureSession session,
                CaptureRequest request, TotalCaptureResult result) {
            if (!running) return;
            Long exposure = result.get(CaptureResult.SENSOR_EXPOSURE_TIME);
            Integer sensitivity = result.get(CaptureResult.SENSOR_SENSITIVITY);
            Integer aeState = result.get(CaptureResult.CONTROL_AE_STATE);
            if (exposure != null) latestAeExposureNs = exposure;
            if (sensitivity != null) latestAeSensitivity = sensitivity;
            if (aeState != null) latestAeState = aeState;
            if (measuring && measurementPhase == PHASE_SHADOW_COLLECT) {
                if (exposure != null) {
                    shadowExposureMinNs = Math.min(shadowExposureMinNs, exposure);
                    shadowExposureMaxNs = Math.max(shadowExposureMaxNs, exposure);
                }
                if (sensitivity != null) {
                    shadowSensitivityMin = Math.min(shadowSensitivityMin, sensitivity);
                    shadowSensitivityMax = Math.max(shadowSensitivityMax, sensitivity);
                }
            } else if (measuring && measurementPhase == PHASE_HIGHLIGHT_COLLECT) {
                if (exposure != null) {
                    highlightExposureMinNs = Math.min(
                        highlightExposureMinNs, exposure);
                    highlightExposureMaxNs = Math.max(
                        highlightExposureMaxNs, exposure);
                }
                if (sensitivity != null) {
                    highlightSensitivityMin = Math.min(
                        highlightSensitivityMin, sensitivity);
                    highlightSensitivityMax = Math.max(
                        highlightSensitivityMax, sensitivity);
                }
            }
            boolean converged = aeState != null
                && (aeState == CaptureResult.CONTROL_AE_STATE_CONVERGED
                    || aeState == CaptureResult.CONTROL_AE_STATE_LOCKED
                    || aeState == CaptureResult.CONTROL_AE_STATE_FLASH_REQUIRED);
            if (!measuring && !aeReady && converged && latestAeExposureNs > 0L
                    && latestAeSensitivity > 0) {
                aeReady = true;
                line("ae_ready=yes");
                line("phase=framing_ready");
                runOnUiThread(new Runnable() {
                    @Override public void run() { measureButton.setEnabled(true); }
                });
            } else if (measuring && measurementPhase == PHASE_HIGHLIGHT_WAIT_AE
                    && converged && exposure != null && sensitivity != null) {
                Integer requestCompensation = request.get(
                    CaptureRequest.CONTROL_AE_EXPOSURE_COMPENSATION);
                long candidateEquivalent = HdrMath.iso100Equivalent(
                    exposure, sensitivity);
                if (requestCompensation != null
                        && requestCompensation == highlightCompensationUnits
                        && candidateEquivalent < shadowIso100EquivalentNs * 0.60) {
                    lockAndCollectHighlights(exposure, sensitivity,
                        candidateEquivalent);
                }
            }
        }

        @Override public void onCaptureFailed(CameraCaptureSession session,
                CaptureRequest request,
                android.hardware.camera2.CaptureFailure failure) {
            if (running) fail("preview_capture_failed_" + failure.getReason());
        }
    };

    private void startYuvMeasurement() {
        if (!running || !previewReady || !aeReady || measuring
                || captureSession == null || cameraHandler == null) return;
        measureButton.setEnabled(false);
        previewButton.setEnabled(false);
        cameraHandler.post(new Runnable() {
            @Override public void run() { beginYuvMeasurement(); }
        });
    }

    private void beginYuvMeasurement() {
        try {
            shadowAnchorExposureNs = latestAeExposureNs;
            shadowAnchorSensitivity = latestAeSensitivity;
            if (shadowAnchorExposureNs <= 0L || shadowAnchorSensitivity <= 0) {
                throw new IllegalStateException("ae_anchor_missing");
            }
            shadowIso100EquivalentNs = HdrMath.iso100Equivalent(
                shadowAnchorExposureNs, shadowAnchorSensitivity);
            shadowExposureMinNs = Long.MAX_VALUE;
            shadowExposureMaxNs = -1L;
            shadowSensitivityMin = Integer.MAX_VALUE;
            shadowSensitivityMax = -1;
            settleFramesRemaining = SETTLE_FRAME_COUNT;
            shadowAccumulator = null;
            highlightAccumulator = null;
            measuring = true;
            measurementPhase = PHASE_SHADOW_SETTLE;
            if (aeLockAvailable) {
                previewBuilder.set(CaptureRequest.CONTROL_AE_LOCK, Boolean.TRUE);
            }
            if (awbLockAvailable) {
                previewBuilder.set(CaptureRequest.CONTROL_AWB_LOCK, Boolean.TRUE);
            }
            captureSession.setRepeatingRequest(previewBuilder.build(),
                previewCallback, cameraHandler);
            line("phase=shadow_yuv_temporal_measurement");
            line("shadow_ae_anchor_state=" + latestAeState);
            line("shadow_ae_anchor_exposure_ns=" + shadowAnchorExposureNs);
            line("shadow_ae_anchor_sensitivity=" + shadowAnchorSensitivity);
            line("shadow_ae_iso100_equivalent_ns=" + shadowIso100EquivalentNs);
            line("ae_lock_requested=" + yesNo(aeLockAvailable));
            line("awb_lock_requested=" + yesNo(awbLockAvailable));
            line("settle_frames=" + SETTLE_FRAME_COUNT);
            line("shadow_measurement_frames=" + MEASUREMENT_FRAME_COUNT);
            cameraHandler.postDelayed(new Runnable() {
                @Override public void run() {
                    if (running && measuring
                            && measurementPhase <= PHASE_SHADOW_COLLECT) {
                        fail("shadow_yuv_measurement_timeout");
                    }
                }
            }, MEASUREMENT_TIMEOUT_MS);
        } catch (Throwable error) {
            fail("measurement_start_exception_" + safe(error));
        }
    }

    private void startHighlightMeasurement() {
        try {
            measurementPhase = PHASE_HIGHLIGHT_WAIT_AE;
            previewBuilder.set(CaptureRequest.CONTROL_AE_EXPOSURE_COMPENSATION,
                Integer.valueOf(highlightCompensationUnits));
            if (aeLockAvailable) {
                previewBuilder.set(CaptureRequest.CONTROL_AE_LOCK, Boolean.FALSE);
            }
            captureSession.setRepeatingRequest(previewBuilder.build(),
                previewCallback, cameraHandler);
            line("phase=highlight_ae_minus_compensation");
            line("highlight_compensation_units=" + highlightCompensationUnits);
            line("highlight_compensation_ev=" + decimal(
                highlightCompensationUnits * aeCompensationStep.doubleValue()));
            cameraHandler.postDelayed(new Runnable() {
                @Override public void run() {
                    if (running && measuring
                            && measurementPhase >= PHASE_HIGHLIGHT_WAIT_AE
                            && measurementPhase <= PHASE_HIGHLIGHT_COLLECT) {
                        fail("highlight_yuv_measurement_timeout");
                    }
                }
            }, MEASUREMENT_TIMEOUT_MS);
        } catch (Throwable error) {
            fail("highlight_measurement_start_exception_" + safe(error));
        }
    }

    private void lockAndCollectHighlights(long exposureNs, int sensitivity,
            long equivalentNs) {
        if (measurementPhase != PHASE_HIGHLIGHT_WAIT_AE) return;
        try {
            highlightAnchorExposureNs = exposureNs;
            highlightAnchorSensitivity = sensitivity;
            highlightIso100EquivalentNs = equivalentNs;
            highlightExposureMinNs = Long.MAX_VALUE;
            highlightExposureMaxNs = -1L;
            highlightSensitivityMin = Integer.MAX_VALUE;
            highlightSensitivityMax = -1;
            settleFramesRemaining = SETTLE_FRAME_COUNT;
            highlightAccumulator = null;
            if (aeLockAvailable) {
                previewBuilder.set(CaptureRequest.CONTROL_AE_LOCK, Boolean.TRUE);
            }
            captureSession.setRepeatingRequest(previewBuilder.build(),
                previewCallback, cameraHandler);
            measurementPhase = PHASE_HIGHLIGHT_SETTLE;
            line("highlight_ae_anchor_exposure_ns=" + highlightAnchorExposureNs);
            line("highlight_ae_anchor_sensitivity=" + highlightAnchorSensitivity);
            line("highlight_ae_iso100_equivalent_ns=" + highlightIso100EquivalentNs);
            line("highlight_settle_frames=" + SETTLE_FRAME_COUNT);
            line("highlight_measurement_frames=" + HIGHLIGHT_FRAME_COUNT);
            line("phase=highlight_yuv_measurement");
        } catch (Throwable error) {
            fail("highlight_lock_exception_" + safe(error));
        }
    }

    private final ImageReader.OnImageAvailableListener yuvListener =
            new ImageReader.OnImageAvailableListener() {
        @Override public void onImageAvailable(ImageReader reader) {
            Image image = null;
            try {
                image = reader.acquireLatestImage();
                if (image == null) return;
                if (!running || !measuring || measurementPhase == PHASE_ANALYZING)
                    return;
                if (measurementPhase == PHASE_HIGHLIGHT_WAIT_AE) return;
                if (measurementPhase == PHASE_SHADOW_SETTLE
                        || measurementPhase == PHASE_HIGHLIGHT_SETTLE) {
                    settleFramesRemaining--;
                    if (settleFramesRemaining <= 0) {
                        if (measurementPhase == PHASE_SHADOW_SETTLE) {
                            shadowExposureMinNs = Long.MAX_VALUE;
                            shadowExposureMaxNs = -1L;
                            shadowSensitivityMin = Integer.MAX_VALUE;
                            shadowSensitivityMax = -1;
                            measurementPhase = PHASE_SHADOW_COLLECT;
                        } else {
                            highlightExposureMinNs = Long.MAX_VALUE;
                            highlightExposureMaxNs = -1L;
                            highlightSensitivityMin = Integer.MAX_VALUE;
                            highlightSensitivityMax = -1;
                            measurementPhase = PHASE_HIGHLIGHT_COLLECT;
                        }
                    }
                    return;
                }
                if (measurementPhase == PHASE_SHADOW_COLLECT) {
                    recordShadowResult(latestAeExposureNs, latestAeSensitivity);
                    if (shadowAccumulator == null) {
                        shadowAccumulator = new LumaAccumulator(image, LUMA_SAMPLE_STEP);
                    }
                    shadowAccumulator.add(image);
                    if (shadowAccumulator.frames >= MEASUREMENT_FRAME_COUNT) {
                        measurementPhase = PHASE_HIGHLIGHT_WAIT_AE;
                        Handler handler = cameraHandler;
                        if (handler != null) {
                            handler.post(new Runnable() {
                                @Override public void run() {
                                    startHighlightMeasurement();
                                }
                            });
                        }
                    }
                } else if (measurementPhase == PHASE_HIGHLIGHT_COLLECT) {
                    recordHighlightResult(latestAeExposureNs, latestAeSensitivity);
                    if (highlightAccumulator == null) {
                        highlightAccumulator = new LumaAccumulator(
                            image, LUMA_SAMPLE_STEP);
                    }
                    highlightAccumulator.add(image);
                    if (highlightAccumulator.frames >= HIGHLIGHT_FRAME_COUNT) {
                        measurementPhase = PHASE_ANALYZING;
                        final LumaAccumulator completedShadow = shadowAccumulator;
                        final LumaAccumulator completedHighlight = highlightAccumulator;
                        if (completedShadow == null) {
                            throw new IllegalStateException("shadow_accumulator_missing");
                        }
                        if (completedHighlight == null) {
                            throw new IllegalStateException("highlight_accumulator_missing");
                        }
                        new Thread(new Runnable() {
                            @Override public void run() {
                                analyzeMeasurement(completedShadow,
                                    completedHighlight);
                            }
                        }, "l16-yuv-hdr-analyzer").start();
                    }
                } else if (measurementPhase != PHASE_IDLE) {
                    throw new IllegalStateException("unexpected_measurement_phase");
                }
            } catch (Throwable error) {
                fail("yuv_collection_exception_" + safe(error));
            } finally {
                if (image != null) image.close();
            }
        }
    };

    private void recordShadowResult(long exposureNs, int sensitivity) {
        if (exposureNs > 0L) {
            shadowExposureMinNs = Math.min(shadowExposureMinNs, exposureNs);
            shadowExposureMaxNs = Math.max(shadowExposureMaxNs, exposureNs);
        }
        if (sensitivity > 0) {
            shadowSensitivityMin = Math.min(shadowSensitivityMin, sensitivity);
            shadowSensitivityMax = Math.max(shadowSensitivityMax, sensitivity);
        }
    }

    private void recordHighlightResult(long exposureNs, int sensitivity) {
        if (exposureNs > 0L) {
            highlightExposureMinNs = Math.min(highlightExposureMinNs, exposureNs);
            highlightExposureMaxNs = Math.max(highlightExposureMaxNs, exposureNs);
        }
        if (sensitivity > 0) {
            highlightSensitivityMin = Math.min(highlightSensitivityMin, sensitivity);
            highlightSensitivityMax = Math.max(highlightSensitivityMax, sensitivity);
        }
    }

    private void analyzeMeasurement(LumaAccumulator completedShadow,
            LumaAccumulator completedHighlight) {
        try {
            YuvStats shadowStats = completedShadow.analyze();
            YuvStats highlightStats = completedHighlight.analyze();
            if (!running || terminal) return;
            double shadowSnrIso100 = HdrMath.snrAtIso100Equivalent(
                shadowStats.shadowTemporalSnr, shadowAnchorSensitivity);
            HdrMath.Plan plan = HdrMath.makeAdaptivePlan(
                highlightIso100EquivalentNs, highlightStats.highlightLinearFraction,
                shadowIso100EquivalentNs, shadowSnrIso100,
                exposureRange.getLower(), exposureRange.getUpper());
            writeYuvStats("shadow_phase", shadowStats);
            line("shadow_phase_exposure_min_ns=" + printableMin(
                shadowExposureMinNs));
            line("shadow_phase_exposure_max_ns=" + shadowExposureMaxNs);
            line("shadow_phase_sensitivity_min=" + printableMin(
                shadowSensitivityMin));
            line("shadow_phase_sensitivity_max=" + shadowSensitivityMax);
            writeYuvStats("highlight_phase", highlightStats);
            line("highlight_phase_exposure_min_ns=" + printableMin(
                highlightExposureMinNs));
            line("highlight_phase_exposure_max_ns=" + highlightExposureMaxNs);
            line("highlight_phase_sensitivity_min=" + printableMin(
                highlightSensitivityMin));
            line("highlight_phase_sensitivity_max=" + highlightSensitivityMax);
            line("yuv_assumed_gamma=" + decimal(HdrMath.ASSUMED_YUV_GAMMA));
            line("highlight_linear_fraction_proxy="
                + decimal(highlightStats.highlightLinearFraction));
            line("highlight_clipped_fraction="
                + decimal(highlightStats.clippedFraction));
            line("highlight_resolved_clipped_fraction_limit="
                + decimal(MAX_RESOLVED_HIGHLIGHT_CLIPPED_FRACTION));
            line("highlight_estimator_percentile=p99.9");
            boolean highlightResolved = highlightStats.clippedFraction
                <= MAX_RESOLVED_HIGHLIGHT_CLIPPED_FRACTION
                && highlightStats.p999 < highlightStats.whiteCode;
            line("highlight_p99_9_below_white=" + yesNo(
                highlightStats.p999 < highlightStats.whiteCode));
            line("highlight_p99_99_below_white_diagnostic=" + yesNo(
                highlightStats.p9999 < highlightStats.whiteCode));
            line("highlight_endpoint_resolved=" + yesNo(highlightResolved));
            line("highlight_measurement_delta_ev=" + decimal(
                exposureSpanEv(highlightIso100EquivalentNs,
                    shadowIso100EquivalentNs)));
            line("shadow_selection=yuv_mean_p1_to_p5");
            line("shadow_selected_samples=" + shadowStats.shadowSelectedCount);
            line("shadow_mean_y_code=" + decimal(shadowStats.shadowMeanCode));
            line("shadow_temporal_snr_proxy="
                + decimal(shadowStats.shadowTemporalSnr));
            line("shadow_snr_iso100_equivalent_proxy="
                + decimal(shadowSnrIso100));
            line("target_shadow_snr=" + decimal(HdrMath.TARGET_SHADOW_SNR));
            line("temporal_instability_fraction_sigma_gt_2="
                + decimal(shadowStats.temporalInstabilityFraction));
            line("highlight_target_linear_fraction="
                + decimal(HdrMath.TARGET_HIGHLIGHT_LINEAR_FRACTION));
            line("ladder_spacing=LOGARITHMIC_FOUR_BAYER_ENDPOINTS");
            line("ideal_dynamic_range_ev=" + decimal(plan.idealSpanEv));
            line("ideal_A1_exposure_ns=" + plan.idealBayerNs[0]);
            line("ideal_A3_exposure_ns=" + plan.idealBayerNs[1]);
            line("ideal_A4_exposure_ns=" + plan.idealBayerNs[2]);
            line("ideal_A5_exposure_ns=" + plan.idealBayerNs[3]);
            line("ideal_highlight_endpoint_clamped="
                + yesNo(plan.highlightEndpointClamped));
            line("ideal_shadow_endpoint_clamped="
                + yesNo(plan.shadowEndpointClamped));
            line("pilot_max_exposure_ns="
                + HdrMath.PROVEN_PILOT_MAX_EXPOSURE_NS);
            line("pilot_dynamic_range_ev=" + decimal(plan.pilotSpanEv));
            line("pilot_A1_exposure_ns=" + plan.pilotBayerNs[0]);
            line("pilot_A2_exposure_ns=" + plan.provisionalA2Ns);
            line("pilot_A3_exposure_ns=" + plan.pilotBayerNs[1]);
            line("pilot_A4_exposure_ns=" + plan.pilotBayerNs[2]);
            line("pilot_A5_exposure_ns=" + plan.pilotBayerNs[3]);
            line("pilot_range_clamped=" + yesNo(plan.pilotRangeClamped));
            line("A2_role=PROVISIONAL_HIGHLIGHT_SAFE_PANCHROMATIC");
            line("A2_calibration_status=NEEDS_PAN_TO_BAYER_RESPONSE_CALIBRATION");
            line("measurement_model=YUV_GAMMA_AND_TEMPORAL_SNR_PROXY");
            line("yuv_to_lcc_response_transfer=UNVERIFIED_REQUIRES_PAIRED_LRI");
            boolean shadowStable = exposureStable(shadowExposureMinNs,
                shadowExposureMaxNs, shadowSensitivityMin,
                shadowSensitivityMax);
            boolean highlightStable = exposureStable(highlightExposureMinNs,
                highlightExposureMaxNs, highlightSensitivityMin,
                highlightSensitivityMax);
            line("shadow_phase_exposure_stable=" + yesNo(shadowStable));
            line("highlight_phase_exposure_stable=" + yesNo(highlightStable));
            long[] capturePlan = new long[] {
                plan.pilotBayerNs[0], plan.provisionalA2Ns,
                plan.pilotBayerNs[1], plan.pilotBayerNs[2],
                plan.pilotBayerNs[3]
            };
            boolean rootBounded = rootValuesBoundedAndOrdered(capturePlan);
            boolean pilotUseful = plan.pilotSpanEv >= MIN_USEFUL_PILOT_SPAN_EV
                && capturePlan[4] > capturePlan[0];
            line("root_capture_min_exposure_ns=" + ROOT_MIN_EXPOSURE_NS);
            line("root_capture_max_exposure_ns="
                + HdrMath.PROVEN_PILOT_MAX_EXPOSURE_NS);
            line("root_capture_plan_bounded=" + yesNo(rootBounded));
            line("pilot_min_useful_dynamic_range_ev="
                + decimal(MIN_USEFUL_PILOT_SPAN_EV));
            line("pilot_dynamic_range_useful=" + yesNo(pilotUseful));
            boolean passed = shadowStable && highlightStable && highlightResolved
                && rootBounded && pilotUseful;
            String reason = passed ? "adaptive_yuv_hdr_plan_computed"
                : !highlightResolved
                    ? "highlight_still_clipped_at_min_ae_compensation"
                    : !rootBounded
                        ? "adaptive_plan_outside_bounded_root_capture_range"
                        : !pilotUseful
                            ? "pilot_hdr_ladder_collapsed_by_20ms_cap"
                        : "adaptive_plan_computed_with_unstable_exposure";
            if (passed) {
                armMeasuredCapture(capturePlan);
            } else {
                line("root_capture_plan_status=REFUSED_NOT_EXECUTED");
                finishProbe("PARTIAL", reason);
            }
        } catch (Throwable error) {
            fail("yuv_analysis_exception_" + safe(error));
        }
    }

    private void writeYuvStats(String prefix, YuvStats stats) {
        line(prefix + "_yuv_dimensions=" + stats.width + "x" + stats.height);
        line(prefix + "_yuv_sample_step=" + stats.sampleStep);
        line(prefix + "_yuv_sample_count=" + stats.sampleCount);
        line(prefix + "_yuv_collected_frames=" + stats.frameCount);
        line(prefix + "_yuv_first_timestamp_ns=" + stats.firstTimestampNs);
        line(prefix + "_yuv_last_timestamp_ns=" + stats.lastTimestampNs);
        line(prefix + "_yuv_range_assumption=" + stats.rangeAssumption);
        line(prefix + "_yuv_black_code=" + stats.blackCode);
        line(prefix + "_yuv_white_code=" + stats.whiteCode);
        line(prefix + "_yuv_p0_1=" + stats.p001);
        line(prefix + "_yuv_p1=" + stats.p01);
        line(prefix + "_yuv_p5=" + stats.p05);
        line(prefix + "_yuv_p50=" + stats.p50);
        line(prefix + "_yuv_p99_9=" + stats.p999);
        line(prefix + "_yuv_p99_99=" + stats.p9999);
        line(prefix + "_yuv_highlight_normalized_code="
            + decimal(stats.highlightNormalizedCode));
        line(prefix + "_yuv_clipped_fraction="
            + decimal(stats.clippedFraction));
    }

    private static boolean exposureStable(long minimumNs, long maximumNs,
            int minimumSensitivity, int maximumSensitivity) {
        return minimumNs > 0L && maximumNs >= minimumNs
            && minimumSensitivity > 0 && maximumSensitivity == minimumSensitivity
            && maximumNs <= Math.round(minimumNs * 1.03);
    }

    private static double exposureSpanEv(long shortNs, long longNs) {
        if (shortNs <= 0L || longNs < shortNs) return 0.0;
        return Math.log(longNs / (double) shortNs) / Math.log(2.0);
    }

    private static boolean rootValuesBoundedAndOrdered(long[] values) {
        if (values == null || values.length != 5 || values[1] != values[0]) {
            return false;
        }
        for (long value : values) {
            if (value < ROOT_MIN_EXPOSURE_NS
                    || value > HdrMath.PROVEN_PILOT_MAX_EXPOSURE_NS) {
                return false;
            }
        }
        return values[2] >= values[0] && values[3] >= values[2]
            && values[4] >= values[3];
    }

    private static boolean validRootCapturePlan(long[] values) {
        return rootValuesBoundedAndOrdered(values) && values[4] > values[0]
            && exposureSpanEv(values[0], values[4])
                >= MIN_USEFUL_PILOT_SPAN_EV;
    }

    private synchronized void armMeasuredCapture(long[] values) throws Exception {
        if (terminal || !running || !validRootCapturePlan(values)) {
            throw new IllegalStateException("cannot_arm_invalid_or_terminal_plan");
        }
        String planText = PLAN_VERSION + " " + values[0] + " " + values[1]
            + " " + values[2] + " " + values[3] + " " + values[4] + "\n";
        writePrivateFile(privateFile(PLAN_NAME),
            planText.getBytes(StandardCharsets.US_ASCII));
        pendingCapturePlan = values.clone();
        capturePlanDeadlineMs = SystemClock.elapsedRealtime()
            + CAPTURE_PLAN_WINDOW_MS;
        terminal = true;
        running = false;
        measuring = false;
        closeCameraResources();
        line("capture_plan_file=" + privateFile(PLAN_NAME).getAbsolutePath());
        line("capture_plan_valid_for_seconds=60");
        line("root_capture_plan_status=ARMED_NOT_YET_EXECUTED");
        line("reason=adaptive_yuv_hdr_plan_computed_and_armed");
        line("camera_closed=yes");
        line("raw_still_requested=no");
        line("root_or_lcc_invoked=no_at_measurement_stage");
        line("probe=PASS");
        runOnUiThread(new Runnable() {
            @Override public void run() {
                previewButton.setEnabled(true);
                previewButton.setText("MESSUNG VERWERFEN & PREVIEW NEU STARTEN");
                measureButton.setEnabled(false);
                captureButton.setEnabled(true);
            }
        });
    }

    private void startRootCapture() {
        long[] values = pendingCapturePlan;
        if (values == null || !validRootCapturePlan(values)
                || privateFile(SPENT_NAME).exists()) {
            captureButton.setEnabled(false);
            line("root_capture_launch=REFUSED_INVALID_OR_SPENT_STATE");
            return;
        }
        if (SystemClock.elapsedRealtime() > capturePlanDeadlineMs) {
            pendingCapturePlan = null;
            deleteQuietly(privateFile(PLAN_NAME));
            captureButton.setEnabled(false);
            line("root_capture_launch=REFUSED_PLAN_EXPIRED");
            line("action=repeat_preview_and_measurement");
            return;
        }
        try {
            writePrivateFile(privateFile(UI_LAUNCH_ARM_NAME),
                (UI_LAUNCH_ARM_VALUE + "\n").getBytes(StandardCharsets.US_ASCII));
            previewButton.setEnabled(false);
            measureButton.setEnabled(false);
            captureButton.setEnabled(false);
            line("root_capture_launch=REQUESTED_ONCE");
            line("root_capture_ui=opening_private_capture_activity");
            Intent intent = new Intent(this, CaptureActivity.class);
            startActivity(intent);
        } catch (Throwable error) {
            deleteQuietly(privateFile(UI_LAUNCH_ARM_NAME));
            captureButton.setEnabled(true);
            line("root_capture_launch=ERROR_" + safe(error));
        }
    }

    private synchronized void finishProbe(final String status, final String reason) {
        if (terminal) return;
        terminal = true;
        running = false;
        measuring = false;
        closeCameraResources();
        line("reason=" + reason);
        line("camera_closed=yes");
        line("raw_still_requested=no");
        line("root_or_lcc_invoked=no");
        line("probe=" + status);
        runOnUiThread(new Runnable() {
            @Override public void run() {
                previewButton.setEnabled(true);
                previewButton.setText("PREVIEW ERNEUT STARTEN");
                measureButton.setEnabled(false);
                captureButton.setEnabled(false);
            }
        });
    }

    private void fail(String reason) {
        finishProbe("FAIL", reason);
    }

    private synchronized void closeCameraResources() {
        try { if (captureSession != null) captureSession.close(); }
        catch (Throwable ignored) {}
        captureSession = null;
        try { if (cameraDevice != null) cameraDevice.close(); }
        catch (Throwable ignored) {}
        cameraDevice = null;
        try { if (yuvReader != null) yuvReader.close(); }
        catch (Throwable ignored) {}
        yuvReader = null;
        try { if (previewSurface != null) previewSurface.release(); }
        catch (Throwable ignored) {}
        previewSurface = null;
        if (cameraThread != null) {
            cameraThread.quitSafely();
            cameraThread = null;
            cameraHandler = null;
        }
    }

    private void resetReport(String text) {
        synchronized (reportLock) {
            report.setLength(0);
            report.append(text);
        }
        publishReport();
    }

    private void line(String value) {
        synchronized (reportLock) { report.append(value).append('\n'); }
        publishReport();
    }

    private void publishReport() {
        final String snapshot;
        synchronized (reportLock) { snapshot = report.toString(); }
        runOnUiThread(new Runnable() {
            @Override public void run() {
                output.setText(snapshot);
                persistDisplayedReport(snapshot);
            }
        });
    }

    private File reportFile() {
        File directory = getExternalFilesDir(null);
        return directory == null ? null : new File(directory, REPORT_NAME);
    }

    private File captureReportFile() {
        File directory = getExternalFilesDir(null);
        return directory == null ? null : new File(directory, CAPTURE_REPORT_NAME);
    }

    private void persistRecoveryCaptureReport(String text) {
        File file = captureReportFile();
        if (file == null) return;
        try {
            FileOutputStream stream = new FileOutputStream(file, false);
            try {
                stream.write(text.getBytes(StandardCharsets.US_ASCII));
                stream.getFD().sync();
            } finally {
                stream.close();
            }
        } catch (Throwable ignored) {
            // Recovery display remains useful even if the external copy fails.
        }
    }

    private static String readBoundedAscii(File file) throws Exception {
        if (file.length() > MAX_RECOVERY_RESULT_SIZE) {
            throw new IllegalStateException("supervisor_result_too_large");
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

    private File privateFile(String name) {
        return new File(getFilesDir(), name);
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
            throw new IllegalStateException("cannot_restrict_private_file_mode");
        }
    }

    private static void deleteQuietly(File file) {
        try {
            if (file.exists()) file.delete();
        } catch (Throwable ignored) {
            // A new measurement refuses or overwrites only its fixed files.
        }
    }

    private void persistDisplayedReport(String text) {
        File file = reportFile();
        if (file == null) return;
        try {
            FileOutputStream stream = new FileOutputStream(file, false);
            try {
                stream.write(text.getBytes(StandardCharsets.UTF_8));
                stream.getFD().sync();
            } finally {
                stream.close();
            }
        } catch (Throwable ignored) {
            // Diagnostics must never influence Camera2 lifecycle handling.
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

    private static boolean hasSizes(Size[] sizes) {
        return sizes != null && sizes.length > 0;
    }

    private static boolean hasFocalLengths(float[] values) {
        return values != null && values.length > 0;
    }

    private static float closestFocalLength(float[] values, float preferred) {
        float best = values[0];
        for (float value : values) {
            if (Math.abs(value - preferred) < Math.abs(best - preferred)) best = value;
        }
        return best;
    }

    private static Size choosePreviewSize(Size[] sizes) {
        if (!hasSizes(sizes)) throw new IllegalStateException("preview_size_missing");
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

    private static Size chooseMeasurementSize(Size[] sizes) {
        if (!hasSizes(sizes)) throw new IllegalStateException("yuv_size_missing");
        for (Size size : sizes) {
            if (size.getWidth() == 640 && size.getHeight() == 480) return size;
        }
        Size best = sizes[0];
        long targetArea = 640L * 480L;
        long bestDistance = Long.MAX_VALUE;
        for (Size size : sizes) {
            long area = (long) size.getWidth() * size.getHeight();
            long distance = Math.abs(area - targetArea);
            if (distance < bestDistance) {
                best = size;
                bestDistance = distance;
            }
        }
        return best;
    }

    private static String printableMin(long value) {
        return value == Long.MAX_VALUE ? "unavailable" : Long.toString(value);
    }

    private static String printableMin(int value) {
        return value == Integer.MAX_VALUE ? "unavailable" : Integer.toString(value);
    }

    private static String value(Object value) {
        return value == null ? "unknown" : value.toString();
    }

    private static String decimal(double value) {
        return String.format(Locale.US, "%.8f", value);
    }

    private static String yesNo(boolean value) {
        return value ? "yes" : "no";
    }

    private static String safe(Throwable error) {
        String name = error.getClass().getSimpleName();
        String message = error.getMessage();
        if (message == null || message.isEmpty()) return name;
        return (name + "_" + message).replaceAll("[^A-Za-z0-9_.-]+", "_");
    }
}
