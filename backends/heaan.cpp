#include "backend_interface.h"
#include "heaan_inject.h"

// HEAAN-only includes
#include "HEAAN.h"
#include <NTL/ZZ.h>
#include <cstdint>
#include <vector>
#include <complex>
#include <algorithm>
#include <array> 
#include <set>

const size_t MAX_H = 64;
/*
 const long nu   = (7*logT + 3) / 3;      // 8 para logT=3, 10 para logT=4
 const long logq = logDelta + nu;         // 38 con logDelta=30, logT=3
 *
 */
struct HEAANContext : BackendContext {
    Context cc;
    SecretKey sk;
    Scheme scheme;

    std::vector<double> baseInput;
    std::vector<double> goldenOutput;
    std::vector<std::complex<double>> baseInputComplex;
    std::vector<std::complex<double>> goldenOutputComplex;
    NTL::ZZ seed;
    bool isComplex = false;

    HEAANContext(
        uint32_t logN,
        uint32_t logQ,
        uint32_t h,
        uint64_t seed_
    )
        : cc(logN, logQ)
        , sk(logN, h)
        , scheme(sk, cc)   // ← ahora sí
        , seed(NTL::ZZ(seed_))
    {}

    HEAANContext(const HEAANContext&) = delete;
    HEAANContext& operator=(const HEAANContext&) = delete;
};

std::vector<double> get_reference_output(const BackendContext* bctx)
{
    auto& ctx = static_cast<const HEAANContext&>(*bctx);
    if(ctx.isComplex){
        const auto& g = ctx.goldenOutputComplex;
        const size_t n = g.size();

        std::vector<double> out(2 * n);

        for (size_t i = 0; i < n; ++i) {
            out[i]     = g[i].real();
            out[i + n] = g[i].imag();
        }
        return out;
    }

    return ctx.goldenOutput;
}

void backend_prepare_args(CampaignArgs& args)
{
    args.library    = "heaan";
    args.mult_depth = 0;
    args.withNTT   = false;        // OpenFHE only
    args.scaleTech = "none";       // OpenFHE only
    args.dnum      = 0;            // OpenFHE only
    // Each level-consuming op costs logDelta bits of logq, and bootstrapping needs the
    // ciphertext to still be above logDelta+10 (the logq we hand to bootstrapAndEqual).
    // Without this check HEAAN indexes qpows[] with a negative exponent.
    const long logq_boot = long(args.logDelta) + 10;
    long logq = long(args.logQ);
    for (const Op& op : args.ops) {
        if (op.type == OpType::Boot) {
            if (logq < logq_boot)
                throw std::invalid_argument(
                    "heaan: not enough modulus left for 'boot' (logq=" + std::to_string(logq) +
                    " < logDelta+10=" + std::to_string(logq_boot) + ")");
            logq = long(args.logQ);          // bootstrapping restores the chain
            continue;
        }
        if (is_mult(op.type)) logq -= long(args.logDelta);
        if (logq <= 0)
            throw std::invalid_argument(
                "heaan: the pipeline needs more than logQ=" + std::to_string(args.logQ) +
                " with logDelta=" + std::to_string(args.logDelta));
    }
}

BackendContext* setup_campaign(const CampaignArgs& args)
{
    long logq_boot = (long)args.logDelta+10;
    long h;
    uint64_t N = 1 << args.logN;
    if (args.logN > 10)
        h = MAX_H;
    else
        h = std::max<long>(4,N/64);
    NTL::SetSeed(NTL::ZZ(args.seed));
    auto* ctx = new HEAANContext(args.logN, args.logQ, h, args.seed);
    std::srand(args.seed);
    if (has_op(args.ops, OpType::Boot))
       ctx->scheme.addBootKey(ctx->sk, args.logSlots, logq_boot + 4);

    std::set<long> rots;
    for (const Op& op : args.ops)
       if (op.type == OpType::Rot) rots.insert(long(op.param));
    for (long r : rots)
       ctx->scheme.addLeftRotKey(ctx->sk, r);
    if(args.isComplex>0){
        compute_plain_io(args, ctx->baseInputComplex, ctx->goldenOutputComplex);
        ctx->isComplex = true;
    } else{
        compute_plain_io(args, ctx->baseInput, ctx->goldenOutput);
    }

    return ctx;
}


