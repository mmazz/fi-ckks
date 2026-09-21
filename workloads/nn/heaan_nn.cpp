// Workload NN sobre HEAAN: MLP 784 -> 64 -> 10 (ver mnist.h).
// Implementa backend_interface.h, asi que corre con el mismo apps/fi_main.cpp.
//
// Stages (--stage) y op_step:
//   encode, encrypt_c0, encrypt_c1       ciphertext de entrada
//   decrypt_c0, decrypt_c1, decode       logit de la clase correcta
//   hidden_layer  0..13   registros de una neurona (forward / reduceSum)
//   cheby_tanh3   0..9    registros de la activacion de una neurona
//   mul           0..25   multBitFlip de x^2 * x dentro de la activacion
//   rescale       0..3    rescale despues de x^3
//   add           0..5    suma final de la activacion
//   rot           0..11   una rotacion de reduceSum
// En los stages internos, cada inyeccion sortea la neurona (hidden_layer) y,
// cuando corresponde, la rotacion de reduceSum (reduceSum_layer). Ambas se loguean.
// op_depth tiene que ser 0: cada neurona se recorre una sola vez.
#include "backend_interface.h"
#include "heaan_inject.h"
#include "mnist.h"
#include "nn_workload.h"
#include "nn_site.h"
#include "HEAAN.h"
#include <NTL/ZZ.h>
#include <complex>
#include <cstdlib>
#include <memory>
#include <vector>

using nn::Site;
using nn::at;
using nn::pick_site;
namespace {

constexpr long kHammingWeight = 64;

struct NNHeaanContext : BackendContext {
    Context   cc;
    SecretKey sk;
    Scheme    scheme;
    NTL::ZZ   seed;

    NNModel model;
    std::vector<NTL::ZZX>              W1;   // fila j de W1 codificada (una por neurona)
    std::vector<std::vector<NTL::ZZX>> W2;   // W2[o][h] replicado en todos los slots

