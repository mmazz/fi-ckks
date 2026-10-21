// // Network metrics WITHOUT faults: accuracy and per-class / macro F1, in plain and under
// CKKS, plus the logit error between both. Built once per backend:
// fi_nn_metrics_heaan and fi_nn_metrics_openfhe.
//
//   fi_nn_metrics_heaan --images 50 --first_image 0 --logN 12 --logQ 220 --logDelta 30 --logSlots 10 --seed 1
//
// --images N and --first_image K belong to this tool; every other flag is a campaign flag.
// Images come from <FI_NN_DATA>/mnist_test.csv. One row per image is written to
// <results_dir>/nn_metrics/<config>_img<K>-<K+N-1>.csv (analysis/nn_accuracy.py reads them).
// If that file already exists the run is skipped, like a finished campaign.

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
#include <filesystem> 
#include <fstream> 
#include <sstream>


namespace {

using CtxPtr = std::unique_ptr<BackendContext, void (*)(BackendContext*)>;

size_t argmax(const std::vector<double>& v)
{
    return size_t(std::max_element(v.begin(), v.end()) - v.begin());
}

// Removes --images / --first_image from argv and leaves the rest for parse_arguments.
std::vector<char*> extract_options(int argc, char** argv, size_t& images, size_t& first)
{
    std::vector<char*> rest;
    for (int i = 0; i < argc; ++i) {
        const std::string arg = argv[i];
        if ((arg == "--images" || arg == "--first_image") && i + 1 < argc) {
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

// Per-class precision, recall and F1 (one-vs-rest), and their unweighted mean.
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
  
// One file per run: parallel runs (one per chunk of images) never write the same file.
std::string metrics_path(const CampaignArgs& args, size_t first, size_t images)
{
    std::ostringstream name;
    name << args.results_dir << "/nn_metrics/" << args.library
         << "_logN" << args.logN << "_logQ" << args.logQ << "_logDelta" << args.logDelta
         << "_logSlots" << args.logSlots << "_depth" << args.mult_depth
         << "_seed" << args.seed << "_img" << first << "-" << first + images - 1 << ".csv";
    return name.str();
}

// Written to <path>.tmp and renamed at the end: a killed run never leaves a half file
// that the next run would take as done.
void write_rows(const std::string& path, const CampaignArgs& args, size_t first,
                const std::vector<size_t>& labels, const std::vector<size_t>& plain_preds,
                const std::vector<size_t>& ckks_preds, const std::vector<double>& rel_err)
{
    namespace fs = std::filesystem;
    fs::create_directories(fs::path(path).parent_path());
    const std::string tmp = path + ".tmp";
    {
        std::ofstream f(tmp);
        if (!f) throw std::runtime_error("cannot write " + tmp);
        f << "library,logN,logQ,logDelta,logSlots,mult_depth,seed,"
             "image,label,plain_pred,ckks_pred,logit_rel_err\n";
        f << std::setprecision(6);
        for (size_t k = 0; k < labels.size(); ++k)
            f << args.library << ',' << args.logN << ',' << args.logQ << ',' << args.logDelta << ','
              << args.logSlots << ',' << args.mult_depth << ',' << args.seed << ','
              << first + k << ',' << labels[k] << ',' << plain_preds[k] << ','
              << ckks_preds[k] << ',' << rel_err[k] << '\n';
    }
    fs::rename(tmp, path);
}
int main(int argc, char** argv)
{
    try {
        size_t images = 20, first = 0;
        std::vector<char*> rest = extract_options(argc, argv, images, first);

        CampaignArgs args = parse_arguments(int(rest.size()), rest.data());
        backend_prepare_args(args);
        validateArgs(args);
        const std::string out_path = metrics_path(args, first, images);
        if (std::filesystem::exists(out_path)) {
            std::cout << "already done: " << out_path << "\n";
            return 0;
        }

        // Plain metrics: weights and images are loaded without going through the HE library.
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
    // setup_campaign requires the plain network to get its image right, so it starts on a
    // good one; nn_set_image then switches images without regenerating keys or weights.
        size_t seed_image = SIZE_MAX;
        for (size_t k = 0; k < labels.size(); ++k)
            if (plain_preds[k] == labels[k]) { seed_image = first + k; break; }
        if (seed_image == SIZE_MAX)
            throw std::runtime_error("the plain network gets none of those images right");
        args.seed_input = uint32_t(seed_image);

        CtxPtr ctx(setup_campaign(args), destroy_campaign);

        std::vector<size_t> ckks_preds;
        std::vector<double> rel_err;
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
            rel_err.push_back(rel);
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
                  << ", worst" << worst_rel << "\n";
        write_rows(out_path, args, first, labels, plain_preds, ckks_preds, rel_err);
        std::cout << "written: " << out_path << "\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << '\n';
        return 1;
    }
}
