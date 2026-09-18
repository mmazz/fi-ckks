#pragma once
// Extra del workload NN, fuera de backend_interface.h: lo implementan heaan_nn.cpp y openfhe_nn.cpp.
#include "backend_interface.h"
#include <cstddef>

// Cambia la imagen de un contexto ya creado, sin tocar claves ni pesos codificados.
// No exige que la red en claro acierte: la usa apps/tools/nn_metrics.cpp para medir
// accuracy sobre todas las imagenes. Las campanias siguen usando setup_campaign.
void nn_set_image(BackendContext* ctx, size_t image_index);