    NNHeaanContext(long logN, long logQ, long h, uint64_t seed_)
        : cc(logN, logQ), sk(logN, h), scheme(sk, cc), seed(NTL::ZZ(seed_)) {}
};


void reduceSum(NNHeaanContext& ctx, Ciphertext& ct, const CampaignArgs& args,
               Injector& inj, const Site& site, bool on_neuron)
{
    Scheme& he = ctx.scheme;
    for (uint32_t i = 0; i < args.logSlots; ++i) {
        const bool on_site = on_neuron && i == site.rot;
        const long k = 1L << i;

        Ciphertext rot;
        if (at(inj, on_site, Stage::HiddenLayer, 4) || at(inj, on_site, Stage::HiddenLayer, 5)) {
            Ciphertext ct_copy = ct;   // el fault solo lo ve esta rotacion
            client_flip(inj, inj.spec().op_step == 4 ? ct_copy.bx : ct_copy.ax);
            rot = he.leftRotateFast(ct_copy, k);
        } else if (on_site && inj.here(Stage::Rot)) {
            const FaultSpec& f = inj.spec();
            rot = he.leftRotateFastBitFlip(ct, k, f.op_step, f.coeff, f.bit, f.amountBits);
        } else {
            rot = he.leftRotateFast(ct, k);
        }

        if (at(inj, on_site, Stage::HiddenLayer, 6)) client_flip(inj, rot.bx);
        if (at(inj, on_site, Stage::HiddenLayer, 7)) client_flip(inj, rot.ax);
        if (at(inj, on_site, Stage::HiddenLayer, 8)) client_flip(inj, ct.bx);
        if (at(inj, on_site, Stage::HiddenLayer, 9)) client_flip(inj, ct.ax);
        he.addAndEqual(ct, rot);
        if (at(inj, on_site, Stage::HiddenLayer, 10)) client_flip(inj, ct.bx);
        if (at(inj, on_site, Stage::HiddenLayer, 11)) client_flip(inj, ct.ax);
    }
}

// 0.98*x - 0.23*x^3. Modifica c (es el registro de la neurona).
Ciphertext chebyTanh3(NNHeaanContext& ctx, Ciphertext& c, const CampaignArgs& args,
                      Injector& inj, bool on_site)
{
    Scheme& he = ctx.scheme;
    const long logP = args.logDelta;

    if (at(inj, on_site, Stage::ChebyTanh3, 0)) client_flip(inj, c.bx);
    if (at(inj, on_site, Stage::ChebyTanh3, 1)) client_flip(inj, c.ax);
    Ciphertext c2 = he.square(c);
    he.reScaleByAndEqual(c2, logP);

    if (at(inj, on_site, Stage::ChebyTanh3, 2)) client_flip(inj, c.bx);
    if (at(inj, on_site, Stage::ChebyTanh3, 3)) client_flip(inj, c.ax);
    Ciphertext c3;
    if (on_site && inj.here(Stage::Mul)) {
        const FaultSpec& f = inj.spec();
        c3 = he.multBitFlip(c2, c, f.op_step, f.coeff, f.bit, f.amountBits);
    } else {
        c3 = he.mult(c2, c);
    }
    if (on_site && inj.here(Stage::Rescale)) {
        const FaultSpec& f = inj.spec();
        he.reScaleByAndEqualBitFlip(c3, logP, f.op_step, f.coeff, f.bit, f.amountBits);
    } else {
        he.reScaleByAndEqual(c3, logP);
    }

    if (at(inj, on_site, Stage::ChebyTanh3, 4)) client_flip(inj, c3.bx);   // registro x^3
    if (at(inj, on_site, Stage::ChebyTanh3, 5)) client_flip(inj, c3.ax);
    he.multByConstAndEqual(c3, -0.23, logP);
    he.reScaleByAndEqual(c3, logP);

    if (at(inj, on_site, Stage::ChebyTanh3, 6)) client_flip(inj, c.bx);
    if (at(inj, on_site, Stage::ChebyTanh3, 7)) client_flip(inj, c.ax);
    he.multByConstAndEqual(c, 0.98, logP);
    he.reScaleByAndEqual(c, logP);

    if (at(inj, on_site, Stage::ChebyTanh3, 8)) client_flip(inj, c.bx);
    if (at(inj, on_site, Stage::ChebyTanh3, 9)) client_flip(inj, c.ax);
    if (on_site && inj.here(Stage::Add)) {
        const FaultSpec& f = inj.spec();
        c3 = he.addBitFlip(c3, c, f.op_step, f.coeff, f.bit, f.amountBits);
    } else {
        he.addAndEqual(c3, c);
    }
    return c3;
}

std::vector<Ciphertext> forward(NNHeaanContext& ctx, Ciphertext& c, const CampaignArgs& args,
                                Injector& inj, const Site& site)
{
    Scheme& he = ctx.scheme;
    const long logP = args.logDelta;

    std::vector<Ciphertext> layer1;
    layer1.reserve(NN_HIDDEN);
    for (size_t j = 0; j < NN_HIDDEN; ++j) {
        const bool on_site = (j == site.neuron);

        Ciphertext s;
        if (at(inj, on_site, Stage::HiddenLayer, 0) || at(inj, on_site, Stage::HiddenLayer, 1)) {
            Ciphertext c_copy = c;   // el fault solo lo ve esta neurona
            client_flip(inj, inj.spec().op_step == 0 ? c_copy.bx : c_copy.ax);
            s = he.multByPoly(c_copy, ctx.W1[j], logP);
        } else {
            s = he.multByPoly(c, ctx.W1[j], logP);
        }
        if (at(inj, on_site, Stage::HiddenLayer, 2)) client_flip(inj, s.bx);
        if (at(inj, on_site, Stage::HiddenLayer, 3)) client_flip(inj, s.ax);
        he.reScaleByAndEqual(s, logP);

        reduceSum(ctx, s, args, inj, site, on_site);

        he.addConstAndEqual(s, ctx.model.weights.b1[j]);
        if (at(inj, on_site, Stage::HiddenLayer, 12)) client_flip(inj, s.bx);
        if (at(inj, on_site, Stage::HiddenLayer, 13)) client_flip(inj, s.ax);

        layer1.push_back(chebyTanh3(ctx, s, args, inj, on_site));
    }

    std::vector<Ciphertext> out;
    out.reserve(NN_OUTPUT);
    for (size_t o = 0; o < NN_OUTPUT; ++o) {
        Ciphertext acc = he.multByPoly(layer1[0], ctx.W2[o][0], logP);
        he.reScaleByAndEqual(acc, logP);
        for (size_t h = 1; h < NN_HIDDEN; ++h) {
            Ciphertext term = he.multByPoly(layer1[h], ctx.W2[o][h], logP);
            he.reScaleByAndEqual(term, logP);
            he.addAndEqual(acc, term);
        }
        he.addConstAndEqual(acc, ctx.model.weights.b2[o]);
        out.push_back(std::move(acc));
    }
    return out;
}

} // namespace

