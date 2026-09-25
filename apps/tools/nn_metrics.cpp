// Metricas de la red SIN inyectar faults: accuracy, precision/recall/F1 por clase y
// macro-F1, en claro y cifrado, mas el error de los logits entre ambos.
// Se compila una vez por backend: fi_nn_metrics_heaan y fi_nn_metrics_openfhe.
//
//   fi_nn_metrics_heaan --images 50 --logN 12 --logQ 220 --logDelta 30 --logSlots 10 --seed 1
//
// --images N (o --first-image K) son de esta herramienta; el resto de los flags son los
// de una campania. Las imagenes salen de <FI_NN_DATA>/mnist_test.csv.
#include "backend_interface.h"
#include "mnist.h"
#include "nn_workload.h"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

namespace {

using CtxPtr = std::unique_ptr<BackendContext, void (*)(BackendContext*)>;

size_t argmax(const std::vector<double>& v)
{
    return size_t(std::max_element(v.begin(), v.end()) - v.begin());
}

// Saca --images / --first-image de argv y deja el resto para parse_arguments.
std::vector<char*> extract_options(int argc, char** argv, size_t& images, size_t& first)
{
    std::vector<char*> rest;
    for (int i = 0; i < argc; ++i) {
        const std::string arg = argv[i];
        if ((arg == "--images" || arg == "--first-image") && i + 1 < argc) {
            (arg == "--images" ? images : first) = std::stoul(argv[++i]);
        } else {
            rest.push_back(argv[i]);
        }
    }
    return rest;
}

struct Metrics {
    double accuracy = 0;
    double macro_f1 = 0;
    std::vector<double> f1 = std::vector<double>(NN_OUTPUT, 0.0);
    std::vector<size_t> support = std::vector<size_t>(NN_OUTPUT, 0);
};

// Precision, recall y F1 por clase (one-vs-rest), y su promedio sin ponderar.
Metrics evaluate(const std::vector<size_t>& labels, const std::vector<size_t>& preds)
{
    Metrics m;
    size_t hits = 0;
    std::vector<size_t> tp(NN_OUTPUT, 0), fp(NN_OUTPUT, 0), fn(NN_OUTPUT, 0);
    for (size_t i = 0; i < labels.size(); ++i) {
        m.support[labels[i]]++;
        if (preds[i] == labels[i]) { tp[labels[i]]++; hits++; }
        else                       { fp[preds[i]]++; fn[labels[i]]++; }
    }
    m.accuracy = labels.empty() ? 0.0 : double(hits) / double(labels.size());

    size_t classes = 0;
    for (size_t c = 0; c < NN_OUTPUT; ++c) {
        const double prec = tp[c] + fp[c] ? double(tp[c]) / double(tp[c] + fp[c]) : 0.0;
        const double rec  = tp[c] + fn[c] ? double(tp[c]) / double(tp[c] + fn[c]) : 0.0;
        m.f1[c] = prec + rec > 0 ? 2 * prec * rec / (prec + rec) : 0.0;
        if (m.support[c]) { m.macro_f1 += m.f1[c]; classes++; }
    }
    if (classes) m.macro_f1 /= double(classes);
    return m;
}

void print_metrics(const std::string& name, const Metrics& m)
{
    std::cout << std::fixed << std::setprecision(4)
              << name << ": accuracy " << m.accuracy << ", macro-F1 " << m.macro_f1 << "\n";
    for (size_t c = 0; c < NN_OUTPUT; ++c)
        if (m.support[c])
            std::cout << "    class " << c << "  F1 " << m.f1[c] << "  (n=" << m.support[c] << ")\n";
}

} // namespace

int main(int argc, char** argv)
{
    try {
        size_t images = 20, first = 0;
        std::vector<char*> rest = extract_options(argc, argv, images, first);

        CampaignArgs args = parse_arguments(int(rest.size()), rest.data());
        backend_prepare_args(args);
        validateArgs(args);

        // Metricas en claro: se cargan pesos e imagenes sin pasar por la libreria HE.
        NNWeights w;
        const std::string dir = nn_data_dir();
        w.W1 = loadCSVMatrix(dir + "/weights/W1.csv", NN_HIDDEN, NN_INPUT);
        w.b1 = loadCSVVector(dir + "/weights/b1.csv", NN_HIDDEN);
        w.W2 = loadCSVMatrix(dir + "/weights/W2.csv", NN_OUTPUT, NN_HIDDEN);
        w.b2 = loadCSVVector(dir + "/weights/b2.csv", NN_OUTPUT);

        std::vector<size_t> labels, plain_preds;
        std::vector<std::vector<double>> plain_logits;
        for (size_t i = first; i < first + images; ++i) {
            size_t label = 0;
            std::vector<double> pixels;
            loadMnistNormRowByIndex(dir + "/mnist_test.csv", i, label, pixels);
            plain_logits.push_back(plain_forward(pixels, w));
            plain_preds.push_back(argmax(plain_logits.back()));
            labels.push_back(label);
        }

        // setup_campaign exige que la red en claro acierte, asi que arranca en una imagen buena;
        // despues nn_set_image cambia la imagen sin regenerar claves ni pesos codificados.
        size_t seed_image = SIZE_MAX;
        for (size_t k = 0; k < labels.size(); ++k)
            if (plain_preds[k] == labels[k]) { seed_image = first + k; break; }
        if (seed_image == SIZE_MAX)
            throw std::runtime_error("the plain network gets none of those images right");
        args.seed_input = uint32_t(seed_image);

        CtxPtr ctx(setup_campaign(args), destroy_campaign);

        std::vector<size_t> ckks_preds;
        double sum_rel = 0, worst_rel = 0;
        size_t agree = 0;
        for (size_t k = 0; k < labels.size(); ++k) {
            nn_set_image(ctx.get(), first + k);
            Injector inj = Injector::none();
            const std::vector<double> logits = run_iteration(ctx.get(), args, inj).values;
            inj.finish();

            ckks_preds.push_back(argmax(logits));
            agree += ckks_preds.back() == plain_preds[k];
            const double rel = EvaluateCKKSAccuracy(plain_logits[k], logits).l2_rel_error;
            sum_rel += rel;
            worst_rel = std::max(worst_rel, rel);
            std::cout << "." << std::flush;
        }
        std::cout << "\n\n" << args.library << ", images " << first << ".." << first + images - 1 << "\n";
        print_metrics("plain", evaluate(labels, plain_preds));
        print_metrics("ckks ", evaluate(labels, ckks_preds));
        std::cout << "plain vs ckks agreement: " << agree << "/" << labels.size()
                  << std::scientific << std::setprecision(2)
                  << ", logit relative error: mean " << sum_rel / double(labels.size())
                  << ",worst" << worst_rel << "\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << '\n';
        return 1;
    }
}
