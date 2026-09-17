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
        uint32_t qbits = 0;
        for (const auto& t : towers) qbits = std::max<uint32_t>(qbits, t.GetModulus().GetMSB());
        inj.record_probe(uint32_t(towers.size()), qbits);
    } else {
        const FaultSpec& f = inj.spec();
        const DCRTPoly before = p;
        auto& t = towers.at(f.limb);
        if (f.coeff >= t.GetLength()) throw std::out_of_range("coeff fuera de rango");
        const uint64_t a = t[f.coeff].ConvertToInt();
        const uint64_t b = a ^ inj.mask64();
        t[f.coeff] = NativeInteger(b);
        inj.record_flip(__builtin_popcountll(a ^ b), count_diff(before, p));
    }
    p.SetFormat(orig);
}
