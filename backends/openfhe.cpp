#include "openfhe.h"
#include "backend_interface.h"
#include "attack_mode.h"
#include "constants-defs.h"
#include "metrics.h"
#include "args.h"
using namespace lbcrypto;

struct OpenFHEContext final : BackendContext {
    CryptoContext<DCRTPoly> cc;
    KeyPair<DCRTPoly> keys;
    std::vector<double> baseInput;
    std::vector<double> goldenOutput;
    PRNG* prng;
    bool manualRescale = false;
};


std::vector<double> get_reference_output(const BackendContext* bctx)
{
    auto& ctx = static_cast<const OpenFHEContext&>(*bctx);
    return ctx.goldenOutput;
}


void backend_prepare_args(CampaignArgs& args){
    args.library = "openfhe";
}

SecretKeyAttackMode to_openfhe_attack_mode(AttackModeSKA mode)
{
    using OF = SecretKeyAttackMode;
    switch (mode) {
        case AttackModeSKA::Disabled:
            return OF::Disabled;
        case AttackModeSKA::CompleteInjection:
            return OF::CompleteInjection;
        case AttackModeSKA::RealOnly:
            return OF::RealOnly;
        case AttackModeSKA::ImaginaryOnly:
            return OF::ImaginaryOnly;
    }
    throw std::logic_error("Invalid AttackModeSKA");
}

std::string toLower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(),
                   [](unsigned char c){ return std::tolower(c); });
    return s;
}

ScalingTechnique toScalingTechnique(const std::string& s) {
    std::string key = toLower(s);

    if (key == "fixedauto") return ScalingTechnique::FIXEDAUTO;
    if (key == "fixedmanual") return ScalingTechnique::FIXEDMANUAL;
    if (key == "flexibleauto") return ScalingTechnique::FLEXIBLEAUTO;
    if (key == "flexibleautoext") return ScalingTechnique::FLEXIBLEAUTOEXT;

    throw std::invalid_argument("Unknown scaling technique: " + s);
}

BackendContext* setup_campaign(const CampaignArgs& args)
{

    if (args.openfhe_attack_mode || args.openfhe_threshold_bits)
    {
        auto attackModeOF =
            args.openfhe_attack_mode
                ? to_openfhe_attack_mode(*args.openfhe_attack_mode)
                : SecretKeyAttackMode::CompleteInjection;

        double threshold = args.openfhe_threshold_bits.value_or(5.0);

        auto cfg = SDCConfigHelper::MakeConfig(
            false, // Disable execption
            attackModeOF,
            threshold
        );

        SDCConfigHelper::SetGlobalConfig(cfg);
    }
    CCParams<CryptoContextCKKSRNS> params;
    params.SetMultiplicativeDepth(args.mult_depth);
    params.SetScalingModSize(args.logDelta);
    params.SetFirstModSize(args.logQ);
    params.SetBatchSize(1 << args.logSlots);
    params.SetRingDim(1 << args.logN);
    params.SetScalingTechnique(toScalingTechnique(args.scaleTech));

    params.SetSecurityLevel(HEStd_NotSet);
    auto* ctx = new OpenFHEContext();
    ctx->manualRescale = (toScalingTechnique(args.scaleTech) == ScalingTechnique::FIXEDMANUAL);
    ctx->prng = &lbcrypto::PseudoRandomNumberGenerator::GetPRNG();
    ctx->prng->SetSeed(args.seed);
    ctx->cc = GenCryptoContext(params);
    ctx->cc->Enable(PKE);
    ctx->cc->Enable(KEYSWITCH);
    ctx->cc->Enable(LEVELEDSHE);

    ctx->keys = ctx->cc->KeyGen();
   if (has_op(args.ops, OpType::Boot))
       throw std::invalid_argument("openfhe: 'boot' todavia no esta implementado");

   uint32_t n_mults = 0;
   for (const Op& op : args.ops) n_mults += is_mult(op.type);
   if (ctx->manualRescale && n_mults > args.mult_depth)
       throw std::invalid_argument("openfhe: el pipeline tiene " + std::to_string(n_mults) +
                                   " multiplicaciones y mult_depth=" + std::to_string(args.mult_depth));

   if (has_op(args.ops, OpType::Mul))
       ctx->cc->EvalMultKeyGen(ctx->keys.secretKey);

   std::vector<int32_t> rots;
   for (const Op& op : args.ops)
       if (op.type == OpType::Rot && std::find(rots.begin(), rots.end(), int32_t(op.param)) == rots.end())
           rots.push_back(int32_t(op.param));
   if (!rots.empty())
       ctx->cc->EvalAtIndexKeyGen(ctx->keys.secretKey, rots);


    compute_plain_io(args, ctx->baseInput, ctx->goldenOutput);

    return ctx;
}

