#pragma once
#include <fstream>
#include <vector>
#include <mutex>
#include <string>
#include <cstdint>
#include <filesystem>
#include <sstream>
#include <iomanip>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <stdexcept>
#include "args.h"
#include "metrics.h"
 

struct BitflipResult {
    uint32_t limb;
    uint32_t coeff;
    uint32_t bit;
    double l2_abs;
    double l2_rel;
    double linf_abs;
    double linf_rel;
    bool detected;
    SlotErrorStats stats;
    uint32_t hidden_layer;
    uint32_t reduceSum_layer;

    static std::string header();
    std::string row() const;
};

class CampaignLogger {
public:
    CampaignLogger(uint32_t campaign_id,
                   const std::string& results_dir,
                   size_t flush_threshold = 10000);

    void log(const BitflipResult& r);
    void log(uint32_t limb, uint32_t coeff, uint32_t bit,
            double l2_abs, double l2_rel, double linf_abs, double linf_rel, bool is_sdc, SlotErrorStats stats,
            uint32_t hidden_layer = 0,
            uint32_t reduceSum_layer = 0);
    void compress_and_cleanup();
    void flush();
    void close();

    uint64_t total() const { return total_; }
    uint64_t sdc() const { return sdc_; }
    ~CampaignLogger();

private:
    std::ofstream file_;
    std::string csv_path_;
    std::vector<std::string> buffer_;
    std::mutex mtx_;
    size_t flush_threshold_;
    uint64_t total_ = 0;
    uint64_t sdc_ = 0;
    bool closed_ = false;
};
class VectorLogger {
public:
    // Valor que se escribe en limb/coeff/bit para la fila del vector de entrada.
    static constexpr long long kInputRowTag = -1;
 
    VectorLogger(uint32_t campaign_id,
                 const std::string& vectors_dir,
                 uint32_t logSlot,
                 size_t flush_threshold = 16);
    ~VectorLogger();
 
    // Escribe la fila de referencia con el vector de entrada.
    // Es idempotente: la segunda llamada (y las siguientes) no hace nada.
    void set_input(const std::vector<double>& input);
 
    // Una fila por bit flip con el vector de salida.
    void log(uint32_t limb, uint32_t coeff, uint32_t bit,
             const std::vector<double>& output);
 
    // Comodo para el call site: pasa siempre los dos vectores y el logger se
    // encarga de escribir el de entrada una unica vez.
    void log(uint32_t limb, uint32_t coeff, uint32_t bit,
             const std::vector<double>& input,
             const std::vector<double>& output);
 
    void flush();
    void close();
    void compress_and_cleanup();
 
 
    size_t   slots()    const { return n_slots_; }      // 1 << logSlot
    uint32_t log_slot() const { return log_slot_; }
    uint64_t total()    const { return total_; }        // bit flips logueados
    const std::string& path() const { return csv_path_; }
 
private:
    std::string header() const;
    // Requiere mtx_ tomado.
    void write_row_locked(long long limb, long long coeff, long long bit,
                          const std::vector<double>& v);
 
    std::ofstream      file_;
    std::string        csv_path_;
    mutable std::mutex mtx_;
    uint32_t log_slot_;
    size_t   n_slots_;
    size_t   flush_threshold_;
    size_t   since_flush_   = 0;
    uint64_t total_         = 0;
    bool     input_written_ = false;
    bool     closed_        = false;
};
 

