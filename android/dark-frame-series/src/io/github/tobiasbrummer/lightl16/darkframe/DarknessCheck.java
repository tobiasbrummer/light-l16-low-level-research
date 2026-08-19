// SPDX-License-Identifier: MIT
package io.github.tobiasbrummer.lightl16.darkframe;

import android.app.Activity;
import android.graphics.ImageFormat;
import android.graphics.SurfaceTexture;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.util.Range;
import android.util.Size;
import android.view.Surface;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

/**
 * Confirms that the lens is covered before a 25-minute dark frame series.
 *
 * The measurement deliberately forces the worst case for darkness instead of
 * letting auto-exposure choose: AE off, the highest sensitivity the device
 * reports, and a 100 ms integration.  If the scene is still dark under maximum
 * amplification, the lens is covered.
 *
 * This only sees the module Camera2 exposes, not all sixteen, so it catches a
 * forgotten cover rather than proving every module is dark.
 */
public final class DarknessCheck {

    public interface Callback {
        void onResult(boolean dark, String report);
    }

    // Calibrated on the device on 2026-08-18: a fully covered lens reads a
    // mean luma of 54 to 60 at these settings, while a dimly lit evening room
    // already reads 134.  That 134 is a lower bound for "uncovered", since a
    // brighter room only moves it further from this limit.
    //
    // The first version used 24 and 64, both below the covered reading, so no
    // amount of covering could pass.  At ISO 12800 the sensor's own noise
    // floor occupies the lower half of the 8-bit range after gamma, which is
    // why these limits look high for a "darkness" test.
    private static final int DARK_MEAN_MAX_LUMA = 90;

    // Judged against the mean rather than as an absolute level: the mean
    // already answers "how bright is the frame", so what p99.9 adds is
    // "is there one bright patch in an otherwise dark frame".  A covered lens
    // measured a spread of about 31.
    private static final int DARK_SPREAD_MAX_LUMA = 60;
    private static final int REQUIRED_FRAMES = 8;
    private static final long PROBE_EXPOSURE_NS = 100000000L;
    private static final long OVERALL_TIMEOUT_MS = 20000L;
    private static final int LUMA_SAMPLE_STEP = 4;

    private static volatile boolean cameraOpen;

    private final StringBuilder report = new StringBuilder();
    private final int[] histogram = new int[256];

    private HandlerThread cameraThread;
    private Handler cameraHandler;
    private CameraDevice cameraDevice;
    private CameraCaptureSession captureSession;
    private ImageReader yuvReader;
    private SurfaceTexture dummyTexture;
    private Surface dummySurface;
    private Callback callback;
    private long sampleCount;
    private long lumaSum;
    private int frames;
    private boolean finished;

    /** True when no CameraDevice or ImageReader reference is held. */
    public static boolean isClosed() {
        return !cameraOpen;
    }

    public void start(Activity activity, Callback resultCallback) {
        callback = resultCallback;
        cameraThread = new HandlerThread("l16-darkness-check");
        cameraThread.start();
        cameraHandler = new Handler(cameraThread.getLooper());
        cameraOpen = true;

        try {
            CameraManager manager =
                (CameraManager) activity.getSystemService(Activity.CAMERA_SERVICE);
            String id = chooseCamera(manager);
            CameraCharacteristics characteristics =
                manager.getCameraCharacteristics(id);
            configure(characteristics);
            line("camera_id=" + id);
            manager.openCamera(id, deviceCallback, cameraHandler);
            armTimeout();
        } catch (Throwable error) {
            finish(false, "open_exception_" + safe(error));
        }
    }

    /** Releases every camera resource.  Safe to call more than once. */
    public void close() {
        try {
            if (captureSession != null) {
                captureSession.close();
                captureSession = null;
            }
        } catch (Throwable ignored) {
            // Closing must not throw; the caller checks isClosed() afterwards.
        }
        try {
            if (cameraDevice != null) {
                cameraDevice.close();
                cameraDevice = null;
            }
        } catch (Throwable ignored) {
            // See above.
        }
        try {
            if (yuvReader != null) {
                yuvReader.close();
                yuvReader = null;
            }
        } catch (Throwable ignored) {
            // See above.
        }
        if (dummySurface != null) {
            dummySurface.release();
            dummySurface = null;
        }
        if (dummyTexture != null) {
            dummyTexture.release();
            dummyTexture = null;
        }
        if (cameraThread != null) {
            cameraThread.quitSafely();
            cameraThread = null;
            cameraHandler = null;
        }
        cameraOpen = false;
    }

