package io.github.tobiasbrummer.lightl16.hdrmeterprobe;

/** Pure arithmetic for the preview-derived adaptive exposure ladder. */
public final class HdrMath {
    public static final double TARGET_HIGHLIGHT_LINEAR_FRACTION = 0.70;
    public static final double TARGET_SHADOW_SNR = 8.0;
    public static final double ASSUMED_YUV_GAMMA = 2.2;
    public static final long PROVEN_PILOT_MAX_EXPOSURE_NS = 20000000L;

    public static final class Plan {
        public final long[] idealBayerNs;
        public final long[] pilotBayerNs;
        public final long provisionalA2Ns;
        public final double idealSpanEv;
        public final double pilotSpanEv;
        public final boolean highlightEndpointClamped;
        public final boolean shadowEndpointClamped;
        public final boolean pilotRangeClamped;

        Plan(long[] idealBayerNs, long[] pilotBayerNs, long provisionalA2Ns,
                double idealSpanEv, double pilotSpanEv,
                boolean highlightEndpointClamped,
                boolean shadowEndpointClamped, boolean pilotRangeClamped) {
            this.idealBayerNs = idealBayerNs;
            this.pilotBayerNs = pilotBayerNs;
            this.provisionalA2Ns = provisionalA2Ns;
            this.idealSpanEv = idealSpanEv;
            this.pilotSpanEv = pilotSpanEv;
            this.highlightEndpointClamped = highlightEndpointClamped;
            this.shadowEndpointClamped = shadowEndpointClamped;
            this.pilotRangeClamped = pilotRangeClamped;
        }
    }

    private HdrMath() {}

    public static long iso100Equivalent(long exposureNs, int sensitivity) {
        if (exposureNs <= 0L || sensitivity <= 0) {
            throw new IllegalArgumentException("invalid_ae_measurement");
        }
        return saturatingMultiply(exposureNs, sensitivity) / 100L;
    }

    public static double gammaDecode(double normalizedCode) {
        if (!finite(normalizedCode) || normalizedCode < 0.0
                || normalizedCode > 1.0) {
            throw new IllegalArgumentException("invalid_normalized_code");
        }
        return Math.pow(normalizedCode, ASSUMED_YUV_GAMMA);
    }

    public static double snrAtIso100Equivalent(double measuredSnr,
            int measuredSensitivity) {
        if (!finite(measuredSnr) || measuredSnr < 0.0
                || measuredSensitivity <= 0) {
            throw new IllegalArgumentException("invalid_snr_input");
        }
        return measuredSnr * Math.sqrt(measuredSensitivity / 100.0);
    }

    public static Plan makeAdaptivePlan(long highlightIso100EquivalentNs,
            double highlightLinearFraction, long shadowIso100EquivalentNs,
            double shadowSnrAtIso100, long sensorMinNs, long sensorMaxNs) {
        if (highlightIso100EquivalentNs <= 0L
                || shadowIso100EquivalentNs <= 0L
                || !finite(highlightLinearFraction)
                || highlightLinearFraction <= 0.0
                || !finite(shadowSnrAtIso100) || shadowSnrAtIso100 < 0.0) {
            throw new IllegalArgumentException("invalid_plan_input");
        }
        validateRange(sensorMinNs, sensorMaxNs);

        double highlightRequested = highlightIso100EquivalentNs
            * TARGET_HIGHLIGHT_LINEAR_FRACTION / highlightLinearFraction;
        long unboundedShort = boundedDoubleToLong(highlightRequested);
        // Never make the shortest role longer than the dedicated highlight
        // measurement exposure.
        unboundedShort = Math.min(unboundedShort, highlightIso100EquivalentNs);
        long shortNs = clamp(unboundedShort, sensorMinNs, sensorMaxNs);
        boolean highlightClamped = shortNs != unboundedShort;

        double shadowFactor;
        if (shadowSnrAtIso100 <= 0.0) {
            shadowFactor = Double.POSITIVE_INFINITY;
        } else {
            double ratio = TARGET_SHADOW_SNR / shadowSnrAtIso100;
            shadowFactor = Math.max(1.0, ratio * ratio);
        }
        double shadowRequested = shadowIso100EquivalentNs * shadowFactor;
        long unboundedLong = boundedDoubleToLong(shadowRequested);
        unboundedLong = Math.max(unboundedLong, shortNs);
        long longNs = clamp(unboundedLong, sensorMinNs, sensorMaxNs);
        longNs = Math.max(longNs, shortNs);
        boolean shadowClamped = longNs != unboundedLong;

        long[] ideal = logarithmicFour(shortNs, longNs);
        long pilotMax = Math.min(sensorMaxNs, PROVEN_PILOT_MAX_EXPOSURE_NS);
        pilotMax = Math.max(sensorMinNs, pilotMax);
        long[] pilot = new long[4];
        boolean pilotClamped = false;
        for (int i = 0; i < ideal.length; i++) {
            pilot[i] = Math.min(ideal[i], pilotMax);
            if (pilot[i] != ideal[i]) pilotClamped = true;
        }
        // A2 is deliberately kept at the highlight-safe endpoint until a
        // panchromatic-to-Bayer response calibration has been measured.
        long a2 = pilot[0];
        return new Plan(ideal, pilot, a2, exposureSpanEv(ideal[0], ideal[3]),
            exposureSpanEv(pilot[0], pilot[3]), highlightClamped,
            shadowClamped, pilotClamped);
    }

