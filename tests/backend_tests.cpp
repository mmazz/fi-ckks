// Tests del contrato de backend_interface.h. Se compila una vez por backend
// (fi_test_heaan, fi_test_openfhe): lo que se testea es igual para todos.
// Los parametros de la campania vienen por linea de comandos, como en fi_main.
#include "backend_interface.h"
#include "check.h"

#include <memory>
#include <string>
#include <vector>

using CtxPtr = std::unique_ptr<BackendContext, void (*)(BackendContext*)>;

static CampaignArgs g_args;   // lo llena main() con los flags de CTest

static CtxPtr make_ctx(const CampaignArgs& args)
{
    return CtxPtr(setup_campaign(args), destroy_campaign);
}

static std::vector<double> run_clean(BackendContext* ctx, const CampaignArgs& args)
{
    Injector inj = Injector::none();
    std::vector<double> values = run_iteration(ctx, args, inj).values;
    inj.finish();       // tira si hubo algun flip en una corrida limpia
    return values;
}

static FaultSpec fault(const CampaignArgs& args, Stage stage,
                       uint32_t op_step, uint32_t coeff, uint32_t bit)
{
    FaultSpec f;
    f.stage      = stage;
    f.op_depth   = 0;
    f.op_step    = op_step;
    f.limb       = 0;
    f.coeff      = coeff;
    f.bit        = bit;
    f.amountBits = args.amountBits;
    return f;
}
static std::vector<std::pair<Stage, uint32_t>> stages_to_probe(const CampaignArgs& args)
{
    std::vector<std::pair<Stage, uint32_t>> v = {
        {Stage::Encode, 0}, {Stage::EncryptC0, 0}, {Stage::EncryptC1, 0},
        {Stage::DecryptC0, 0}, {Stage::DecryptC1, 0},
    };
    if (args.library == "heaan")
        for (auto s : {std::pair<Stage, uint32_t>{Stage::Decode, 0}, {Stage::Add, 0}, {Stage::Add, 5},
                       {Stage::Mul, 0}, {Stage::Mul, 25}, {Stage::Rescale, 0},
                       {Stage::Rot, 0}, {Stage::Rot, 11}})
            v.push_back(s);
    if (args.library == "openfhe") {
        // Every in-operation site of the fork (fault-hook.h): add 0..5, mul 0..10.
        for (uint32_t k = 0; k < 6; ++k)  v.push_back({Stage::Add, k});
        for (uint32_t k = 0; k < 11; ++k) v.push_back({Stage::Mul, k});
    }
    return v;
}


// ------------------------------------------------------------------ //

// Misma seed, mismo resultado: dos corridas en el mismo contexto.
TEST(clean_run_is_deterministic)
{
    CtxPtr ctx = make_ctx(g_args);
    CHECK_EQ(run_clean(ctx.get(), g_args), run_clean(ctx.get(), g_args));
}

// Misma seed, mismo resultado: dos contextos distintos (claves incluidas).
TEST(same_seed_gives_same_output)
{
    CtxPtr a = make_ctx(g_args);
    CtxPtr b = make_ctx(g_args);
    CHECK_EQ(run_clean(a.get(), g_args), run_clean(b.get(), g_args));
}

// Otra seed, otro ciphertext: si esto falla, la seed no controla el ruido.
TEST(other_seed_gives_other_output)
{
    CampaignArgs other = g_args;
    other.seed += 1;
    CtxPtr a = make_ctx(g_args);
    CtxPtr b = make_ctx(other);
    CHECK_NE(run_clean(a.get(), g_args), run_clean(b.get(), other));
}

// El golden CKKS tiene que coincidir con la cuenta en claro.
TEST(golden_matches_plain)
{
    CtxPtr ctx = make_ctx(g_args);
    const std::vector<double> ckks = run_clean(ctx.get(), g_args);
    const std::vector<double> plain = get_reference_output(ctx.get());
    CHECK_EQ(ckks.size(), plain.size());
    CKKSAccuracyMetrics m = EvaluateCKKSAccuracy(plain, ckks);
    CHECK(m.l2_rel_error < 1e-3);
}