    private String chooseCamera(CameraManager manager) throws CameraAccessException {
        String[] ids = manager.getCameraIdList();
        for (String id : ids) {
            StreamConfigurationMap map = manager.getCameraCharacteristics(id)
                .get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            if (map != null
                    && map.getOutputSizes(ImageFormat.YUV_420_888) != null
                    && map.getOutputSizes(ImageFormat.YUV_420_888).length > 0) {
                return id;
            }
        }
        throw new IllegalStateException("no_yuv_camera");
    }

    private Range<Integer> sensitivityRange;
    private Range<Long> exposureRange;

    private void configure(CameraCharacteristics characteristics) {
        StreamConfigurationMap map = characteristics.get(
            CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
        if (map == null) {
            throw new IllegalStateException("stream_map_missing");
        }
        sensitivityRange = characteristics.get(
            CameraCharacteristics.SENSOR_INFO_SENSITIVITY_RANGE);
        exposureRange = characteristics.get(
            CameraCharacteristics.SENSOR_INFO_EXPOSURE_TIME_RANGE);
        if (sensitivityRange == null || exposureRange == null) {
            throw new IllegalStateException("manual_exposure_unsupported");
        }
        Size size = smallest(map.getOutputSizes(ImageFormat.YUV_420_888));
        yuvReader = ImageReader.newInstance(
            size.getWidth(), size.getHeight(), ImageFormat.YUV_420_888, 3);
        yuvReader.setOnImageAvailableListener(imageListener, cameraHandler);

        // A dummy texture keeps the session at two surfaces.  A reader-only
        // configuration is rejected by some HALs on this API level.
        dummyTexture = new SurfaceTexture(0);
        dummyTexture.setDefaultBufferSize(size.getWidth(), size.getHeight());
        dummySurface = new Surface(dummyTexture);
        line("measurement_yuv_size=" + size);
        line("sensor_sensitivity_range=" + sensitivityRange);
        line("sensor_exposure_range_ns=" + exposureRange);
    }

    private static Size smallest(Size[] sizes) {
        if (sizes == null || sizes.length == 0) {
            throw new IllegalStateException("no_yuv_sizes");
        }
        Size best = sizes[0];
        for (Size size : sizes) {
            if ((long) size.getWidth() * size.getHeight()
                    < (long) best.getWidth() * best.getHeight()) {
                best = size;
            }
        }
        return best;
    }

    private final CameraDevice.StateCallback deviceCallback =
            new CameraDevice.StateCallback() {
        @Override public void onOpened(CameraDevice camera) {
            cameraDevice = camera;
            createSession();
        }

        @Override public void onDisconnected(CameraDevice camera) {
            finish(false, "camera_disconnected");
        }

        @Override public void onError(CameraDevice camera, int error) {
            finish(false, "camera_error_" + error);
        }
    };

    private void createSession() {
        try {
            List<Surface> surfaces = new ArrayList<Surface>();
            surfaces.add(dummySurface);
            surfaces.add(yuvReader.getSurface());
            cameraDevice.createCaptureSession(surfaces, sessionCallback, cameraHandler);
        } catch (Throwable error) {
            finish(false, "session_exception_" + safe(error));
        }
    }

    private final CameraCaptureSession.StateCallback sessionCallback =
            new CameraCaptureSession.StateCallback() {
        @Override public void onConfigured(CameraCaptureSession session) {
            captureSession = session;
            try {
                CaptureRequest.Builder builder = cameraDevice.createCaptureRequest(
                    CameraDevice.TEMPLATE_PREVIEW);
                builder.addTarget(dummySurface);
                builder.addTarget(yuvReader.getSurface());
                builder.set(CaptureRequest.CONTROL_AE_MODE,
                    CaptureRequest.CONTROL_AE_MODE_OFF);
                builder.set(CaptureRequest.CONTROL_AWB_MODE,
                    CaptureRequest.CONTROL_AWB_MODE_OFF);
                builder.set(CaptureRequest.CONTROL_AF_MODE,
                    CaptureRequest.CONTROL_AF_MODE_OFF);
                int sensitivity = sensitivityRange.getUpper();
                long exposure = PROBE_EXPOSURE_NS;
                if (exposure > exposureRange.getUpper()) {
                    exposure = exposureRange.getUpper();
                }
                if (exposure < exposureRange.getLower()) {
                    exposure = exposureRange.getLower();
                }
                builder.set(CaptureRequest.SENSOR_SENSITIVITY, sensitivity);
                builder.set(CaptureRequest.SENSOR_EXPOSURE_TIME, exposure);
                line("probe_sensitivity=" + sensitivity);
                line("probe_exposure_ns=" + exposure);
                session.setRepeatingRequest(builder.build(), null, cameraHandler);
            } catch (Throwable error) {
                finish(false, "request_exception_" + safe(error));
            }
        }

        @Override public void onConfigureFailed(CameraCaptureSession session) {
            finish(false, "session_configure_failed");
        }
    };

    private final ImageReader.OnImageAvailableListener imageListener =
            new ImageReader.OnImageAvailableListener() {
        @Override public void onImageAvailable(ImageReader reader) {
            Image image = null;
            try {
                image = reader.acquireLatestImage();
                if (image == null || finished) {
                    return;
                }
                accumulate(image);
                if (frames >= REQUIRED_FRAMES) {
                    evaluate();
                }
            } catch (Throwable error) {
                finish(false, "frame_exception_" + safe(error));
            } finally {
                if (image != null) {
                    image.close();
                }
            }
        }
    };

    private void accumulate(Image image) {
        if (image.getFormat() != ImageFormat.YUV_420_888
                || image.getPlanes().length < 1) {
            throw new IllegalStateException("unexpected_yuv_layout");
        }
        Image.Plane plane = image.getPlanes()[0];
        int rowStride = plane.getRowStride();
        int pixelStride = plane.getPixelStride();
        if (rowStride <= 0 || pixelStride <= 0) {
            throw new IllegalStateException("invalid_yuv_stride");
        }
        ByteBuffer buffer = plane.getBuffer().duplicate();
        int base = buffer.position();
        int limit = buffer.limit();
        int width = image.getWidth();
        int height = image.getHeight();
        for (int row = 0; row < height; row += LUMA_SAMPLE_STEP) {
            int rowOffset = base + row * rowStride;
            for (int column = 0; column < width; column += LUMA_SAMPLE_STEP) {
                int offset = rowOffset + column * pixelStride;
                if (offset < base || offset >= limit) {
                    throw new IllegalStateException("yuv_buffer_too_short");
                }
                int value = buffer.get(offset) & 0xff;
                histogram[value]++;
                lumaSum += value;
                sampleCount++;
            }
        }
        frames++;
    }

    private void evaluate() {
        if (sampleCount <= 0L) {
            finish(false, "no_samples");
            return;
        }
        double mean = (double) lumaSum / (double) sampleCount;
        int p999 = percentile(0.999);
        int maximum = percentile(1.0);
        double spread = p999 - mean;
        line("frames=" + frames);
        line("samples=" + sampleCount);
        line("mean_luma=" + String.format("%.3f", mean));
        line("p999_luma=" + p999);
        line("max_luma=" + maximum);
        line("spread_luma=" + String.format("%.3f", spread));
        line("mean_luma_limit=" + DARK_MEAN_MAX_LUMA);
        line("spread_luma_limit=" + DARK_SPREAD_MAX_LUMA);
        boolean levelOk = mean <= DARK_MEAN_MAX_LUMA;
        boolean spreadOk = spread <= DARK_SPREAD_MAX_LUMA;
        String reason;
        if (levelOk && spreadOk) {
            reason = "lens_cover_confirmed";
        } else if (!levelOk && !spreadOk) {
            reason = "scene_too_bright_and_uneven";
        } else if (!levelOk) {
            reason = "scene_too_bright";
        } else {
            reason = "bright_patch_suggests_a_light_leak";
        }
        finish(levelOk && spreadOk, reason);
    }

    /** Percentile over the luma histogram; the p99.9 bound catches an edge
     *  light leak that a mean would average away. */
    private int percentile(double fraction) {
        long target = (long) Math.ceil(fraction * sampleCount);
        long seen = 0L;
        for (int value = 0; value < histogram.length; value++) {
            seen += histogram[value];
            if (seen >= target) {
                return value;
            }
        }
        return histogram.length - 1;
    }

    private void armTimeout() {
        final long deadline = SystemClock.elapsedRealtime() + OVERALL_TIMEOUT_MS;
        cameraHandler.postDelayed(new Runnable() {
            @Override public void run() {
                if (!finished && SystemClock.elapsedRealtime() >= deadline) {
                    finish(false, "measurement_timeout_after_"
                        + OVERALL_TIMEOUT_MS + "ms");
                }
            }
        }, OVERALL_TIMEOUT_MS);
    }

    /**
     * Reports exactly once.  The camera is always released first, so no path
     * can leave a Camera2 client open when the root runner is armed.
     */
    private void finish(boolean dark, String reason) {
        if (finished) {
            return;
        }
        finished = true;
        Callback target = callback;
        callback = null;
        try {
            close();
        } finally {
            line("darkness_reason=" + reason);
            line("camera2_closed=" + (isClosed() ? "yes" : "no"));
            if (target != null) {
                target.onResult(dark && isClosed(), report.toString());
            }
        }
    }

    private void line(String text) {
        report.append(text).append('\n');
    }

    private static String safe(Throwable error) {
        String name = error.getClass().getSimpleName();
        return name == null ? "Throwable" : name;
    }
}
