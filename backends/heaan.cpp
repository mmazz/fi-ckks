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

void backend_prepare_args(CampaignArgs& args){
    args.library = "heaan";
    args.mult_depth = 0;
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
    Plaintext plain_clean;

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


    if (inj.here("encode")) client_flip(inj, plain.mx);

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
        c_clean = ctx.scheme.encryptMsg(plain_clean, ctx.seed);
    }
    if (has_op(args.ops, OpType::PMul)){
        if(args.isComplex){
            plain_clean =  ctx.cc.encode(baseInputComplex, baseSize, args.logDelta);
        } else {
            plain_clean =  ctx.cc.encode(baseInput, baseSize, args.logDelta);
        }
    }

    if (inj.here("encrypt_c0")) client_flip(inj, c.bx);
    if (inj.here("encrypt_c1")) client_flip(inj, c.ax);
    // ---- Server side: el pipeline ----
    std::array<uint32_t, kNumOpTypes> occ{};   // ocurrencias por tipo -> op_depth
    uint32_t n_rescale = 0;

    auto rescale = [&]() {
       const uint32_t r = n_rescale++;
       if (inj.here("rescale", r)) {
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
           if (inj.here("add", d)) {
               const FaultSpec& f = inj.spec();
               c = ctx.scheme.addBitFlip(c, c_clean, f.op_step, f.coeff, f.bit, f.amountBits);
           } else {
               c = ctx.scheme.add(c, c_clean);
           }
           break;

       case OpType::PMul:
           c = ctx.scheme.multByPoly(c, plain_clean.mx, args.logDelta);
           rescale();
           break;

       case OpType::Mul:
           if (inj.here("mul", d)) {
               const FaultSpec& f = inj.spec();
               c = ctx.scheme.multBitFlip(c, c_clean, f.op_step, f.coeff, f.bit, f.amountBits);
           } else if (inj.here("mul_asplos", d)) {
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
           if (inj.here("rot", d)) {
               const FaultSpec& f = inj.spec();
               c = ctx.scheme.leftRotateFastBitFlip(c, k, f.op_step, f.coeff, f.bit, f.amountBits);
           } else if (inj.here("rot_asplos", d)) {
               const FaultSpec& f = inj.spec();
               c = ctx.scheme.leftRotateFastBitFlipAsplos(c, k, f.op_step, f.coeff, f.bit, f.amountBits);
           } else {
               c = ctx.scheme.leftRotateFast(c, k);
           }
           break;
       }

    //cipher, logq, logQ, logT, logI=4
       case OpType::Boot:
           if (inj.here("boot", d)) {
               const FaultSpec& f = inj.spec();
               ctx.scheme.bootstrapAndEqualBitFlip(c, logq_boot, args.logQ, 4, 4, f.op_step, f.coeff, f.bit, f.amountBits);
           } else if (inj.here("boot_coeff", d) || inj.here("boot_eval", d) || inj.here("boot_slot", d)) {
               const FaultSpec& f = inj.spec();
               ctx.scheme.bootstrapAndEqualBitFlip_inside(c, logq_boot, args.logQ, 4, 4, f.stage, f.op_step, f.coeff, f.bit, f.amountBits);
           } else {
               ctx.scheme.bootstrapAndEqual(c, logq_boot, args.logQ, 4, 4);
           }
           break;
       }
    }

    // ---- Back to client side (despues de TODO el pipeline, incluido el boot) ----
    if (inj.here("decrypt_c0")) client_flip(inj, c.bx);
    if (inj.here("decrypt_c1")) client_flip(inj, c.ax);



    Plaintext decrypt_plain = ctx.scheme.decryptMsg(ctx.sk, c);

    if (inj.here("decode")) client_flip(inj, decrypt_plain.mx);

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

