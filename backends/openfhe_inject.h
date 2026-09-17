#pragma once
// Piezas comunes de OpenFHE: inyeccion en DCRTPoly y configuracion del detector de SDC.
// Lo usan backends/openfhe.cpp y workloads/nn/openfhe_nn.cpp.
#include "campaign_helper.h"
#include "injector.h"
#include "openfhe.h"

// Flipea (limb, coeff, bit, amountBits) del FaultSpec activo en `p`.
// withNTT = true: el flip se hace en representacion de evaluacion (NTT).
// Deja `p` en el formato en que llego. En modo probe solo mide limbs y bits.
void inject(lbcrypto::DCRTPoly& p, bool withNTT, Injector& inj);

// Detector de SDC del fork (config global) segun --attackModeSKA / --thresholdSKA.
// Nunca tira excepcion: solo deja el resultado para SDCConfigHelper::WasSDCDetected.
void configure_sdc(const CampaignArgs& args);
