#pragma once
#include "campaign_helper.h"
#include "metrics.h"
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

using cdouble = std::complex<double>;
inline std::mt19937_64& rng() {
    static thread_local std::mt19937_64 gen{0};
    return gen;
}

inline void seed_rng(uint64_t seed, uint64_t run_id = 0) {
    std::seed_seq seq{ (uint32_t)seed, (uint32_t)(seed >> 32),
                       (uint32_t)run_id, (uint32_t)(run_id >> 32) };
    rng().seed(seq);
}

inline uint32_t random_int(int a, int b) {
    std::uniform_int_distribution<int> dist(a, b);
    return (uint32_t)dist(rng());
}
void printVector(const std::vector<double>& v,
                 const std::string& name = "",
                 size_t max_elems = SIZE_MAX);

void printVector(const std::vector<cdouble>& v,
                 const std::string& name = "",
                 size_t max_elems = SIZE_MAX);

template <typename T>
void printBaselineComparison(
    const CampaignArgs& args,
    const std::vector<T>& goldenOutput,
    const std::vector<T>& goldenCKKSValues,
    const CKKSAccuracyMetrics& baseline_metrics,
    bool print_elements = true
) {
    args.print(std::cerr);
    std::cout << "GoldenCKKSOutput vs output "
              << goldenOutput.size() << "\n";

    if (print_elements) {
        for (size_t i = 0; i < goldenOutput.size(); i++) {
            std::cout << goldenCKKSValues[i]
                      << ", "
                      << goldenOutput[i]
                      << std::endl;
        }
    }

    std::cout << "L2 relative error : "
              << baseline_metrics.l2_rel_error << "\n";
    std::cout << "Linf abs error   : "
              << baseline_metrics.linf_abs_error << "\n";
    std::cout << "Bits precision   : "
              << baseline_metrics.bits_precision << "\n";

    std::cerr << "Error with golden norm, checkout the used parameters"
              << std::endl;
}
// -----------------------------
// API
// -----------------------------

std::vector<uint32_t> extraBitsBetweenDeltaAndQ(const CampaignArgs& args);
// reg_bits: register width measured by the probe (0 = unknown, use logQ).
std::vector<uint32_t> bitsToFlipGenerator(const CampaignArgs& args, uint32_t reg_bits = 0);
void validateArgs(const CampaignArgs& args);
std::vector<double> uniform_dist(uint32_t batchSize, int64_t  logMin, int64_t logMax, uint64_t seed, bool verbose=false);