// Todos los (stage, op_step) de la lista se alcanzan, y el probe mide algo razonable.
TEST(probe_reaches_every_stage)
{
    CtxPtr ctx = make_ctx(g_args);
    for (const auto& [stage, step] : stages_to_probe(g_args)) {
        Injector probe = Injector::probe(stage, 0, step);
        run_iteration(ctx.get(), g_args, probe);
        probe.finish();                                  // tira "never reach" si no llego
        CHECK(probe.probed_limbs() >= 1);
        CHECK(probe.probed_coeff_bits() > 0);
    }
}

// Un punto de inyeccion que no existe: en HEAAN un op_step fuera de rango,
// en OpenFHE un stage interno que todavia no esta implementado.
// // An injection point that does not exist: an op_step out of range.
TEST(probe_rejects_unreachable_point)
{
    CtxPtr ctx = make_ctx(g_args);
    Injector probe = Injector::probe(Stage::Mul, 0, 999);
    run_iteration(ctx.get(), g_args, probe);
    CHECK_THROWS(probe.finish());
}

// op_depth fuera del pipeline tampoco se alcanza (el pipeline tiene una sola mult).
TEST(probe_rejects_unreachable_depth)
{
    CtxPtr ctx = make_ctx(g_args);
    Injector probe = Injector::probe(Stage::EncryptC0, 5, 0);
    run_iteration(ctx.get(), g_args, probe);
    CHECK_THROWS(probe.finish());
}

// Un fault alto en el ciphertext cambia la salida.
TEST(fault_changes_output)
{
    CtxPtr ctx = make_ctx(g_args);
    const std::vector<double> golden = run_clean(ctx.get(), g_args);

    Injector inj = Injector::fault(fault(g_args, Stage::EncryptC0, 0, 1, g_args.logDelta));
    std::vector<double> values = run_iteration(ctx.get(), g_args, inj).values;
    inj.finish();                                        // valida cantidad de bits y coeficientes
    CHECK_NE(values, golden);
}

// Despues de inyectar, el estado compartido (claves, contexto) tiene que quedar limpio.
TEST(fault_is_transient)
{
    CtxPtr ctx = make_ctx(g_args);
    const std::vector<double> golden = run_clean(ctx.get(), g_args);

    for (const auto& [stage, step] : stages_to_probe(g_args)) {
        Injector inj = Injector::fault(fault(g_args, stage, step, 1, g_args.logDelta));
        run_iteration(ctx.get(), g_args, inj);
        inj.finish();
        CHECK_EQ(run_clean(ctx.get(), g_args), golden);
    }
}

// amountBits > 1 flipea exactamente esa cantidad de bits: lo verifica Injector::finish().
TEST(amount_bits_flips_exactly_n)
{
    CampaignArgs args = g_args;
    args.amountBits = 3;
    CtxPtr ctx = make_ctx(args);
    Injector inj = Injector::fault(fault(args, Stage::EncryptC1, 0, 2, args.logDelta));
    run_iteration(ctx.get(), args, inj);
    inj.finish();
}

// El mismo fault, dos veces, da el mismo resultado.
TEST(same_fault_gives_same_output)
{
    CtxPtr ctx = make_ctx(g_args);
    std::vector<std::vector<double>> out;
    for (int i = 0; i < 2; ++i) {
        Injector inj = Injector::fault(fault(g_args, Stage::EncryptC0, 0, 3, g_args.logDelta + 1));
        out.push_back(run_iteration(ctx.get(), g_args, inj).values);
        inj.finish();
    }
    CHECK_EQ(out[0], out[1]);
}

int main(int argc, char** argv)
{
    try {
        g_args = parse_arguments(argc, argv);
        backend_prepare_args(g_args);
        validateArgs(g_args);
    } catch (const std::exception& e) {
        std::cerr << "ERROR in arguments: " << e.what() << '\n';
        return 2;
    }
    std::cout << "== backend " << g_args.library << " [" << g_args.pipeline << "] ==\n";
    return check::run_all();
}
