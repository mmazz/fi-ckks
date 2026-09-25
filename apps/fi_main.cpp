#include "backend_interface.h"
#include "logger.h"
#include "registry.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iostream>
#include <memory>
#include <set>

using CtxPtr = std::unique_ptr<BackendContext, void (*)(BackendContext*)>;

struct Sink {
    CampaignLogger&     logger;
    VectorLogger*       vlogger;        // nullptr si no hay --saveVectors
    std::vector<double> norms;
    uint32_t num_limbs    = 1;
    bool     classifier   = false;
    size_t   golden_class = 0;          // argmax del golden CKKS (solo si classifier)
    uint64_t iters        = 0;
};

static size_t argmax(const std::vector<double>& v)
{
    return size_t(std::max_element(v.begin(), v.end()) - v.begin());
}

// Arma el fault de una iteracion. Todo lo que no es (limb, coeff, bit) sale de args.
static FaultSpec make_fault(const CampaignArgs& args, uint32_t limb, uint32_t coeff, uint32_t bit)
{
    if (bit + args.amountBits > args.bitsPerCoeff)
        throw std::out_of_range("make_fault: bit + amountBits > bitsPerCoeff (bit=" +
                                std::to_string(bit) + ", amountBits=" +
                                std::to_string(args.amountBits) + ")");
    FaultSpec f;
    f.stage      = args.stage;
    f.op_depth   = args.op_depth;
    f.op_step    = args.op_step;
    f.limb       = limb;
    f.coeff      = coeff;
    f.bit        = bit;
    f.amountBits = args.amountBits;
    return f;
}

static std::vector<double> run_clean(BackendContext* ctx, const CampaignArgs& args)
{
    Injector inj = Injector::none();
    std::vector<double> values = run_iteration(ctx, args, inj).values;
    inj.finish();
    return values;
}


static void check_transient(BackendContext* ctx, const CampaignArgs& args,
                            const std::vector<double>& ckks_golden)
{
    if (run_clean(ctx, args) != ckks_golden)
        throw std::runtime_error("contaminated state: the golden has changes after inject");
}

static bool baseline_ok(const BackendContext& ctx, const CampaignArgs& args,
                        const std::vector<double>& plain_golden, const std::vector<double>& ckks_golden)
{
    CKKSAccuracyMetrics m = EvaluateCKKSAccuracy(plain_golden, ckks_golden);
    bool ok;
    if (ctx.classifier) {
        ok = argmax(plain_golden) == argmax(ckks_golden) && m.l2_rel_error <= ctx.baseline_tol;
    } else {
        double scale = 0.0;
        for (double g : plain_golden) scale = std::max(scale, std::abs(g));
        double tol = ctx.baseline_tol > 0 ? ctx.baseline_tol
            : (has_op(args.ops, OpType::Boot) ? 1e-3 : 1e-4);
        ok = AcceptCKKSResult(m, tol, tol * std::max(1.0, scale));
    }
    if (!ok)
        printBaselineComparison(args, plain_golden, ckks_golden, m);
    return ok;
}

static void run_one(BackendContext* ctx, CampaignArgs& args,
                    const std::vector<double>& ckks_golden, const FaultSpec& f, Sink& s)
{
    Injector inj = Injector::fault(f);
    IterationResult res = run_iteration(ctx, args, inj);
    inj.finish();
    if (++s.iters % 1000 == 0) check_transient(ctx, args, ckks_golden);

    const CKKSAccuracyMetrics m = EvaluateCKKSAccuracy(ckks_golden, res.values);

    BitflipResult r;
    r.limb            = f.limb;
    r.coeff           = f.coeff;
    r.bit             = f.bit;
    r.l2_abs          = m.l2_abs_error;      // ||error||_2
    r.l2_rel          = m.l2_rel_error;      // ||error||_2 / ||golden||_2
    r.linf_abs        = m.linf_abs_error;
    r.linf_rel        = m.linf_rel_error;
    r.detected        = res.detected;
    r.stats           = categorize_slots_relative(ckks_golden, res.values, ckks_golden.size());
    r.hidden_layer    = res.hidden_layer;
    r.reduceSum_layer = res.reduceSum_layer;
    // A NaN/inf logit makes argmax meaningless (NaN never compares greater), so a destroyed
    // output could land on the golden class and count as correct. Any non-finite logit is
    // a misclassification.
    const bool finite_out = std::all_of(res.values.begin(), res.values.end(),
                                        [](double x) { return std::isfinite(x); });
    r.misclassified   = s.classifier && (!finite_out || argmax(res.values) != s.golden_class);
    r.out_of_range    = inj.out_of_range();
    s.logger.log(r);

    if (s.vlogger) s.vlogger->log(f.limb, f.coeff, f.bit, ckks_golden, res.values);

    // Un fault puede dar inf/NaN; no sirven para percentiles (y NaN rompe std::sort).
    if (std::isfinite(m.l2_rel_error)) s.norms.push_back(m.l2_rel_error);
}

static void run_exhaustive(BackendContext* ctx, CampaignArgs& args, const std::vector<double>& ckks_golden, Sink& s)
{
    const uint32_t N = (1U << args.logN);
    for (uint32_t limb = 0; limb < s.num_limbs; limb++)
        for (uint32_t coeff = 0; coeff < N; coeff++)
            for (uint32_t bit = 0; bit + args.amountBits <= args.bitsPerCoeff; bit++)
                run_one(ctx, args, ckks_golden, make_fault(args, limb, coeff, bit), s);
}

