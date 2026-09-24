#pragma once
// Piezas comunes de OpenFHE: inyeccion en DCRTPoly y configuracion del detector de SDC.
// Lo usan backends/openfhe.cpp y workloads/nn/openfhe_nn.cpp.
#include "campaign_helper.h"
#include "injector.h"
#include "openfhe.h"
#include "fault-hook.h"
// Flipea (limb, coeff, bit, amountBits) del FaultSpec activo en `p`.
// withNTT = true: el flip se hace en representacion de evaluacion (NTT).
// Deja `p` en el formato en que llego. En modo probe solo mide limbs y bits.
void inject(lbcrypto::DCRTPoly& p, bool withNTT, Injector& inj);

// Detector de SDC del fork (config global) segun --attackModeSKA / --thresholdSKA.
// Nunca tira excepcion: solo deja el resultado para SDCConfigHelper::WasSDCDetected.
void configure_sdc(const CampaignArgs& args);

// Arms the fork's in-operation fault site (fault-hook.h) for the active FaultSpec:
// the site is (op, inj.spec().op_step) and the flip itself is inject(), so the same
// checks (one coefficient, amountBits bits, out_of_range, probe) apply.
// Disarms on scope exit, so a site that never fired cannot fire in a later op.
class ArmedFault {
public:
    ArmedFault(lbcrypto::fi::Op op, bool withNTT, Injector& inj);
    ~ArmedFault();
    ArmedFault(const ArmedFault&) = delete;
    ArmedFault& operator=(const ArmedFault&) = delete;
};
