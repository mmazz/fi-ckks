#include "backend_interface.h"
#include "logger.h"
#include "registry.h"
#include <algorithm>
#include <chrono>
#include <iostream>
#include <memory>

struct Sink {
    CampaignLogger&     logger;
    VectorLogger*       vlogger;   // nullptr si no hay --saveVectors
    std::vector<double> norms;
    uint32_t num_limbs = 1;
    uint64_t iters = 0;
};

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

// Corrida sin fault. finish() verifica que no se haya flipeado nada.
static std::vector<double> run_clean(BackendContext* ctx, const CampaignArgs& args)
{
    Injector inj = Injector::none();
    std::vector<double> values = run_iteration(ctx, args, inj).values;
    inj.finish();
    return values;
}

// Si el golden cambio despues de inyectar, algun estado compartido
// (claves, tablas, contexto) quedo corrupto: el fault no fue transitorio.
static void check_transient(BackendContext* ctx, const CampaignArgs& args,
                            const std::vector<double>& ckks_golden)
{
    if (run_clean(ctx, args) != ckks_golden)
        throw std::runtime_error("estado contaminado: el golden cambio despues de inyectar");
}

static bool baseline_ok(const CampaignArgs& args, const std::vector<double>& plain_golden, const std::vector<double>& ckks_golden){
    CKKSAccuracyMetrics baseline_metrics = EvaluateCKKSAccuracy(plain_golden, ckks_golden);
    double tol= has_op(args.ops, OpType::Boot) ? 1e-3 : 1e-4;
    bool res = AcceptCKKSResult(baseline_metrics, tol, tol);
    if(!res)
        printBaselineComparison(
            args,
            plain_golden,
            ckks_golden,
            baseline_metrics
        );
    return res;
}
static void run_one(BackendContext* ctx, CampaignArgs& args,
                    const std::vector<double>& ckks_golden, const FaultSpec& f, Sink& s)
{
    Injector inj = Injector::fault(f);
    IterationResult res = run_iteration(ctx, args, inj);
    inj.finish();
    if (++s.iters % 1000 == 0) check_transient(ctx, args, ckks_golden);

    CKKSAccuracyMetrics  exp_metrics = EvaluateCKKSAccuracy(ckks_golden, res.values);

    auto slot_stats = categorize_slots_relative(ckks_golden, res.values, ckks_golden.size());
    s.logger.log(f.limb,
            f.coeff,
            f.bit,
            exp_metrics.l2_abs_error,     // ||error||_2 
            exp_metrics.l2_rel_error,     // ||error||_2 / ||golden||_2
            exp_metrics.linf_abs_error,
            exp_metrics.linf_rel_error,
            res.detected,
            slot_stats
        );
    if (s.vlogger) s.vlogger->log(f.limb, f.coeff, f.bit, ckks_golden, res.values);

    s.norms.push_back(exp_metrics.l2_rel_error);
}

static void run_exhaustive(BackendContext* ctx, CampaignArgs& args, const std::vector<double>& ckks_golden, Sink& s){
    
    uint32_t num_limb = s.num_limbs;
    uint32_t N = (1U<<args.logN);
    
    for (size_t limb=0; limb<num_limb; limb++)
    {
        for (size_t coeff=0; coeff<N; coeff++)
        {
            for(size_t bit=0; bit + args.amountBits <= args.bitsPerCoeff; bit++)
            {                
                run_one(ctx, args, ckks_golden,  make_fault(args, limb, coeff, bit), s);
            }
        }
    }
}

static void run_random(BackendContext* ctx, CampaignArgs& args, const std::vector<double>& ckks_golden, Sink& s){
    std::vector<uint32_t> bits_to_flip = bitsToFlipGenerator(args); 
    uint32_t N = (1U<<args.logN);

    uint32_t num_limb = s.num_limbs;
    for (size_t sample=0; sample<args.numSamples; sample++)
    {
        uint32_t limb = random_int(0, num_limb - 1);
        uint32_t coeff = random_int(0, N-1);
        for(size_t bitIndex=0; bitIndex< bits_to_flip.size(); bitIndex++)
        {                
            uint32_t bit = bits_to_flip[bitIndex];
            run_one(ctx, args, ckks_golden, make_fault(args, limb, coeff, bit), s);
        }
    }
}


int main(int argc, char** argv) {
    try{
        CampaignArgs args = parse_arguments(argc, argv);
        backend_prepare_args(args);
        validateArgs(args);
        if(args.isExhaustive)
            args.numSamples = 0;

        BackendContext* ctx = setup_campaign(args);
        const std::vector<double> ckks_golden  = run_clean(ctx, args); //run_iteration(ctx, args, std::nullopt).values;
        const std::vector<double> plain_golden = get_reference_output(ctx);
        if (!baseline_ok(args, plain_golden, ckks_golden)) { 
            destroy_campaign(ctx); 
            return 1;
        }

         Injector probe = Injector::probe(args.stage, args.op_depth, args.op_step);
         run_iteration(ctx, args, probe);
         probe.finish();
         if (probe.probed_coeff_bits() > args.bitsPerCoeff)
             std::cerr << "WARNING: los coeficientes en '" << args.stage << "' tienen hasta "
                       << probe.probed_coeff_bits() << " bits y bitsPerCoeff=" << args.bitsPerCoeff << "\n";
         check_transient(ctx, args, ckks_golden);

        CampaignRegistry registry(args);
        if (registry.already_done){
            std::cout << "Campaing already done" << std::endl;
            return 0;
        }
        seed_rng(args.seed, args.seed_input);
        CampaignLogger logger(registry.campaign_id, args.results_dir + "/data");
        std::unique_ptr<VectorLogger> vlogger;
        if (args.saveVectors)
            vlogger = std::make_unique<VectorLogger>(registry.campaign_id, args.results_dir + "/vectors",
                                                     args.logSlots + (args.isComplex ? 1 : 0));
        Sink s{logger, vlogger.get(), {}, probe.probed_limbs()};

        auto start_time = std::chrono::steady_clock::now();

        if(args.isExhaustive)
            run_exhaustive(ctx, args,  ckks_golden,  s);
        else
            run_random(ctx, args,  ckks_golden,  s);

        check_transient(ctx, args, ckks_golden);
        auto end_time = std::chrono::steady_clock::now();
        std::chrono::seconds duration = std::chrono::duration_cast<std::chrono::seconds>(end_time - start_time);
        auto minutes = std::chrono::duration_cast<std::chrono::minutes>(duration);
        uint64_t mins = minutes.count();
        logger.close();
        if (vlogger) vlogger->close();
        double p95 = 0, p99 = 0;
        if(!s.norms.empty()){
            std::sort(s.norms.begin(), s.norms.end());
            p95 = percentile(s.norms, 0.95);
            p99 = percentile(s.norms, 0.99);
        }


        registry.register_end({registry.campaign_id, logger.total(), logger.sdc(), mins, p95, p99, timestamp_now()});
        destroy_campaign(ctx);
        return 0;
    } catch (const std::exception& e) { 
        std::cerr << "ERROR: " << e.what() << '\n'; return 1; 
    }
}
