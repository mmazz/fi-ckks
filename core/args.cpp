#include "args.h"
#include "pipeline.h"
#include <cmath>
#include <algorithm>
#include <stdexcept>
#include <algorithm>

void printVector(const std::vector<double>& v,
                 const std::string& name,
                 size_t max_elems)
{
    if (!name.empty())
        std::cout << name << " (" << v.size() << "): ";

    size_t n = std::min(v.size(), max_elems);

    std::cout << "[ ";
    for (size_t i = 0; i < n; ++i) {
        std::cout << v[i];
        if (i + 1 < n) std::cout << ", ";
    }

    if (n < v.size())
        std::cout << ", ...";

    std::cout << " ]\n";
}

void printVector(const std::vector<cdouble>& v,
                 const std::string& name,
                 size_t max_elems)
{
    if (!name.empty())
        std::cout << name << " (" << v.size() << "): ";

    size_t n = std::min(v.size(), max_elems);

    std::cout << "[ ";
    for (size_t i = 0; i < n; ++i) {
        std::cout << v[i];
        if (i + 1 < n) std::cout << ", ";
    }

    if (n < v.size())
        std::cout << ", ...";

    std::cout << " ]\n";
}

void validateArgs(const CampaignArgs& args)
{
    if (args.logQ > args.bitsPerCoeff)
        throw std::invalid_argument(
            "Bits per coefficient is less than logQ"
        );

    if (args.logDelta > args.logQ)
        throw std::invalid_argument(
            "Delta is bigger than logQ"
        );

    if (args.logSlots >= args.logN)
        throw std::invalid_argument(
            "Log slots is bigger than or equal to logN"
        );
    // The plaintext model rotates by k % slots (pipeline.h); HEAAN indexes
    // context.rotGroup[k], an array of 2^(logN-1) entries, so k out of range is an
    // out-of-bounds read (segfault at k == 2^(logN-1)). Keep both in the same domain.
    const double max_rot = double(1u << args.logSlots);
    for (const Op& op : args.ops)
        if (op.type == OpType::Rot && (op.param < 1.0 || op.param >= max_rot))
            throw std::invalid_argument("pipeline: rot must be in [1, 2^logSlots) = [1, " +
                                        std::to_string(uint64_t(max_rot)) + ")");

    if (args.amountBits == 0)
        throw std::invalid_argument("amountBits must be >= 1");
    if (args.amountBits > args.bitsPerCoeff)
        throw std::invalid_argument("amountBits > bitsPerCoeff: the sweep would be empty");
}

std::vector<uint32_t> bitsToFlipGenerator(const CampaignArgs& args)
{
    std::vector<uint32_t> res;
    res.reserve(45);

    const uint32_t logQ     = args.logQ;
    const uint32_t logDelta = args.logDelta;
    const uint32_t maxBits  = args.bitsPerCoeff;
    if (maxBits == 0) return res;
    const uint32_t M = maxBits - 1;

    // [start, end] inclusivo, recortado a [0, M]. Un rango valido nunca se descarta.
    auto addRange = [&](uint32_t start, uint32_t end)
    {
        if (start > M) return;
        end = std::min(end, M);
        if (end < start) return;

        const uint32_t diff = end - start + 1;
        uint32_t count;
        if      (diff <= 2)  count = diff;       // antes se perdian los rangos de 1 y 2 bits
        else if (diff < 5)   count = diff - 1;
        else if (diff < 30)  count = 5;
        else                 count = 15;

        for (uint32_t i = 0; i < count; i++) {
            const uint32_t v = (count == 1)
                ? start
                : start + uint32_t((uint64_t)(end - start) * i / (count - 1));
            if (res.empty() || res.back() != v) res.push_back(v);
        }
    };

    uint32_t gapDelta = 1;
    if      (logDelta >= 50) gapDelta = 5;
    else if (logDelta >= 30) gapDelta = 3;

    if (logDelta >= gapDelta) addRange(0, logDelta - gapDelta);
    addRange(logDelta, logQ);

    const uint32_t gapQ = (maxBits - logQ > 10) ? 3 : 1;
    addRange(logQ + gapQ, M);
    // HEAAN + boot: a fault in bit b is masked by the boot iff b minus the bits consumed
    // before the boot is >= logq_boot = logDelta + 10 (same constant as backends/heaan.cpp).
    // The coarse points above are ~(logQ - logDelta)/14 bits apart, far too sparse to locate
    // that edge, so sample EVERY bit in a window around each candidate edge
    // logq_boot + k*logDelta, k = 0..(mults in the pipeline). That covers any injection point.
    const bool has_boot = std::any_of(args.ops.begin(), args.ops.end(),
                                      [](const Op& op) { return op.type == OpType::Boot; });
    if (args.library == "heaan" && has_boot) {
        uint32_t n_mults = 0;
        for (const Op& op : args.ops) n_mults += is_mult(op.type);
        constexpr uint32_t kWindow = 8;
        for (uint32_t k = 0; k <= n_mults; ++k) {
            const uint32_t edge = logDelta + 10 + k * logDelta;
            const uint32_t lo = edge > kWindow ? edge - kWindow : 0;
            for (uint32_t b = lo; b <= std::min(edge + kWindow, M); ++b) res.push_back(b);
        }
        // The windows overlap the coarse points: keep the list sorted and without repeats
        // (a repeated bit would count twice when averaging).
        std::sort(res.begin(), res.end());
        res.erase(std::unique(res.begin(), res.end()), res.end());
    }
    return res;
}

// if logMin=logMax=0 it samples from [-1,1]
std::vector<double> uniform_dist(uint32_t batchSize,
                                 int64_t logMin,
                                 int64_t logMax,
                                 uint64_t seed,
                                 bool verbose)
{
    std::vector<double> input(batchSize);

    // Caso especial: ambos cero → [-1, 1]
    const bool specialSymmetric = (logMin == 0 && logMax == 0);
    if (!specialSymmetric && logMin >= logMax) {
        throw std::invalid_argument("logMin < logMax (except the case 0,0 for range [-1,1]).");
    }

    if (verbose) {
        std::cout << "Parameters: batchSize=" << batchSize
                  << ", logMin=" << logMin
                  << ", logMax=" << logMax
                  << ", seed=" << seed << std::endl;
    }

    std::mt19937_64 gen(seed);

    double min_val, max_val;

    if (specialSymmetric) {
        min_val = -1.0;
        max_val =  1.0;
    } else {
        min_val = std::pow(2.0, static_cast<double>(logMin));
        max_val = std::pow(2.0, static_cast<double>(logMax));
    }

    if (verbose) {
        std::cout << "Range = [" << min_val << ", " << max_val << "]" << std::endl;
    }

    std::uniform_real_distribution<double> dist(min_val, max_val);

    for (uint32_t i = 0; i < batchSize; ++i) {
        input[i] = dist(gen);
        if (verbose)
            std::cout << input[i] << ", ";
    }

    if (verbose)
        std::cout << std::endl;

    return input;
}


