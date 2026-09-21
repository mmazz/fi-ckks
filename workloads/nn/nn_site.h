#pragma once
// Where inside the network the fault lands. Shared by heaan_nn.cpp and openfhe_nn.cpp.
#include "backend_interface.h"
#include "mnist.h"

#include <random>

namespace nn {

// Where the fault lands inside the network on this run.
struct Site {
    uint32_t neuron = 0;   // logged as hidden_layer
    uint32_t rot    = 0;   // logged as reduceSum_layer
};

inline bool is_internal(Stage st)
{
    return st == Stage::HiddenLayer || st == Stage::ChebyTanh3 || st == Stage::Mul ||
           st == Stage::Rescale || st == Stage::Add || st == Stage::Rot;
}

// The site is drawn from (seed, seed_input, limb, coeff) with its own generator, NOT
// from the campaign RNG. Two consequences, both wanted:
//   - every bit of the same coefficient hits the same neuron, so a coeff x bit map
//     shows what the coefficient does instead of the variance between neurons;
//   - the campaign RNG is only consumed by the (limb, coeff) sampling, so two
//     campaigns that differ only in stage/op_step now sweep the same coefficients.
// Clean runs never get here, so the campaign stays deterministic.
inline Site pick_site(const CampaignArgs& args, Injector& inj)
{
    Site s;
    if (!is_internal(args.stage) || !inj.here(args.stage)) return s;

    const FaultSpec& f = inj.spec();
    std::seed_seq seq{uint32_t(args.seed), uint32_t(args.seed_input), f.limb, f.coeff};
    std::mt19937_64 gen(seq);

    s.neuron = uint32_t(std::uniform_int_distribution<int>(0, int(NN_HIDDEN) - 1)(gen));
    const bool uses_rot = args.stage == Stage::Rot ||
                          (args.stage == Stage::HiddenLayer && args.op_step >= 4 && args.op_step <= 11);
    if (uses_rot)
        s.rot = uint32_t(std::uniform_int_distribution<int>(0, int(args.logSlots) - 1)(gen));
    return s;
}

// true if this run injects at (stage, step) and we are on the chosen site.
inline bool at(Injector& inj, bool on_site, Stage stage, uint32_t step)
{
    return on_site && inj.here(stage) && inj.spec().op_step == step;
}

} // namespace nn
