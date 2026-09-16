#include "args.h"
#include <cmath>
#include <algorithm>
#include <stdexcept>

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
}


std::vector<uint32_t> bitsToFlipGenerator(const CampaignArgs& args)
{
    std::vector<uint32_t> res;
    res.reserve(25);

    const uint32_t logQ     = args.logQ;
    const uint32_t logDelta = args.logDelta;
    const uint32_t maxBits  = args.bitsPerCoeff;
    const uint32_t M        = maxBits - 1;

    auto addRange = [&](uint32_t start, uint32_t end)
    {
        if (end < start || end >= maxBits) return;
        uint32_t count = 0;
        if (count == 1) {
            res.push_back(start);
            return;
        }
        uint32_t diff = end - start + 1;
        if (diff == 0) {
            res.push_back(start);
            return;
        }
        if (diff < 3){
            return;
        }else if (diff < 5) {
            count = diff - 1;
        } else if (diff < 30) {
            count = 5;
        } else {
            count = 15;
        }
        for (uint32_t i = 0; i < count; i++) {
            uint32_t v = start + (uint64_t)(end - start) * i / (count - 1);

            if (res.empty() || res.back() != v)
                res.push_back(v);
        }
    };
    uint32_t gapDelta = 1;
    if (logDelta>=50)
        gapDelta = 5;
    else if (logDelta>=30)
        gapDelta = 3;
    if (logDelta >= gapDelta) addRange(0, logDelta - gapDelta);
    addRange(logDelta, logQ);

    uint32_t gapQ = 1;
    uint32_t diffQ = maxBits-logQ;
    if (diffQ>10)
        gapQ = 3;
    addRange(logQ+gapQ, M);
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


