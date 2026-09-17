// Workload NN sobre OpenFHE: la misma red que heaan_nn.cpp (ver mnist.h).
// Implementa backend_interface.h, asi que corre con el mismo apps/fi_main.cpp.
//
// Stages (--stage) y op_step:
//   encode, encrypt_c0, encrypt_c1       ciphertext de entrada
//   decrypt_c0, decrypt_c1               logit de la clase correcta
//   hidden_layer  0..13   mismos registros que en HEAAN (step par = c0, impar = c1)
//   cheby_tanh3   0..9    mismos registros que en HEAAN
// Todavia no hay decode ni stages dentro de las operaciones (mul, rescale, add, rot):
// con esos stages el probe falla con "never reach".
// Scaling FLEXIBLEAUTO: los rescale los hace OpenFHE.
#include "backend_interface.h"
#include "mnist.h"
#include "nn_site.h"
#include "openfhe_inject.h"

#include "openfhe.h"

#include <memory>
#include <vector>

using namespace lbcrypto;
using nn::Site;
using nn::at;
using nn::pick_site;

namespace {

using Ct = Ciphertext<DCRTPoly>;

struct NNOpenfheContext : BackendContext {
    CryptoContext<DCRTPoly> cc;
    KeyPair<DCRTPoly>       keys;
    PRNG*                   prng = nullptr;

    NNModel model;
    std::vector<Plaintext>              W1;   // fila j de W1 (una por neurona)
    std::vector<Plaintext>              b1;   // b1[j] replicado en todos los slots
    std::vector<std::vector<Plaintext>> W2;   // W2[o][h] replicado en todos los slots
    std::vector<Plaintext>              b2;   // b2[o] replicado en todos los slots
};

// Registro de la red: step par -> c0, step impar -> c1 (igual que bx/ax en HEAAN).
void flip_reg(Ct& c, const CampaignArgs& args, Injector& inj)
{
    inject(c->GetElements()[inj.spec().op_step % 2], args.withNTT, inj);
}

// true si esta corrida inyecta en first_step o first_step + 1 (el par c0/c1 del registro).
bool at_pair(Injector& inj, bool on_site, const char* stage, uint32_t first_step)
{
    return at(inj, on_site, stage, first_step) || at(inj, on_site, stage, first_step + 1);
}

void reduceSum(NNOpenfheContext& ctx, Ct& ct, const CampaignArgs& args,
               Injector& inj, const Site& site, bool on_neuron)
{
    for (uint32_t i = 0; i < args.logSlots; ++i) {
        const bool on_site = on_neuron && i == site.rot;
        const int32_t k = int32_t(1) << i;

        Ct rot;
        if (at_pair(inj, on_site, "hidden_layer", 4)) {
            Ct ct_copy = ct->Clone();   // el fault solo lo ve esta rotacion
            flip_reg(ct_copy, args, inj);
            rot = ctx.cc->EvalRotate(ct_copy, k);
        } else {
            rot = ctx.cc->EvalRotate(ct, k);
        }

        if (at_pair(inj, on_site, "hidden_layer", 6)) flip_reg(rot, args, inj);
        if (at_pair(inj, on_site, "hidden_layer", 8)) flip_reg(ct, args, inj);
        ct = ctx.cc->EvalAdd(ct, rot);
        if (at_pair(inj, on_site, "hidden_layer", 10)) flip_reg(ct, args, inj);
    }
}

// 0.98*x - 0.23*x^3. Modifica x (es el registro de la neurona).
Ct chebyTanh3(NNOpenfheContext& ctx, Ct& x, const CampaignArgs& args, Injector& inj, bool on_site)
{
    auto& cc = ctx.cc;

    if (at_pair(inj, on_site, "cheby_tanh3", 0)) flip_reg(x, args, inj);
    Ct x2 = cc->EvalMult(x, x);

    if (at_pair(inj, on_site, "cheby_tanh3", 2)) flip_reg(x, args, inj);
    Ct x3 = cc->EvalMult(x2, x);

    if (at_pair(inj, on_site, "cheby_tanh3", 4)) flip_reg(x3, args, inj);
    Ct t1 = cc->EvalMult(x3, -0.23);

    if (at_pair(inj, on_site, "cheby_tanh3", 6)) flip_reg(x, args, inj);
    Ct t2 = cc->EvalMult(x, 0.98);

    if (at_pair(inj, on_site, "cheby_tanh3", 8)) flip_reg(t2, args, inj);
    return cc->EvalAdd(t1, t2);
}

std::vector<Ct> forward(NNOpenfheContext& ctx, const Ct& c, const CampaignArgs& args,
                        Injector& inj, const Site& site)
{
    auto& cc = ctx.cc;

    std::vector<Ct> layer1;
    layer1.reserve(NN_HIDDEN);
    for (size_t j = 0; j < NN_HIDDEN; ++j) {
        const bool on_site = (j == site.neuron);

        Ct s;
        if (at_pair(inj, on_site, "hidden_layer", 0)) {
            Ct c_copy = c->Clone();   // el fault solo lo ve esta neurona
            flip_reg(c_copy, args, inj);
            s = cc->EvalMult(c_copy, ctx.W1[j]);
        } else {
            s = cc->EvalMult(c, ctx.W1[j]);
        }
        if (at_pair(inj, on_site, "hidden_layer", 2)) flip_reg(s, args, inj);

        reduceSum(ctx, s, args, inj, site, on_site);

        s = cc->EvalAdd(s, ctx.b1[j]);
        if (at_pair(inj, on_site, "hidden_layer", 12)) flip_reg(s, args, inj);

        layer1.push_back(chebyTanh3(ctx, s, args, inj, on_site));
    }

    std::vector<Ct> out;
    out.reserve(NN_OUTPUT);
    for (size_t o = 0; o < NN_OUTPUT; ++o) {
        Ct acc = cc->EvalMult(layer1[0], ctx.W2[o][0]);
        for (size_t h = 1; h < NN_HIDDEN; ++h)
            acc = cc->EvalAdd(acc, cc->EvalMult(layer1[h], ctx.W2[o][h]));
        out.push_back(cc->EvalAdd(acc, ctx.b2[o]));
    }
    return out;
}

} // namespace