void backend_prepare_args(CampaignArgs& args)
{
    args.library    = "heaanNN";
    args.mult_depth = 0;
    if (!args.ops.empty())
        throw std::invalid_argument("heaanNN: the workload is the network; --pipeline must be left empty");
    if ((size_t(1) << args.logSlots) < NN_INPUT)
        throw std::invalid_argument("heaanNN: 2^logSlots it has to be >= " + std::to_string(NN_INPUT));
}

BackendContext* setup_campaign(const CampaignArgs& args)
{
    NTL::SetSeed(NTL::ZZ(args.seed));
    std::srand(args.seed);
    auto ctx = std::make_unique<NNHeaanContext>(args.logN, args.logQ, kHammingWeight, args.seed);
    ctx->classifier   = true;
    ctx->baseline_tol = 1e-2;

    for (uint32_t i = 0; i < args.logSlots; ++i)
        ctx->scheme.addLeftRotKey(ctx->sk, 1L << i);

    // seed_input elige la imagen: es el "input" de la campania.
    ctx->model = load_nn_model(nn_data_dir(), args.seed_input);
    const NNWeights& w = ctx->model.weights;

    const long slots = 1L << args.logSlots;
    std::vector<double> buffer(slots);

    ctx->W1.resize(NN_HIDDEN);
    for (size_t j = 0; j < NN_HIDDEN; ++j) {
        std::fill(buffer.begin(), buffer.end(), 0.0);
        std::copy(w.W1[j].begin(), w.W1[j].end(), buffer.begin());
        ctx->W1[j] = ctx->cc.encode(buffer.data(), slots, args.logDelta);
    }

    ctx->W2.assign(NN_OUTPUT, std::vector<NTL::ZZX>(NN_HIDDEN));
    for (size_t o = 0; o < NN_OUTPUT; ++o)
        for (size_t h = 0; h < NN_HIDDEN; ++h) {
            std::fill(buffer.begin(), buffer.end(), w.W2[o][h]);
            ctx->W2[o][h] = ctx->cc.encode(buffer.data(), slots, args.logDelta);
        }

    return ctx.release();
}

void destroy_campaign(BackendContext* ctx)
{
    delete ctx;
}

void nn_set_image(BackendContext* bctx, size_t image_index)
{
    auto& model = static_cast<NNHeaanContext&>(*bctx).model;
    loadMnistNormRowByIndex(nn_data_dir() + "/mnist_test.csv", image_index, model.label, model.image);
    model.plain_logits = plain_forward(model.image, model.weights);
}

std::vector<double> get_reference_output(const BackendContext* bctx)
{
    return static_cast<const NNHeaanContext&>(*bctx).model.plain_logits;
}

IterationResult run_iteration(BackendContext* bctx, const CampaignArgs& args, Injector& inj)
{
    auto& ctx = static_cast<NNHeaanContext&>(*bctx);
    InjectorScope scope(inj, ctx.cc.N);
    const Site site = pick_site(args, inj);

    const long slots = 1L << args.logSlots;
    std::vector<std::complex<double>> arr(slots, {0.0, 0.0});
    for (size_t i = 0; i < ctx.model.image.size(); ++i) arr[i] = {ctx.model.image[i], 0.0};

    Plaintext plain = ctx.scheme.encode(arr.data(), slots, args.logDelta, args.logQ);
    if (inj.here(Stage::Encode)) client_flip(inj, plain.mx);

    Ciphertext c = ctx.scheme.encryptMsg(plain, ctx.seed);
    if (inj.here(Stage::EncryptC0)) client_flip(inj, c.bx);
    if (inj.here(Stage::EncryptC1)) client_flip(inj, c.ax);

    std::vector<Ciphertext> outs = forward(ctx, c, args, inj, site);

    // Los faults de salida van al logit de la clase correcta.
    const size_t target = ctx.model.label;
    if (inj.here(Stage::DecryptC0)) client_flip(inj, outs[target].bx);
    if (inj.here(Stage::DecryptC1)) client_flip(inj, outs[target].ax);

    IterationResult res;
    res.values.reserve(outs.size());
    for (size_t o = 0; o < outs.size(); ++o) {
        Plaintext dec = ctx.scheme.decryptMsg(ctx.sk, outs[o]);
        if (o == target && inj.here(Stage::Decode)) client_flip(inj, dec.mx);
        std::unique_ptr<std::complex<double>[]> v(ctx.scheme.decode(dec));
        res.values.push_back(v[0].real());
    }
    res.hidden_layer    = site.neuron;
    res.reduceSum_layer = site.rot;
    return res;
}
