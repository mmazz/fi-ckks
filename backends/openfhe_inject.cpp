#include "openfhe_inject.h"

#include <algorithm>
#include <stdexcept>

using namespace lbcrypto;

namespace {

int count_diff(const DCRTPoly& a, const DCRTPoly& b)
{
    const auto& ta = a.GetAllElements();
    const auto& tb = b.GetAllElements();
    int n = 0;
    for (size_t i = 0; i < ta.size(); ++i)
        for (size_t j = 0; j < ta[i].GetLength(); ++j)
            n += (ta[i][j] != tb[i][j]);
    return n;
}

SecretKeyAttackMode to_openfhe_attack_mode(AttackModeSKA mode)
{
    switch (mode) {
        case AttackModeSKA::Disabled:          return SecretKeyAttackMode::Disabled;
        case AttackModeSKA::CompleteInjection: return SecretKeyAttackMode::CompleteInjection;
        case AttackModeSKA::RealOnly:          return SecretKeyAttackMode::RealOnly;
        case AttackModeSKA::ImaginaryOnly:     return SecretKeyAttackMode::ImaginaryOnly;
    }
    throw std::logic_error("Invalid AttackModeSKA");
}

} // namespace

void configure_sdc(const CampaignArgs& args)
{
    const auto mode = args.openfhe_attack_mode ? to_openfhe_attack_mode(*args.openfhe_attack_mode)
                                               : SecretKeyAttackMode::CompleteInjection;
    const double threshold = args.openfhe_threshold_bits.value_or(5.0);
    // enableDetection = false: no tira excepcion, pero el estado queda en el plaintext.
    SDCConfigHelper::SetGlobalConfig(SDCConfigHelper::MakeConfig(false, mode, threshold));
}

void inject(DCRTPoly& p, bool withNTT, Injector& inj)
{
    const Format orig = p.GetFormat();
    p.SetFormat(withNTT ? Format::EVALUATION : Format::COEFFICIENT);
    auto& towers = p.GetAllElements();
    if (inj.probing()) {
        // El MINIMO: es el primer bit a partir del cual ALGUN limb se sale del modulo.
        // Con el maximo, un limb de 41 bits al lado de uno de 60 pasaba desapercibido.
        uint32_t qbits = towers.empty() ? 0 : ~uint32_t(0);
        for (const auto& t : towers) qbits = std::min<uint32_t>(qbits, t.GetModulus().GetMSB());
        inj.record_probe(uint32_t(towers.size()), qbits);
    } else {
        const FaultSpec& f = inj.spec();
        const DCRTPoly before = p;
        auto& t = towers.at(f.limb);
        if (f.coeff >= t.GetLength()) throw std::out_of_range("coeff out of range");
        const uint64_t a = t[f.coeff].ConvertToInt();
        const uint64_t b = a ^ inj.mask64();
        // El registro es de 64 bits; el modulo del limb no. Inyectamos el valor tal cual
        // (asi se comporta el hardware) pero marcamos la fila si quedo >= q, porque ahi
        // la perturbacion ya no es +-2^bit sino (a ^ 2^bit) mod q - a.
        if (b >= t.GetModulus().ConvertToInt()) inj.record_out_of_range();
        t[f.coeff] = NativeInteger(b);
        const uint64_t got = t[f.coeff].ConvertToInt();
        // The store must be a pure XOR with the mask: if OpenFHE ever reduced on
        // assignment the fault would stop being "flip these bits".
        if ((a ^ got) != inj.mask64())
            throw std::logic_error("stored value is not a ^ mask (the limb modulus reduced it?)");
        inj.record_flip(__builtin_popcountll(a ^ got), count_diff(before, p));
    }
    p.SetFormat(orig);
}

ArmedFault::ArmedFault(fi::Op op, bool withNTT, Injector& inj)
{
    fi::Arm(op, inj.spec().op_step, [&inj, withNTT](DCRTPoly& p) { inject(p, withNTT, inj); });
}

ArmedFault::~ArmedFault()
{
    fi::Disarm();
}
