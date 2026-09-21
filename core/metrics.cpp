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
        // Pasada 1: maximos e Linf. Los maximos son la escala de las normas L2.
    // Acumular diff*diff directo desborda a inf en cuanto UN slot pasa de 2^512,
    // y un flip en un bit alto de HEAAN (logQ 840, logDelta 40) llega a 2^800.
    double max_diff = 0.0, max_golden = 0.0, linf_rel_error = 0.0;

    // std::max(x, NaN) devuelve x, o sea que un NaN se perderia y el fault se loguearia
    // como error 0. Este max lo propaga.
    auto maxp = [](double a, double b) {
        return (std::isnan(a) || std::isnan(b)) ? std::numeric_limits<double>::quiet_NaN()
                                                : std::max(a, b);
    };

    for (size_t i = 0; i < golden.size(); ++i) {
        const double abs_g    = std::abs(golden[i]);
        const double abs_diff = std::abs(ckks[i] - golden[i]);

        max_diff   = maxp(max_diff, abs_diff);
        max_golden = maxp(max_golden, abs_g);

        if (abs_g > zero_eps)
            linf_rel_error = maxp(linf_rel_error, abs_diff / abs_g);
    }

    // Pasada 2: ||v||_2 = max|v| * sqrt( sum (v_i / max|v|)^2 ).
    // Cada termino cae en [0,1], asi que la suma vale a lo sumo n: no desborda nunca.
    // Si max es 0, inf o NaN se devuelve tal cual (el caso degenerado se propaga solo).
    auto scaled_norm = [&](double scale, auto component) -> double {
        if (!(scale > 0.0) || !std::isfinite(scale)) return scale;
        double acc = 0.0;
        for (size_t i = 0; i < golden.size(); ++i) {
            const double t = component(i) / scale;
            acc += t * t;
        }
        return scale * std::sqrt(acc);
    };

    const double l2_abs_error = scaled_norm(max_diff,   [&](size_t i) { return ckks[i] - golden[i]; });
    const double l2_golden    = scaled_norm(max_golden, [&](size_t i) { return golden[i]; });

    const double l2_rel_error = l2_abs_error / std::max(l2_golden, zero_eps);
    const double bits_precision = (l2_rel_error > 0.0) ? -std::log2(l2_rel_error)
                                    : std::numeric_limits<double>::infinity();
    return {
        l2_abs_error,
        l2_rel_error,
        linf_rel_error,
        max_diff,          // linf_abs_error
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