IterationResult run_iteration(
    BackendContext* bctx,
    const CampaignArgs& args, Injector& inj
    )
    {

    auto& ctx = static_cast<HEAANContext&>(*bctx);
    InjectorScope scope(inj, ctx.cc.N);
    long logq_boot = (long)args.logDelta + 10;
    auto baseInput = ctx.baseInput.data();
    auto baseSize  = ctx.baseInput.size();
    auto baseInputComplex = ctx.baseInputComplex.data();

    if(args.isComplex){
        baseSize = ctx.baseInputComplex.size();
    }

    Plaintext plain;
    Plaintext plain_clean;   // operando de add/mul: se cifra, necesita logp/logq de verdad
    NTL::ZZX  pmul_poly;     // operando de pmul: es un polinomio pelado, NO un Plaintext

    if(args.isComplex>0){
        plain = ctx.scheme.encode(
            baseInputComplex,
            baseSize,
            args.logDelta,
            args.logQ
        );
    } else{
        plain = ctx.scheme.encode(
            baseInput,
            baseSize,
            args.logDelta,
            args.logQ
        );
    }


    if (inj.here(Stage::Encode)) client_flip(inj, plain.mx);

    Ciphertext c = ctx.scheme.encryptMsg(plain, ctx.seed);
    Ciphertext c_clean;
    if (has_op(args.ops, OpType::Add) || has_op(args.ops, OpType::Mul)){
        if(args.isComplex){
            plain_clean =  ctx.scheme.encode(baseInputComplex,
                                baseSize,
                                args.logDelta,
                                args.logQ
                            );
        } else {
            plain_clean =  ctx.scheme.encode(baseInput,
                                baseSize,
                                args.logDelta,
                                args.logQ
                            );
        }
        // So we are not then adding or mul the exactly same cipher, rather than a cipher with the same message
        c_clean = ctx.scheme.encryptMsg(plain_clean, ctx.seed+1);
    }

    if (has_op(args.ops, OpType::PMul)){
        // Context::encode devuelve ZZX. Asignarlo a un Plaintext compilaba (el ctor no es
        // explicit) y dejaba logp=0/logq=0 en silencio; guardamos el ZZX y listo.
        if(args.isComplex){
            pmul_poly =  ctx.cc.encode(baseInputComplex, baseSize, args.logDelta);
        } else {
            pmul_poly =  ctx.cc.encode(baseInput, baseSize, args.logDelta);
        }
    }
    if (inj.here(Stage::EncryptC0)) client_flip(inj, c.bx);
    if (inj.here(Stage::EncryptC1)) client_flip(inj, c.ax);
    // ---- Server side: el pipeline ----
    std::array<uint32_t, kNumOpTypes> occ{};   // ocurrencias por tipo -> op_depth
    // c_clean se cifro a logQ y c va bajando con cada rescale. Ring2Utils::add usa AddMod
    // (una sola resta condicional), asi que sumar un operando de modulo mas grande deja
    // coeficientes sin reducir: el resultado decodifica bien igual, pero el registro queda
    // con el ancho de bits del modulo viejo y el eje "bit" de las inyecciones posteriores
    // deja de significar lo mismo. Bajamos c_clean al nivel de c antes de cada op binaria.
    auto align_clean = [&]() {
       if (c_clean.logq > c.logq) ctx.scheme.modDownToAndEqual(c_clean, c.logq);
    };

    uint32_t n_rescale = 0;

    auto rescale = [&]() {
       const uint32_t r = n_rescale++;
       if (inj.here(Stage::Rescale, r)) {
           const FaultSpec& f = inj.spec();
           ctx.scheme.reScaleByAndEqualBitFlip(c, args.logDelta, f.op_step, f.coeff, f.bit, f.amountBits);
       } else {
           ctx.scheme.reScaleByAndEqual(c, args.logDelta);
       }
    };

    for (const Op& op : args.ops) {
       const uint32_t d = occ[size_t(op.type)]++;
       switch (op.type) {
       case OpType::Add:
           align_clean();
           if (inj.here(Stage::Add, d)) {
               const FaultSpec& f = inj.spec();
               c = ctx.scheme.addBitFlip(c, c_clean, f.op_step, f.coeff, f.bit, f.amountBits);
           } else {
               c = ctx.scheme.add(c, c_clean);
           }
           break;

       case OpType::PMul:
           c = ctx.scheme.multByPoly(c, pmul_poly, args.logDelta);
           rescale();
           break;

       case OpType::Mul:
           align_clean();
           if (inj.here(Stage::Mul, d)) {
               const FaultSpec& f = inj.spec();
               c = ctx.scheme.multBitFlip(c, c_clean, f.op_step, f.coeff, f.bit, f.amountBits);
           } else if (inj.here(Stage::MulAsplos, d)) {
               const FaultSpec& f = inj.spec();
               Ciphertext operand = c_clean;
               c = ctx.scheme.multBitFlipAsplos(c, operand, f.op_step, f.coeff, f.bit, f.amountBits);
           } else {
               c = ctx.scheme.mult(c, c_clean);
           }
           rescale();
           break;

       case OpType::Scalar:
           c = ctx.scheme.multByConst(c, op.param, args.logDelta);
           rescale();
           break;

       case OpType::Rot: {
           const long k = long(op.param);
           if (inj.here(Stage::Rot, d)) {
               const FaultSpec& f = inj.spec();
               c = ctx.scheme.leftRotateFastBitFlip(c, k, f.op_step, f.coeff, f.bit, f.amountBits);
           } else if (inj.here(Stage::RotAsplos, d)) {
               const FaultSpec& f = inj.spec();
               c = ctx.scheme.leftRotateFastBitFlipAsplos(c, k, f.op_step, f.coeff, f.bit, f.amountBits);
           } else {
               c = ctx.scheme.leftRotateFast(c, k);
           }
           break;
       }

    //cipher, logq, logQ, logT, logI=4
       case OpType::Boot:
           if (inj.here(Stage::Boot, d)) {
               const FaultSpec& f = inj.spec();
               ctx.scheme.bootstrapAndEqualBitFlip(c, logq_boot, args.logQ, 4, 4, f.op_step, f.coeff, f.bit, f.amountBits);
           } else if (inj.here(Stage::BootCoeff, d) || inj.here(Stage::BootSlot, d) || inj.here(Stage::BootEval, d)) {
               const FaultSpec& f = inj.spec();
               ctx.scheme.bootstrapAndEqualBitFlip_inside(c, logq_boot, args.logQ, 4, 4, to_string(f.stage), f.op_step, f.coeff, f.bit, f.amountBits);
           } else {
               ctx.scheme.bootstrapAndEqual(c, logq_boot, args.logQ, 4, 4);
           }
           break;
       }
    }

    // ---- Back to client side (despues de TODO el pipeline, incluido el boot) ----
    if (inj.here(Stage::DecryptC0)) client_flip(inj, c.bx);
    if (inj.here(Stage::DecryptC1)) client_flip(inj, c.ax);



    Plaintext decrypt_plain = ctx.scheme.decryptMsg(ctx.sk, c);

    if (inj.here(Stage::Decode)) client_flip(inj, decrypt_plain.mx);

    complex<double>* decoded = ctx.scheme.decode(decrypt_plain);

    IterationResult res;
    const size_t slots = 1u << args.logSlots;
    if(args.isComplex>0){
        res.values.resize(2*slots);

        for (size_t i = 0; i < slots; i++) {
            res.values[i] = decoded[i].real();
            res.values[i+slots] = decoded[i].imag();
        }

    } else {
        res.values.resize(slots);

        for (size_t i = 0; i < slots; i++) {
            res.values[i] = decoded[i].real();
        }

    }

    delete[] decoded;

    res.detected = false;

    return res;
}


void destroy_campaign(BackendContext* ctx) {
    delete ctx;
}

