#pragma once
// Eleccion del sitio del fault dentro de la red. Compartido por heaan_nn.cpp y openfhe_nn.cpp.
#include "backend_interface.h"
#include "mnist.h"

#include <string>

namespace nn {

// Donde cae el fault dentro de la red en esta corrida.
struct Site {
    uint32_t neuron = 0;   // se loguea como hidden_layer
    uint32_t rot    = 0;   // se loguea como reduceSum_layer
};

inline bool is_internal(Stage st)
{
    return st == Stage::HiddenLayer || st == Stage::ChebyTanh3 || st == Stage::Mul ||
           st == Stage::Rescale || st == Stage::Add || st == Stage::Rot;
}

// Solo sortea si esta corrida inyecta (o mide) en un stage interno.
// Las corridas limpias no consumen el rng: la campania sigue siendo determinista.
inline Site pick_site(const CampaignArgs& args, Injector& inj)
{
    Site s;
    if (!is_internal(args.stage) || !inj.here(args.stage)) return s;
    s.neuron = random_int(0, int(NN_HIDDEN) - 1);
    const bool uses_rot = args.stage == Stage::Rot ||
                          (args.stage == Stage::HiddenLayer && args.op_step >= 4 && args.op_step <= 11);
    if (uses_rot) s.rot = random_int(0, int(args.logSlots) - 1);
    return s;
}

// true si esta corrida inyecta en (stage, step) y estamos en el sitio elegido.
inline bool at(Injector& inj, bool on_site, Stage stage, uint32_t step)
{
    return on_site && inj.here(stage) && inj.spec().op_step == step;
}

} // namespace nn
