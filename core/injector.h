#pragma once
#include <cstdint>
#include <stdexcept>
#include <string>
#include <string_view>

struct FaultSpec {
    std::string stage;
    uint32_t op_depth = 0, op_step = 0;
    uint32_t limb = 0, coeff = 0, bit = 0, amountBits = 1;
};

class Injector {
public:
    static Injector none() { return Injector(Mode::None, {}); }
    static Injector fault(const FaultSpec& f) { return Injector(Mode::Fault, f); }
    static Injector probe(const std::string& stage, uint32_t op_depth, uint32_t op_step) {
        FaultSpec f; f.stage = stage; f.op_depth = op_depth; f.op_step = op_step;
        return Injector(Mode::Probe, f);
    }

    bool here(std::string_view stage, uint32_t depth = 0) const {
        return mode_ != Mode::None && f_.stage == stage && f_.op_depth == depth;
    }
    bool probing() const { return mode_ == Mode::Probe; }
    const FaultSpec& spec() const {
        if (mode_ == Mode::None) throw std::logic_error("Injector::spec() in modo None");
        return f_;
    }
    uint64_t mask64() const {
        if (f_.amountBits == 0 || f_.bit >= 64 || f_.bit + f_.amountBits > 64)
            throw std::out_of_range("mask64: bit=" + std::to_string(f_.bit) +
                                    " amountBits=" + std::to_string(f_.amountBits));
        const uint64_t ones = (f_.amountBits == 64) ? ~0ULL : ((1ULL << f_.amountBits) - 1);
        return ones << f_.bit;
    }

    void record_flip(int flipped_bits, int changed_coeffs) {
        if (mode_ != Mode::Fault) throw std::logic_error("record_flip out of Fault mode");
        if (flipped_bits != int(f_.amountBits))
            throw std::logic_error(std::to_string(flipped_bits) + " bits flipped, " + std::to_string(f_.amountBits) + " requested");
        if (changed_coeffs != 1)
            throw std::logic_error(std::to_string(changed_coeffs) + " coefficients change, no 1");
        ++applied_;
    }
    void record_restore() { ++restored_; }
    void record_probe(uint32_t limbs, uint32_t coeff_bits) {
        if (mode_ != Mode::Probe) throw std::logic_error("record_probe out of Probe mode");
        ++probes_; limbs_ = limbs; coeff_bits_ = coeff_bits;
    }

    void finish() const {
        const std::string where = " (stage=" + f_.stage + " op_depth=" + std::to_string(f_.op_depth) +
                                  " op_step=" + std::to_string(f_.op_step) + ")";
        switch (mode_) {
        case Mode::None:
            if (applied_ || restored_ || probes_)
                throw std::logic_error("were flips in the run without fault");
            break;
        case Mode::Fault:
            if (applied_ != 1 || restored_ > 1)
                throw std::runtime_error("fault apply " + std::to_string(applied_) +
                                         " times, restaured " + std::to_string(restored_) + where);
            break;
        case Mode::Probe:
            if (probes_ == 0)
                throw std::runtime_error("the injection point was never reach " + where);
            break;
        }
    }
    uint32_t probed_limbs() const { return limbs_; }
    uint32_t probed_coeff_bits() const { return coeff_bits_; }

private:
    enum class Mode { None, Fault, Probe };
    Injector(Mode m, FaultSpec f) : mode_(m), f_(std::move(f)) {}
    Mode mode_;
    FaultSpec f_;
    int applied_ = 0, restored_ = 0, probes_ = 0;
    uint32_t limbs_ = 0, coeff_bits_ = 0;
};
