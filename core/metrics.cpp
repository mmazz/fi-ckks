#include "metrics.h"

CKKSAccuracyMetrics EvaluateCKKSAccuracy(
    const std::vector<double>& golden,
    const std::vector<double>& ckks,
    double zero_eps
) {
    if (golden.size() != ckks.size())
        throw std::invalid_argument("EvaluateCKKSAccuracy: size mismatch");

    if (golden.empty())
        throw std::invalid_argument("EvaluateCKKSAccuracy: empty vectors");

    double l2_diff_sq   = 0.0;
    double l2_golden_sq = 0.0;

    double linf_abs_error = 0.0;
    double linf_rel_error = 0.0;

    for (size_t i = 0; i < golden.size(); ++i) {
        const double g    = golden[i];
        const double abs_g    = std::abs(g);

        const double diff = ckks[i] - g;
        const double abs_diff = std::abs(diff);

        l2_diff_sq   += diff * diff;
        l2_golden_sq += g * g;

        linf_abs_error = std::max(linf_abs_error, abs_diff);

        if (abs_g > zero_eps) {
            linf_rel_error = std::max(linf_rel_error, abs_diff / abs_g);
        }
    }

    const double denom = std::max(std::sqrt(l2_golden_sq), zero_eps);

    const double l2_abs_error =  std::sqrt(l2_diff_sq);
    const double l2_rel_error =  l2_abs_error / denom;

    const double bits_precision = (l2_rel_error > 0.0) ? -std::log2(l2_rel_error)
                                    : std::numeric_limits<double>::infinity();

    return {
        l2_abs_error,
        l2_rel_error,
        linf_rel_error,
        linf_abs_error,
        bits_precision
    };
}

SlotErrorStats categorize_slots_relative(
    const std::vector<double>& golden,
    const std::vector<double>& output,
    size_t size,
    const RelativeErrorThresholds& thr
) {
    if (golden.size() < size || output.size() < size)
        throw std::invalid_argument("categorize_slots_relative: size mismatch");

    SlotErrorStats stats;

    for (size_t i = 0; i < size; ++i) {
        const double g    = golden[i];
        const double diff = std::abs(output[i] - g);

        double rel_err;

        // -------------------------
        // Caso A: golden ≈ 0
        // -------------------------
        if (std::abs(g) < thr.zero_eps) {
            // usamos error absoluto normalizado
            rel_err = diff;
        } else {
            rel_err = diff / std::abs(g);
        }

        // -------------------------
        // Clasificación
        // -------------------------
        if (rel_err > thr.failed)
            stats.failed++;
        else if (rel_err > thr.corrupted)
            stats.corrupted++;
        else if (rel_err > thr.degraded)
            stats.degraded++;
        else
            stats.correct++;
    }

    return stats;
}

bool AcceptCKKSResult(
    const CKKSAccuracyMetrics& m,
    double max_l2_rel_error,
    double max_linf_abs_error,
    double min_bits_precision
) {
    return (m.l2_rel_error   <= max_l2_rel_error) &&
           (m.linf_abs_error <= max_linf_abs_error) &&
           (m.bits_precision >= min_bits_precision);
}


double percentile(std::vector<double>& v, double p) {
    if (v.empty()) return 0.0;
    double pos = p * (v.size() - 1);
    size_t idx = static_cast<size_t>(pos);
    double frac = pos - idx;

    if (idx + 1 < v.size())
        return v[idx] * (1.0 - frac) + v[idx + 1] * frac;
    else
        return v[idx];
}

