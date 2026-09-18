#pragma once
#include "campaign_helper.h"
#include <random>

#include <iostream>
#include <getopt.h>
#include <cstring>
#include <cmath>
#include <stdexcept>
#include <algorithm>
#include <vector>
#include <stdexcept>
#include <random>
#include <utility>
#include <stdexcept>
#include <complex>
#include <cctype>

struct RelativeErrorThresholds {
    double zero_eps   = 1e-15; // qué consideramos "golden = 0"
    double degraded   = 1e-2;  // 1%
    double corrupted  = 1e-1;  // 10%
    double failed     = 10.0;  // ×10
};
struct SlotErrorStats {
    uint64_t failed     = 0;
    uint64_t corrupted  = 0;
    uint64_t degraded   = 0;
    uint64_t correct    = 0;

    uint64_t total() const {
        return failed + corrupted + degraded + correct;
    }
};
struct CKKSAccuracyMetrics {
    double l2_abs_error;     // ||y - g||₂ / ||g||₂
    double l2_rel_error;     // ||y - g||₂ / ||g||₂
    double linf_rel_error;   // max_i |y_i - g_i| / |g_i|   (g_i != 0)
    double linf_abs_error;   // max_i |y_i - g_i|
    double bits_precision;   // -log2(l2_rel_error)
};

struct ErrorThresholds {
    double abs_zero;        // qué se considera "cero" en golden

    double baseline_abs;    // baseline.linf_abs_error
    double baseline_rel;    // baseline.linf_rel_error

    double good;            // multiplicador (≈ 1–2)
    double bad;             // multiplicador (≈ 5)
    double fail;            // multiplicador (≈ 50)
};


CKKSAccuracyMetrics EvaluateCKKSAccuracy(
    const std::vector<double>& golden,
    const std::vector<double>& ckks,
    double zero_eps = 1e-15
);


SlotErrorStats categorize_slots_relative(
    const std::vector<double>& golden,
    const std::vector<double>& output,
    size_t size,
    const RelativeErrorThresholds& thr = {}
);


bool AcceptCKKSResult(const CKKSAccuracyMetrics& m, double max_rel_error = 1e-4,
                      double max_abs_error = 1e-4, double min_bits = 10.0);

double percentile(std::vector<double>& v, double p);



