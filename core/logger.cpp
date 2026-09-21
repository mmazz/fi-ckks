#include "logger.h"


namespace fs = std::filesystem;

std::string BitflipResult::header() {
    return "limb,coeff,bit,l2_abs,l2_rel,linf_abs,linf_rel,detected,correct,degraded,corrupted,failed,hidden_layer,reduceSum_layer,misclassified,out_of_range";
}

std::string BitflipResult::row() const {
    std::ostringstream ss;
    ss << std::setprecision(std::numeric_limits<double>::max_digits10);
    ss << limb << "," << coeff << "," << bit << ","
       << l2_abs << ","<< l2_rel << ","
       << linf_abs << "," << linf_rel << "," << (detected? 1 : 0) << ","
       << stats.correct << "," << stats.degraded << ","
       << stats.corrupted << "," << stats.failed<< ","
       << hidden_layer << "," << reduceSum_layer << "," << (misclassified ? 1 : 0)
       << "," << (out_of_range ? 1 : 0);
    return ss.str();
}


CampaignLogger::CampaignLogger(uint32_t id,
                               const std::string& dir,
                               size_t flush_th)
    : flush_threshold_(flush_th)
{
    fs::create_directories(dir);

    std::ostringstream path;
    path << dir << "/campaign_" << std::setw(6)
         << std::setfill('0') << id << ".csv";
    csv_path_ = path.str();

    file_.open(csv_path_, std::ios::out | std::ios::trunc);
    if (!file_.is_open())
        throw std::runtime_error("CampaignLogger: could not be opened " + csv_path_);

    file_ << BitflipResult::header() << "\n";

}




CampaignLogger::~CampaignLogger() {
    close();
}

void CampaignLogger::log(const BitflipResult& r) {
    std::lock_guard<std::mutex> g(mtx_);
    buffer_.push_back(r.row());
    total_++;
    if (r.detected) sdc_++;

    if (buffer_.size() >= flush_threshold_)
        flush();
}

void CampaignLogger::flush() {
    for (auto& l : buffer_)
        file_ << l << "\n";
    buffer_.clear();
    file_.flush();
}

void CampaignLogger::close() {
    if (closed_) return;
    closed_ = true;
    flush();
    file_.close();
    compress_and_cleanup();

}

void CampaignLogger::compress_and_cleanup() {
    if (!fs::exists(csv_path_)) return;          // already compressed or never written
    const std::string gz_path = csv_path_ + ".gz";
    const std::string cmd = "gzip -f \"" + csv_path_ + "\"";

    int ret = std::system(cmd.c_str());

    if (ret != 0) {
        std::cerr << "[WARN] gzip failed for " << csv_path_ << std::endl;
        return;
    }

    // gzip ya borra el .csv si usás -f
    std::cout << "[INFO] Compressed campaign data → " << gz_path << std::endl;
}

VectorLogger::VectorLogger(uint32_t id,
                           const std::string& dir,
                           size_t n_values,
                           size_t flush_th)
    : n_slots_(n_values),
      flush_threshold_(flush_th == 0 ? size_t{1} : flush_th)
{
    fs::create_directories(dir);
 
    std::ostringstream path;
    path << dir << "/campaign_" << std::setw(6)
         << std::setfill('0') << id << ".csv";
    csv_path_ = path.str();

    file_.open(csv_path_, std::ios::out | std::ios::trunc);
    if (!file_.is_open())
        throw std::runtime_error("VectorLogger: could not be opened " + csv_path_);
 
    // 17 digitos significativos => el double se recupera exacto al leerlo.
    file_ << std::defaultfloat
          << std::setprecision(std::numeric_limits<double>::max_digits10);
    file_ << header() << "\n";

}
 
VectorLogger::~VectorLogger() {
    close();
}
 
std::string VectorLogger::header() const {
    std::ostringstream ss;
    ss << "limb,coeff,bit";
    for (size_t i = 0; i < n_slots_; ++i)
        ss << ",v_" << i;
    return ss.str();
}
 
void VectorLogger::write_row_locked(long long limb,
                                    long long coeff,
                                    long long bit,
                                    const std::vector<double>& v)
{
    if (v.size() != n_slots_) {
        std::ostringstream e;
        e << "VectorLogger: waiting " << n_slots_ << " values but only " << v.size() << " arrive";
        throw std::invalid_argument(e.str());
    }
 
    file_ << limb << ',' << coeff << ',' << bit;
    for (double x : v)
        file_ << ',' << x;
    file_ << '\n';
 
    if (++since_flush_ >= flush_threshold_) {
        file_.flush();
        since_flush_ = 0;
    }
}
 
void VectorLogger::set_input(const std::vector<double>& input) {
    std::lock_guard<std::mutex> g(mtx_);
    if (input_written_) return;
    write_row_locked(kInputRowTag, kInputRowTag, kInputRowTag, input);
    input_written_ = true;
}
 
void VectorLogger::log(uint32_t limb, uint32_t coeff, uint32_t bit,
                       const std::vector<double>& output)
{
    std::lock_guard<std::mutex> g(mtx_);
    write_row_locked(limb, coeff, bit, output);
    total_++;
}
 
 
void VectorLogger::log(uint32_t limb, uint32_t coeff, uint32_t bit,
                       const std::vector<double>& input,
                       const std::vector<double>& output)
{
    std::lock_guard<std::mutex> g(mtx_);
    if (!input_written_) {
        write_row_locked(kInputRowTag, kInputRowTag, kInputRowTag, input);
        input_written_ = true;
    }
    write_row_locked(limb, coeff, bit, output);
    total_++;
}
 
void VectorLogger::flush() {
    std::lock_guard<std::mutex> g(mtx_);
    if (file_.is_open()) file_.flush();
    since_flush_ = 0;
}
 
void VectorLogger::close() {
    std::lock_guard<std::mutex> g(mtx_);
    if (closed_) return;
    closed_ = true;
 
    if (file_.is_open()) {
        file_.flush();
        file_.close();
    }
    compress_and_cleanup();
}
 
void VectorLogger::compress_and_cleanup() {
    if (!fs::exists(csv_path_)) return;   // ya comprimido o nunca se escribio
 
    const std::string gz_path = csv_path_ + ".gz";
    const std::string cmd = "gzip -f \"" + csv_path_ + "\"";
 
    int ret = std::system(cmd.c_str());
    if (ret != 0) {
        std::cerr << "[WARN] gzip failed for " << csv_path_ << std::endl;
        return;
    }
 
    std::cout << "[INFO] Compressed campaign vectors -> " << gz_path << std::endl;
}

