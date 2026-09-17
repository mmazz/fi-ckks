#include "openfhe.h"
#include "backend_interface.h"
#include "openfhe_inject.h"
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

    configure_sdc(args);

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
       throw std::invalid_argument("openfhe: 'boot' hasn't been implemented yet");

   uint32_t n_mults = 0;
   for (const Op& op : args.ops) n_mults += is_mult(op.type);
   if (ctx->manualRescale && n_mults > args.mult_depth)
       throw std::invalid_argument("openfhe: the pipeline has " + std::to_string(n_mults) +
                                   " multiplications and mult_depth=" + std::to_string(args.mult_depth));

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
       case OpType::Boot:   throw std::logic_error("openfhe: boot hasn't been implemented yet");
       }
   }
    if (inj.here("decrypt_c0")) inject(c->GetElements()[0], args.withNTT, inj);
    if (inj.here("decrypt_c1")) inject(c->GetElements()[1], args.withNTT, inj);

    ctx.cc->Decrypt(ctx.keys.secretKey, c, &result_bitFlip);

    bool detected = SDCConfigHelper::WasSDCDetected(result_bitFlip);

    result_bitFlip->SetLength(1 << args.logSlots);

    return {result_bitFlip->GetRealPackedValue(), detected};
}


