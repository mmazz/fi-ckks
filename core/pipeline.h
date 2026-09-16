#pragma once
#include <algorithm>
#include <complex>
#include <cstdint>
#include <string>
#include <vector>

enum class OpType { Add, PMul, Mul, Scalar, Rot, Boot };
constexpr size_t kNumOpTypes = 6;

struct Op {
    OpType type;
    double param = 0;   // rot: cantidad de slots; scalar: el escalar
};

// "add x2; pmul; mul x3; scalar 0.5; rot 4; boot"  ->  vector de ops expandido
std::vector<Op> parse_pipeline(const std::string& s);
// Forma canonica: junta repeticiones consecutivas ("mul; mul" -> "mul x2")
std::string to_string(const std::vector<Op>& ops);
const char* op_name(OpType t);
bool has_op(const std::vector<Op>& ops, OpType t);
bool is_mult(OpType t);   // ops que consumen un nivel (van seguidas de rescale)

// Semantica en claro de cada op. Una sola implementacion para los dos backends.
template <class T>
void apply_plain(const Op& op, std::vector<T>& g, const std::vector<T>& base) {
    switch (op.type) {
    case OpType::Add:
        for (size_t i = 0; i < g.size(); ++i) g[i] += base[i];
        break;
    case OpType::PMul:
    case OpType::Mul:
        for (size_t i = 0; i < g.size(); ++i) g[i] *= base[i];
        break;
    case OpType::Scalar:
        for (auto& x : g) x *= op.param;
        break;
    case OpType::Rot: {
        if (g.empty()) break;
        const size_t k = size_t(op.param) % g.size();
        std::rotate(g.begin(), g.begin() + k, g.end());
        break;
    }
    case OpType::Boot:
        break;
    }
}

struct CampaignArgs;
void compute_plain_io(const CampaignArgs& args, std::vector<double>& base, std::vector<double>& golden);
void compute_plain_io(const CampaignArgs& args, std::vector<std::complex<double>>& base,
                      std::vector<std::complex<double>>& golden);
