#pragma once
// Injection point, as an enum. It used to be a std::string compared by value all over
// the backends, so a typo in `inj.here("mul_inisde")` silently never matched and the
// campaign only failed later, at probe time. Now it does not compile.
//
// Adding a stage: one entry in the enum and one row in kStageNames. If the old
// (string) name is different, add it to kStageAliases so existing configs keep working.
#include <cstdint>
#include <stdexcept>
#include <string>

enum class Stage : uint8_t {
    None = 0,
    // client side
    Encode, EncryptC0, EncryptC1, DecryptC0, DecryptC1, Decode,
    // server side, inside the operations
    Add, PMul, Mul, MulAsplos, Scalar, Rescale, Rot, RotAsplos,
    Boot, BootCoeff, BootEval, BootSlot,
    // neural network workload
    ChebyTanh3, HiddenLayer,
};

struct StageName { const char* name; Stage stage; };

// The name is what goes into campaigns_start.csv, so it must not change.
inline constexpr StageName kStageNames[] = {
    {"none",         Stage::None},
    {"encode",       Stage::Encode},
    {"encrypt_c0",   Stage::EncryptC0},
    {"encrypt_c1",   Stage::EncryptC1},
    {"decrypt_c0",   Stage::DecryptC0},
    {"decrypt_c1",   Stage::DecryptC1},
    {"decode",       Stage::Decode},
    {"add",          Stage::Add},
    {"pmul",         Stage::PMul},
    {"mul",          Stage::Mul},
    {"mul_asplos",   Stage::MulAsplos},
    {"scalar",       Stage::Scalar},
    {"rescale",      Stage::Rescale},
    {"rot",          Stage::Rot},
    {"rot_asplos",   Stage::RotAsplos},
    {"boot",         Stage::Boot},
    {"boot_coeff",   Stage::BootCoeff},
    {"boot_eval",    Stage::BootEval},
    {"boot_slot",    Stage::BootSlot},
    {"cheby_tanh3",  Stage::ChebyTanh3},
    {"hidden_layer", Stage::HiddenLayer},
};

inline const char* to_string(Stage s) {
    for (const auto& e : kStageNames)
        if (e.stage == s) return e.name;
    return "unknown";
}

inline Stage parse_stage(const std::string& s) {
    for (const auto& e : kStageNames)
        if (s == e.name) return e.stage;
    throw std::invalid_argument("invalid stage: '" + s + "'");
}
