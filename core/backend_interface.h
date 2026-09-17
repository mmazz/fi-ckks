#pragma once
// Lo que tiene que implementar cada binario (backend + workload).
// fi_main.cpp es el mismo para todos; el backend se elige al linkear.
#include "args.h"
#include "campaign_helper.h"
#include "injector.h"
#include "metrics.h"

#include <cstdint>
#include <vector>

struct IterationResult {
    std::vector<double> values;
    bool     detected        = false;  // detector de SDC de la libreria (solo OpenFHE)
    uint32_t hidden_layer    = 0;      // NN: neurona donde cayo el fault
    uint32_t reduceSum_layer = 0;      // NN: rotacion de reduceSum donde cayo el fault
};

struct BackendContext {
    virtual ~BackendContext() = default;
    // true: values son logits y el main loguea si cambio la clase predicha.
    bool   classifier   = false;
    // Tolerancia del chequeo claro vs CKKS. 0 = la del main (1e-4, o 1e-3 con boot).
    double baseline_tol = 0.0;
};

void backend_prepare_args(CampaignArgs& args);

BackendContext* setup_campaign(const CampaignArgs& args);
void destroy_campaign(BackendContext* ctx);

// Salida esperada calculada en claro (mismo tamano que IterationResult::values).
std::vector<double> get_reference_output(const BackendContext* ctx);

IterationResult run_iteration(BackendContext* ctx, const CampaignArgs& args, Injector& inj);