    public static int percentileBin(long[] histogram, long count,
            int numerator, int denominator) {
        if (histogram == null || histogram.length == 0 || count <= 0L
                || numerator <= 0 || denominator <= 0
                || numerator > denominator) {
            throw new IllegalArgumentException("invalid_percentile_input");
        }
        long target = (count * numerator + denominator - 1L) / denominator;
        long cumulative = 0L;
        for (int i = 0; i < histogram.length; i++) {
            cumulative += histogram[i];
            if (cumulative >= target) return i;
        }
        throw new IllegalArgumentException("histogram_count_mismatch");
    }

    static long[] logarithmicFour(long shortNs, long longNs) {
        if (shortNs <= 0L || longNs < shortNs) {
            throw new IllegalArgumentException("invalid_ladder_endpoints");
        }
        long[] values = new long[4];
        values[0] = shortNs;
        values[3] = longNs;
        if (shortNs == longNs) {
            values[1] = shortNs;
            values[2] = shortNs;
            return values;
        }
        double logarithmicRatio = Math.log(longNs / (double) shortNs);
        values[1] = Math.round(shortNs * Math.exp(logarithmicRatio / 3.0));
        values[2] = Math.round(shortNs * Math.exp(2.0 * logarithmicRatio / 3.0));
        values[1] = Math.max(values[0], Math.min(values[3], values[1]));
        values[2] = Math.max(values[1], Math.min(values[3], values[2]));
        return values;
    }

    static double exposureSpanEv(long shortNs, long longNs) {
        if (shortNs <= 0L || longNs < shortNs) {
            throw new IllegalArgumentException("invalid_span_endpoints");
        }
        return Math.log(longNs / (double) shortNs) / Math.log(2.0);
    }

    private static long boundedDoubleToLong(double value) {
        if (Double.isNaN(value) || value <= 1.0) return 1L;
        if (Double.isInfinite(value) || value >= Long.MAX_VALUE) {
            return Long.MAX_VALUE;
        }
        return Math.round(value);
    }

    static long clamp(long value, long minimum, long maximum) {
        validateRange(minimum, maximum);
        return Math.max(minimum, Math.min(maximum, value));
    }

    static long saturatingMultiply(long value, long factor) {
        if (value < 0L || factor < 0L) {
            throw new IllegalArgumentException("negative_multiply_input");
        }
        if (factor != 0L && value > Long.MAX_VALUE / factor) {
            return Long.MAX_VALUE;
        }
        return value * factor;
    }

    private static boolean finite(double value) {
        return !Double.isNaN(value) && !Double.isInfinite(value);
    }

    private static void validateRange(long minimum, long maximum) {
        if (minimum <= 0L || maximum < minimum) {
            throw new IllegalArgumentException("invalid_exposure_range");
        }
    }
}
