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

inline bool is_internal(const std::string& st)
{
    return st == "hidden_layer" || st == "cheby_tanh3" || st == "mul" ||
           st == "rescale" || st == "add" || st == "rot";
}

// Solo sortea si esta corrida inyecta (o mide) en un stage interno.
// Las corridas limpias no consumen el rng: la campania sigue siendo determinista.
inline Site pick_site(const CampaignArgs& args, Injector& inj)
{
    Site s;
    if (!is_internal(args.stage) || !inj.here(args.stage)) return s;
    s.neuron = random_int(0, int(NN_HIDDEN) - 1);
    const bool uses_rot = args.stage == "rot" ||
                          (args.stage == "hidden_layer" && args.op_step >= 4 && args.op_step <= 11);
    if (uses_rot) s.rot = random_int(0, int(args.logSlots) - 1);
    return s;
}

// true si esta corrida inyecta en (stage, step) y estamos en el sitio elegido.
inline bool at(Injector& inj, bool on_site, const char* stage, uint32_t step)
{
    return on_site && inj.here(stage) && inj.spec().op_step == step;
}

} // namespace nn
