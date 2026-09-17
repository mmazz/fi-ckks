#pragma once
// Puente entre el Injector del framework y el hook del fork de HEAAN (heaanfi::flip).
// Lo usan el backend (backends/heaan.cpp) y los workloads HEAAN (workloads/nn/heaan_nn.cpp).
// El estado global vive en heaan_inject.cpp: una sola copia en todo el binario.
#include "injector.h"
#include <NTL/ZZX.h>

// Activa `inj` durante una corrida. Todos los flips (los que pide el fork y los
// que hace el workload con client_flip) se validan contra ese Injector.
// Tiene que haber exactamente UN scope vivo por run_iteration: no anidar.
class InjectorScope {
public:
    InjectorScope(Injector& inj, long ring_degree);
    ~InjectorScope();
    InjectorScope(const InjectorScope&) = delete;
    InjectorScope& operator=(const InjectorScope&) = delete;
};

// Flip en un polinomio del lado del workload (encode, encrypt, decrypt, registros de la NN).
// Usa coeff/bit/amountBits del FaultSpec activo. En modo probe solo mide el ancho.
void client_flip(Injector& inj, NTL::ZZX& poly);
