#pragma once
#include "attack_mode.h"
#include "pipeline.h"
#include <chrono>
#include <iomanip>
#include <string>
#include <cstdint>
#include <iostream>
#include <optional>
#include <fstream>
#include <vector>

inline std::string timestamp_now() {
    auto t = std::chrono::system_clock::to_time_t(
        std::chrono::system_clock::now());
    std::ostringstream ss;
    ss << std::put_time(std::localtime(&t), "%Y-%m-%dT%H:%M:%S");
    return ss.str();
}

struct CampaignArgs {
    std::string library = "none";
    std::string stage = "none";

    uint32_t bitsPerCoeff = 64;
    uint32_t logN = 3;
    uint32_t logQ = 60;
    uint32_t logDelta = 50;
    uint32_t logSlots = 2;
    uint32_t mult_depth = 0;
    uint32_t logMin = 0;
    uint32_t logMax = 0;

    uint32_t seed = 0;
    uint32_t seed_input = 0;

    bool withNTT = false;
    std::string pipeline;        // forma canonica, ej: "add; mul x2; rot 4"
    std::vector<Op> ops;         // pipeline ya parseado y expandido
    uint32_t op_step = 0;
    uint32_t op_depth = 0;
    size_t isComplex = 0;
    bool isExhaustive = true;
    bool verbose = false;
    uint32_t dnum = 3;
    uint32_t amountBits = 1;
    std::string scaleTech = "FIXEDMANUAL";
    std::string results_dir = "results";

    uint32_t numSamples = 50;
    bool saveVectors = false;

    std::optional<AttackModeSKA> openfhe_attack_mode = AttackModeSKA::CompleteInjection;
    std::optional<double> openfhe_threshold_bits = 5.0;
    bool logSlots_provided = false;
    void print(std::ostream& os = std::cout) const;
};

void print_usage(const char* program_name);
CampaignArgs parse_arguments(int argc, char* argv[]);


struct CampaignContext {
    uint32_t campaign_id;
    CampaignArgs args;
};
