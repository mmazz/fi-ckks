#include "pipeline.h"
#include "args.h"

#include <cctype>
#include <charconv>
#include <sstream>
#include <stdexcept>

namespace {

struct OpInfo { const char* name; OpType type; bool needs_param; };
constexpr OpInfo kOps[] = {
    {"add",    OpType::Add,    false},
    {"pmul",   OpType::PMul,   false},
    {"mul",    OpType::Mul,    false},
    {"scalar", OpType::Scalar, true },
    {"rot",    OpType::Rot,    true },
    {"boot",   OpType::Boot,   false},
};

const OpInfo& info(OpType t) {
    for (const auto& o : kOps) if (o.type == t) return o;
    throw std::logic_error("OpType desconocido");
}

std::string trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\n\r");
    if (a == std::string::npos) return "";
    size_t b = s.find_last_not_of(" \t\n\r");
    return s.substr(a, b - a + 1);
}

bool is_repeat(const std::string& w) {   // "x3"
    return w.size() >= 2 && w[0] == 'x' &&
           std::all_of(w.begin() + 1, w.end(), [](unsigned char c) { return std::isdigit(c); });
}

std::string fmt_double(double v) {
    char buf[64];
    auto r = std::to_chars(buf, buf + sizeof(buf), v);   // representacion mas corta exacta
    return std::string(buf, r.ptr);
}

} // namespace

const char* op_name(OpType t) { return info(t).name; }

bool has_op(const std::vector<Op>& ops, OpType t) {
    return std::any_of(ops.begin(), ops.end(), [t](const Op& o) { return o.type == t; });
}

bool is_mult(OpType t) { return t == OpType::Mul || t == OpType::PMul || t == OpType::Scalar; }

std::vector<Op> parse_pipeline(const std::string& s) {
    std::vector<Op> out;
    std::stringstream all(s);
    std::string chunk;
    while (std::getline(all, chunk, ';')) {
        chunk = trim(chunk);
        if (chunk.empty()) continue;

        std::istringstream ws(chunk);
        std::string name, w;
        ws >> name;

        const OpInfo* oi = nullptr;
        for (const auto& o : kOps) if (name == o.name) oi = &o;
        if (!oi) throw std::invalid_argument("pipeline: op desconocida '" + name +
                                             "' (validas: add pmul mul scalar rot boot)");

        long reps = 1;
        bool has_param = false;
        double param = 0;
        while (ws >> w) {
            if (is_repeat(w)) {
                reps = std::stol(w.substr(1));
                if (reps < 1) throw std::invalid_argument("pipeline: repeticion invalida en '" + chunk + "'");
            } else if (!has_param) {
                size_t used = 0;
                try { param = std::stod(w, &used); } catch (...) { used = 0; }
                if (used != w.size()) throw std::invalid_argument("pipeline: valor invalido '" + w + "' en '" + chunk + "'");
                has_param = true;
            } else {
                throw std::invalid_argument("pipeline: sobra '" + w + "' en '" + chunk + "'");
            }
        }
        if (oi->needs_param && !has_param)
            throw std::invalid_argument("pipeline: '" + name + "' necesita un valor");
        if (!oi->needs_param && has_param)
            throw std::invalid_argument("pipeline: '" + name + "' no acepta valor");
        if (oi->type == OpType::Rot && (param < 1 || param != double(long(param))))
            throw std::invalid_argument("pipeline: rot necesita un entero >= 1");

        for (long i = 0; i < reps; ++i) out.push_back({oi->type, param});
    }
    return out;
}

std::string to_string(const std::vector<Op>& ops) {
    std::string out;
    for (size_t i = 0; i < ops.size();) {
        size_t j = i;
        while (j < ops.size() && ops[j].type == ops[i].type && ops[j].param == ops[i].param) ++j;
        if (!out.empty()) out += "; ";
        out += op_name(ops[i].type);
        if (info(ops[i].type).needs_param) out += " " + fmt_double(ops[i].param);
        if (j - i > 1) out += " x" + std::to_string(j - i);
        i = j;
    }
    return out;
}

void compute_plain_io(const CampaignArgs& args, std::vector<double>& base, std::vector<double>& golden) {
    base = uniform_dist(1 << args.logSlots, args.logMin, args.logMax, args.seed_input, false);
    golden = base;
    for (const Op& op : args.ops) apply_plain(op, golden, base);
    if (args.verbose) { printVector(base, "Flat input", 10); printVector(golden, "Golden output", 10); }
}

void compute_plain_io(const CampaignArgs& args, std::vector<std::complex<double>>& base,
                      std::vector<std::complex<double>>& golden) {
    auto re = uniform_dist(1 << args.logSlots, args.logMin, args.logMax, args.seed_input, false);
    auto im = uniform_dist(1 << args.logSlots, args.logMin, args.logMax, args.seed_input + 1, false);
    constexpr double inv_sqrt2 = 0.7071067811865475;   // |x| < 1 para entradas en [-1,1]
    base.resize(re.size());
    for (size_t i = 0; i < re.size(); ++i) base[i] = {re[i] * inv_sqrt2, im[i] * inv_sqrt2};
    golden = base;
    for (const Op& op : args.ops) apply_plain(op, golden, base);
    if (args.verbose) { printVector(base, "Flat complex input", 10); printVector(golden, "Golden complex output", 10); }
}
