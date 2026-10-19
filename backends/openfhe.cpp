#include "openfhe.h"
#include "backend_interface.h"
#include "openfhe_inject.h"
#include "attack_mode.h"
#include "constants-defs.h"
#include "metrics.h"
#include "args.h"
#include <array>
using namespace lbcrypto;
// Bootstrapping is only used here, never injected into. Level budget of its CoeffsToSlots
// and SlotsToCoeffs (fixed, like logT/logI in HEAAN). OpenFHE clamps it to log2(slots).
constexpr uint32_t kBootLevelBudget = 2;
// EvalBootstrap (64-bit build) needs q0 / Delta <= 2^correctionFactor: 9 in FIXED*,
// 7..13 in FLEXIBLE* (>= 10 up to logN=12). So logQ - logDelta <= 9.
constexpr uint32_t kBootMaxGap = 9;


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
    args.isComplex = 0;            // HEAAN only: CKKS here is real-packed
    if (args.bitsPerCoeff > 64)
        throw std::invalid_argument("openfhe: bitsPerCoeff <= 64");
    require_stage(args.stage, {Stage::Encode, Stage::EncryptC0, Stage::EncryptC1,
                               Stage::DecryptC0, Stage::DecryptC1, Stage::Add, Stage::Mul},
                  "openfhe");
        // In-operation sites of the fork (fault-hook.h). Out-of-range steps would only
    // fail later with "never reached"; better to say why right away.
    if (args.stage == Stage::Add && args.op_step >= fi::ADD_NUM_STEPS)
        throw std::invalid_argument("openfhe: add has op_step 0.." + std::to_string(fi::ADD_NUM_STEPS - 1));
    if (args.stage == Stage::Mul && args.op_step >= fi::MULT_NUM_STEPS)
        throw std::invalid_argument("openfhe: mul has op_step 0.." + std::to_string(fi::MULT_NUM_STEPS - 1));
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
    const ScalingTechnique st = toScalingTechnique(args.scaleTech);
    const bool boot = has_op(args.ops, OpType::Boot);

    CCParams<CryptoContextCKKSRNS> params;
    // With a boot, mult_depth = levels each boot gives back (levelsAvailableAfterBootstrap
    // in OpenFHE's examples); the context gets the boot's own levels on top.
    std::vector<uint32_t> levelBudget;
    uint32_t boot_depth = 0;
    if (boot) {
        if (args.logQ > args.logDelta + kBootMaxGap)
            throw std::invalid_argument("openfhe: 'boot' needs logQ - logDelta <= " +
                                        std::to_string(kBootMaxGap) + " (e.g. logQ=60, logDelta=51..59)");
        if (args.mult_depth < 1)
            throw std::invalid_argument("openfhe: 'boot' needs --mult_depth >= 1 (levels left after "
                                        "each boot); with 0, EvalBootstrap returns its input unchanged");
        // Same clamp as EvalBootstrapSetup (fewer than 3 slots count as logSlots=1), so the
        // depth below is the one OpenFHE really uses.
        const uint32_t b = std::min(kBootLevelBudget, std::max<uint32_t>(1, args.logSlots));
        levelBudget = {b, b};
        boot_depth  = FHECKKSRNS::GetBootstrapDepth(levelBudget, params.GetSecretKeyDist());
    }
    params.SetMultiplicativeDepth(args.mult_depth + boot_depth);
    params.SetScalingModSize(args.logDelta);
    params.SetFirstModSize(args.logQ);
    params.SetBatchSize(1 << args.logSlots);
    params.SetRingDim(1 << args.logN);
    params.SetScalingTechnique(st);

    params.SetSecurityLevel(HEStd_NotSet);

    // Replay the limbs of the pipeline: a fresh ciphertext has depth + 1, each mult drops
    // one, a boot starts from 2 (see run_iteration) and leaves mult_depth + 1. Fail here,
    // with a message, instead of deep inside OpenFHE. The *AUTO techniques rescale lazily
    // but spend the same levels; without a boot they are left to OpenFHE, as before.
    if (st == ScalingTechnique::FIXEDMANUAL || boot) {
        int64_t limbs = int64_t(args.mult_depth + boot_depth) + 1;
        for (const Op& op : args.ops) {
            if (op.type == OpType::Boot) {
                if (limbs < 2)
                    throw std::invalid_argument("openfhe: no level left for 'boot', raise --mult_depth");
                limbs = int64_t(args.mult_depth) + 1;
            } else if (is_mult(op.type) && --limbs < 1) {
                throw std::invalid_argument("openfhe: the pipeline needs more than mult_depth=" +
                                            std::to_string(args.mult_depth) + " levels" +
                                            (boot ? " between boots" : ""));
            }
        }
    }

    auto* ctx = new OpenFHEContext();
    ctx->manualRescale = (st == ScalingTechnique::FIXEDMANUAL);
    ctx->prng = &lbcrypto::PseudoRandomNumberGenerator::GetPRNG();
    ctx->prng->SetSeed(args.seed);
    ctx->cc = GenCryptoContext(params);
    ctx->cc->Enable(PKE);
    ctx->cc->Enable(KEYSWITCH);
    ctx->cc->Enable(LEVELEDSHE);
    if (boot) {
        ctx->cc->Enable(ADVANCEDSHE);
        ctx->cc->Enable(FHE);
    }

    ctx->keys = ctx->cc->KeyGen();

    // The boot multiplies ciphertexts internally: it needs the relinearization key too.
    if (has_op(args.ops, OpType::Mul) || boot)
        ctx->cc->EvalMultKeyGen(ctx->keys.secretKey);
    if (boot) {
        ctx->cc->EvalBootstrapSetup(levelBudget, {0, 0}, 1u << args.logSlots);
        ctx->cc->EvalBootstrapKeyGen(ctx->keys.secretKey, 1u << args.logSlots);
    }

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

    if (inj.here(Stage::Encode)) inject(ptxt->GetElement<DCRTPoly>(), args.withNTT, inj);

    Ciphertext<DCRTPoly> c = ctx.cc->Encrypt(ctx.keys.publicKey, ptxt);



    if (inj.here(Stage::EncryptC0)) inject(c->GetElements()[0], args.withNTT, inj);
    if (inj.here(Stage::EncryptC1)) inject(c->GetElements()[1], args.withNTT, inj);

   auto operand_pt = [&]() { return ctx.cc->MakeCKKSPackedPlaintext(ctx.baseInput, 1, c->GetLevel()); };
   auto operand_ct = [&]() { return ctx.cc->Encrypt(ctx.keys.publicKey, operand_pt()); };
   auto rescale    = [&]() { if (ctx.manualRescale) ctx.cc->RescaleInPlace(c); };
   // Runs `call` with the fork's fault site armed when this occurrence is the target.
   auto armed = [&](Stage st, fi::Op site, uint32_t d, auto&& call) {
       if (!inj.here(st, d)) return call();
       ArmedFault guard(site, args.withNTT, inj);
       return call();
   };

   std::array<uint32_t, kNumOpTypes> occ{};   // occurrences per op type -> op_depth
   for (const Op& op : args.ops) {
       const uint32_t d = occ[size_t(op.type)]++;
       switch (op.type) {
       case OpType::Add: {
           const auto rhs = operand_ct();   // encrypt outside the armed scope
           c = armed(Stage::Add, fi::Op::Add, d, [&] { return ctx.cc->EvalAdd(c, rhs); });
           break;
       }
       case OpType::PMul:   c = ctx.cc->EvalMult(c, operand_pt());   rescale();     break;
       case OpType::Mul: {
           const auto rhs = operand_ct();
           c = armed(Stage::Mul, fi::Op::Mult, d, [&] { return ctx.cc->EvalMult(c, rhs); });
           rescale();
           break;
       }
       case OpType::Scalar: c = ctx.cc->EvalMult(c, op.param);       rescale();     break;
       case OpType::Rot:    c = ctx.cc->EvalRotate(c, int32_t(op.param));           break;
       case OpType::Boot: {
           // EvalBootstrap only reads the lowest limbs, and returns its input unchanged when
           // it has at least as many limbs as the output. Start it from 2 limbs (q0 + the one
           // its first rescale drops), as OpenFHE's examples do, so every boot is a real one.
           // Compress = pending rescale + drop limbs, for every scaling technique
           // (LevelReduceInPlace does nothing outside FIXEDMANUAL).
           c = ctx.cc->Compress(c, 2);
           c = ctx.cc->EvalBootstrap(c);
           rescale();   // FIXEDMANUAL only: the boot returns with its last rescale pending
           break;
       }
       }
   }
    if (inj.here(Stage::DecryptC0)) inject(c->GetElements()[0], args.withNTT, inj);
    if (inj.here(Stage::DecryptC1)) inject(c->GetElements()[1], args.withNTT, inj);

    ctx.cc->Decrypt(ctx.keys.secretKey, c, &result_bitFlip);

    bool detected = SDCConfigHelper::WasSDCDetected(result_bitFlip);

    result_bitFlip->SetLength(1 << args.logSlots);

    return {result_bitFlip->GetRealPackedValue(), detected};
}