void backend_prepare_args(CampaignArgs& args)
{
    args.library   = "openfheNN";
    args.scaleTech = "FLEXIBLEAUTO";   // la red no hace rescales a mano
    if (!args.ops.empty())
        throw std::invalid_argument("openfheNN: the workload is the network; --pipeline must be left empty");
    if ((size_t(1) << args.logSlots) < NN_INPUT)
        throw std::invalid_argument("openfheNN: 2^logSlots it has to be >= " + std::to_string(NN_INPUT));
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
    params.SetScalingTechnique(FLEXIBLEAUTO);
    params.SetSecurityLevel(HEStd_NotSet);

    auto ctx = std::make_unique<NNOpenfheContext>();
    ctx->classifier   = true;
    ctx->baseline_tol = 1e-2;
    ctx->prng = &PseudoRandomNumberGenerator::GetPRNG();
    ctx->prng->SetSeed(args.seed);

    ctx->cc = GenCryptoContext(params);
    ctx->cc->Enable(PKE);
    ctx->cc->Enable(KEYSWITCH);
    ctx->cc->Enable(LEVELEDSHE);

    ctx->keys = ctx->cc->KeyGen();
    ctx->cc->EvalMultKeyGen(ctx->keys.secretKey);
    std::vector<int32_t> rots;
    for (uint32_t i = 0; i < args.logSlots; ++i) rots.push_back(int32_t(1) << i);
    ctx->cc->EvalAtIndexKeyGen(ctx->keys.secretKey, rots);

    // seed_input elige la imagen: es el "input" de la campania.
    ctx->model = load_nn_model(nn_data_dir(), args.seed_input);
    const NNWeights& w = ctx->model.weights;
    const size_t slots = size_t(1) << args.logSlots;
    auto constant = [&](double v) { return ctx->cc->MakeCKKSPackedPlaintext(std::vector<double>(slots, v)); };

    for (size_t j = 0; j < NN_HIDDEN; ++j) {
        std::vector<double> row(slots, 0.0);
        std::copy(w.W1[j].begin(), w.W1[j].end(), row.begin());
        ctx->W1.push_back(ctx->cc->MakeCKKSPackedPlaintext(row));
        ctx->b1.push_back(constant(w.b1[j]));
    }
    ctx->W2.resize(NN_OUTPUT);
    for (size_t o = 0; o < NN_OUTPUT; ++o) {
        for (size_t h = 0; h < NN_HIDDEN; ++h)
            ctx->W2[o].push_back(constant(w.W2[o][h]));
        ctx->b2.push_back(constant(w.b2[o]));
    }
    return ctx.release();
}

void destroy_campaign(BackendContext* ctx)
{
    delete ctx;
}

std::vector<double> get_reference_output(const BackendContext* bctx)
{
    return static_cast<const NNOpenfheContext&>(*bctx).model.plain_logits;
}

IterationResult run_iteration(BackendContext* bctx, const CampaignArgs& args, Injector& inj)
{
    auto& ctx = static_cast<NNOpenfheContext&>(*bctx);
    ctx.prng->SetSeed(args.seed);
    const Site site = pick_site(args, inj);

    Plaintext ptxt = ctx.cc->MakeCKKSPackedPlaintext(ctx.model.image);
    if (inj.here("encode")) inject(ptxt->GetElement<DCRTPoly>(), args.withNTT, inj);

    Ct c = ctx.cc->Encrypt(ctx.keys.publicKey, ptxt);
    if (inj.here("encrypt_c0")) inject(c->GetElements()[0], args.withNTT, inj);
    if (inj.here("encrypt_c1")) inject(c->GetElements()[1], args.withNTT, inj);

    std::vector<Ct> outs = forward(ctx, c, args, inj, site);

    // Los faults de salida van al logit de la clase correcta.
    const size_t target = ctx.model.label;
    if (inj.here("decrypt_c0")) inject(outs[target]->GetElements()[0], args.withNTT, inj);
    if (inj.here("decrypt_c1")) inject(outs[target]->GetElements()[1], args.withNTT, inj);

    IterationResult res;
    res.values.reserve(outs.size());
    for (const Ct& out : outs) {
        Plaintext dec;
        ctx.cc->Decrypt(ctx.keys.secretKey, out, &dec);
        res.detected = res.detected || SDCConfigHelper::WasSDCDetected(dec);
        dec->SetLength(1);
        res.values.push_back(dec->GetRealPackedValue()[0]);
    }
    res.hidden_layer    = site.neuron;
    res.reduceSum_layer = site.rot;
    return res;
}