void destroy_campaign(BackendContext* ctx) {
    delete ctx;
}
   static int count_diff(const DCRTPoly& a, const DCRTPoly& b) {
       const auto& ta = a.GetAllElements();
       const auto& tb = b.GetAllElements();
       int n = 0;
       for (size_t i = 0; i < ta.size(); ++i)
           for (size_t j = 0; j < ta[i].GetLength(); ++j)
               n += (ta[i][j] != tb[i][j]);
       return n;
   }

   static void inject(DCRTPoly& p, bool withNTT, Injector& inj) {
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

IterationResult run_iteration(BackendContext* bctx,
              const CampaignArgs& args,Injector& inj)
{
    auto& ctx = static_cast<OpenFHEContext&>(*bctx);

   // ctx.prng->ResetToSeed();
    ctx.prng->SetSeed(args.seed);
    Plaintext result_bitFlip;
    Plaintext ptxt = ctx.cc->MakeCKKSPackedPlaintext(ctx.baseInput);

    if (inj.here("encode")) inject(ptxt->GetElement<DCRTPoly>(), args.withNTT, inj);

    Ciphertext<DCRTPoly> c = ctx.cc->Encrypt(ctx.keys.publicKey, ptxt);



    if (inj.here("encrypt_c0")) inject(c->GetElements()[0], args.withNTT, inj);
    if (inj.here("encrypt_c1")) inject(c->GetElements()[1], args.withNTT, inj);

   auto operand_pt = [&]() { return ctx.cc->MakeCKKSPackedPlaintext(ctx.baseInput, 1, c->GetLevel()); };
   auto operand_ct = [&]() { return ctx.cc->Encrypt(ctx.keys.publicKey, operand_pt()); };
   auto rescale    = [&]() { if (ctx.manualRescale) ctx.cc->RescaleInPlace(c); };

   for (const Op& op : args.ops) {
       switch (op.type) {
       case OpType::Add:    c = ctx.cc->EvalAdd(c, operand_ct());                   break;
       case OpType::PMul:   c = ctx.cc->EvalMult(c, operand_pt());   rescale();     break;
       case OpType::Mul:    c = ctx.cc->EvalMult(c, operand_ct());   rescale();     break;
       case OpType::Scalar: c = ctx.cc->EvalMult(c, op.param);       rescale();     break;
       case OpType::Rot:    c = ctx.cc->EvalRotate(c, int32_t(op.param));           break;
       case OpType::Boot:   throw std::logic_error("openfhe: boot no implementado");
       }
   }
    if (inj.here("decrypt_c0")) inject(c->GetElements()[0], args.withNTT, inj);
    if (inj.here("decrypt_c1")) inject(c->GetElements()[1], args.withNTT, inj);

    ctx.cc->Decrypt(ctx.keys.secretKey, c, &result_bitFlip);

    bool detected = SDCConfigHelper::WasSDCDetected(result_bitFlip);

    result_bitFlip->SetLength(1 << args.logSlots);

    return {result_bitFlip->GetRealPackedValue(), detected};
}