static void run_random(BackendContext* ctx, CampaignArgs& args, const std::vector<double>& ckks_golden, Sink& s)
{
    const uint32_t N = (1U << args.logN);

    // Con amountBits > 1 las posiciones mas altas no entran: se descartan.
    std::vector<uint32_t> bits_to_flip;
    for (uint32_t bit : bitsToFlipGenerator(args))
        if (bit + args.amountBits <= args.bitsPerCoeff) bits_to_flip.push_back(bit);
    std::set<std::pair<uint32_t, uint32_t>> seen;
    for (uint32_t sample = 0; sample < args.numSamples; sample++) {
        uint32_t limb = 0, coeff = 0;
        // Rejection sampling: never sample the same coefficient twice. main() already
        // checked numSamples <= num_limbs * N, so this always terminates.
        do {
            limb  = random_int(0, s.num_limbs - 1);
            coeff = random_int(0, N - 1);
        } while (!seen.insert({limb, coeff}).second);

        for (uint32_t bit : bits_to_flip)
            run_one(ctx, args, ckks_golden, make_fault(args, limb, coeff, bit), s);
    }

}

int main(int argc, char** argv)
{
    try {
        CampaignArgs args = parse_arguments(argc, argv);
        backend_prepare_args(args);
        validateArgs(args);
        if (args.stage == Stage::None)
            throw std::invalid_argument("must choose a --stage (see --help); "
                                        "'none' injects nowhere");
        if (args.isExhaustive)
            args.numSamples = 0;
        // Skip before paying for setup + baseline + probe (a full network run each).
        // Read-only: nothing is registered here, so an invalid config still leaves
        // campaigns_start.csv untouched.
        if (CampaignRegistry::is_already_done(args)) {
            std::cout << "Campaign already done" << std::endl;
            return 0;
        }
        CtxPtr ctx(setup_campaign(args), destroy_campaign);
        const std::vector<double> ckks_golden  = run_clean(ctx.get(), args);
        const std::vector<double> plain_golden = get_reference_output(ctx.get());
        if (!baseline_ok(*ctx, args, plain_golden, ckks_golden))
            return 1;

        Injector probe = Injector::probe(args.stage, args.op_depth, args.op_step);
        run_iteration(ctx.get(), args, probe);
        probe.finish();
        const uint32_t real_bits = probe.probed_coeff_bits();
        if (real_bits > args.bitsPerCoeff)
            std::cerr << "WARNING: at stage '" << to_string(args.stage) << "' the registers are up to "
                      << real_bits << " bits wide and bitsPerCoeff=" << args.bitsPerCoeff
                      << ": the sweep is incomplete\n";
        if (args.bitsPerCoeff > real_bits)
            std::cerr << "INFO: at stage '" << to_string(args.stage) << "' the probe measured "
                      << real_bits << " bits and bitsPerCoeff=" << args.bitsPerCoeff
                      << ": flips at bit >= " << real_bits << " may leave the coefficient outside"
                         " its modulus. They are injected anyway (that is what the hardware does);"
                         " OpenFHE marks them in the out_of_range column, HEAAN does not\n";
        // Before registering: a random campaign cannot ask for more coefficients than
        // exist, or run_random would repeat one (duplicate rows, double weight when the
        // seeds are averaged). Checked here so an invalid config leaves no row behind.
        const uint64_t available = uint64_t(probe.probed_limbs()) << args.logN;
        if (!args.isExhaustive && args.numSamples > available)
            throw std::invalid_argument("numSamples (" + std::to_string(args.numSamples) +
                                        ") > available (limb, coeff) pairs (" +
                                        std::to_string(available) + ")");
        check_transient(ctx.get(), args, ckks_golden);

        CampaignRegistry registry(args);
        if (registry.already_done) {
            std::cout << "Campaign already done" << std::endl;
            return 0;
        }
        seed_rng(args.seed, args.seed_input);
        CampaignLogger logger(registry.campaign_id, args.results_dir + "/data");
        std::unique_ptr<VectorLogger> vlogger;
        if (args.saveVectors)
            vlogger = std::make_unique<VectorLogger>(registry.campaign_id, args.results_dir + "/vectors",
                                                     ckks_golden.size());
        Sink s{logger, vlogger.get()};
        s.num_limbs    = probe.probed_limbs();
        s.classifier   = ctx->classifier;
        s.golden_class = argmax(ckks_golden);

        auto start_time = std::chrono::steady_clock::now();

        if (args.isExhaustive)
            run_exhaustive(ctx.get(), args, ckks_golden, s);
        else
            run_random(ctx.get(), args, ckks_golden, s);

        check_transient(ctx.get(), args, ckks_golden);
        auto end_time = std::chrono::steady_clock::now();
        uint64_t mins = std::chrono::duration_cast<std::chrono::minutes>(end_time - start_time).count();
        logger.close();

        if (vlogger) vlogger->close();

        double p95 = 0, p99 = 0;
        if (!s.norms.empty()) {
            std::sort(s.norms.begin(), s.norms.end());
            p95 = percentile(s.norms, 0.95);
            p99 = percentile(s.norms, 0.99);
        }

        registry.register_end({registry.campaign_id, logger.total(), logger.detected(), mins, p95, p99});
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << '\n';
        return 1;
    }
}
