#include "registry.h"
#include <filesystem>
#include <fstream>
#include <sstream>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <chrono>
#include <stdexcept>
#include <type_traits>

namespace fs = std::filesystem;

namespace {

template <typename... Ts>
std::string joinCsvFields(const Ts&... fields)
{
    std::ostringstream oss;
    bool first = true;

    auto append = [&](const auto& value) {
        if (!first) oss << ',';
        first = false;

        using ValueT = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<ValueT, std::string>) {
            oss << CampaignRegistry::csvEscape(value);
        } else {
            oss << value;
        }
    };

    (append(fields), ...);
    return oss.str();
}

} // namespace

CampaignRegistry::FileLock::FileLock(const std::string& path)
{
    fd_ = open(path.c_str(), O_CREAT | O_RDWR, 0666);
    if (fd_ < 0) {
        throw std::runtime_error(
            "CampaignRegistry: no se pudo abrir el lockfile '" + path +
            "' (errno=" + std::to_string(errno) + ")");
    }

    if (flock(fd_, LOCK_EX) != 0) {
        int err = errno;
        close(fd_);
        fd_ = -1;
        throw std::runtime_error(
            "CampaignRegistry: no se pudo tomar flock sobre '" + path +
            "' (errno=" + std::to_string(err) + ")");
    }
}

CampaignRegistry::FileLock::~FileLock()
{
    if (fd_ >= 0) {
        flock(fd_, LOCK_UN);
        close(fd_);
    }
}

std::string CampaignRegistry::csvEscape(const std::string& field)
{
    bool needsQuoting = field.find_first_of(",\"\n\r") != std::string::npos;
    if (!needsQuoting)
        return field;

    std::string escaped = "\"";
    for (char c : field) {
        if (c == '"')
            escaped += "\"\"";
        else
            escaped += c;
    }
    escaped += "\"";
    return escaped;
}

std::string CampaignRegistry::makeCampaignKey(const CampaignArgs& args)
{
    return joinCsvFields(
        args.library, args.stage, args.logN, args.logQ, args.bitsPerCoeff,
        args.logDelta, args.logSlots, args.withNTT, args.mult_depth, args.pipeline,
        args.op_step, args.op_depth, args.amountBits, args.seed,
        args.seed_input, args.isComplex, args.logMin, args.logMax,
        args.isExhaustive,args.numSamples, args.dnum, args.scaleTech);
}

void CampaignRegistry::ensureCsvFilesExist()
{
    if (!fs::exists(start_csv_)) {
        std::ofstream f(start_csv_);
        if (!f)
            throw std::runtime_error("CampaignRegistry: no se pudo crear " + start_csv_);

        f << "campaign_id,library,stage,logN,logQ,bitsPerCoeff,logDelta,logSlots,"
             "withNTT,mult_depth,pipeline,op_step,"
             "op_depth,amountBits,seed,seed_input,"
             "isComplex,logMin,logMax,isExhaustive,numSamples,dnum,scaleTech\n";
    }

    if (!fs::exists(end_csv_)) {
        std::ofstream f(end_csv_);
        if (!f)
            throw std::runtime_error("CampaignRegistry: no se pudo crear " + end_csv_);

        f << "campaign_id,total_bitFlips,sdc_count,"
             "duration_seconds,l2_P95,l2_P99,duration\n";
    }
}


CampaignRegistry::ScanResult CampaignRegistry::scanCsv(
    const std::string& csvFile,
    const std::string& key)
{
    ScanResult result;

    std::ifstream file(csvFile);
    if (!file.is_open())
        return result;

    std::string line;
    std::getline(file, line); // header

    while (std::getline(file, line)) {

        while (!line.empty() && (line.back() == '\r' || line.back() == '\n'))
            line.pop_back();

        if (line.empty())
            continue;

        auto comma = line.find(',');
        if (comma == std::string::npos)
            continue; // linea corrupta: la ignoramos en vez de crashear

        uint32_t id;
        try {
            id = static_cast<uint32_t>(std::stoul(line.substr(0, comma)));
        } catch (const std::exception&) {
            continue; // campaign_id corrupto: ignorar la linea
        }

        result.max_id = std::max(result.max_id, id);

        if (result.existing_id == kInvalidId &&
            line.compare(comma + 1, std::string::npos, key) == 0) {
            result.existing_id = id;
        }
    }
    return result;
}

bool CampaignRegistry::idInCsv(const std::string& csvFile, uint32_t id)
{
    std::ifstream file(csvFile);
    std::string line;
    std::getline(file, line); // header

    while (std::getline(file, line)) {
        auto comma = line.find(',');
        if (comma == std::string::npos)
            continue;
        try {
            if (std::stoul(line.substr(0, comma)) == id)
                return true;
        } catch (const std::exception&) {
            continue; // línea corrupta
        }
    }
    return false;
}

CampaignRegistry::CampaignRegistry(const CampaignArgs& args)
{
    const std::string& results_dir = args.results_dir;
    fs::create_directories(results_dir);

    start_csv_ = results_dir + "/campaigns_start.csv";
    end_csv_   = results_dir + "/campaigns_end.csv";
    lockfile_  = results_dir + "/.registry.lock";

    FileLock lock(lockfile_);

    ensureCsvFilesExist();

    const auto key = makeCampaignKey(args);
    const auto scan = scanCsv(start_csv_, key);
    if (scan.existing_id != kInvalidId) {
        // Ya estaba en start: o terminó (está en end) o quedó interrumpida.
        campaign_id  = scan.existing_id;
        already_done = idInCsv(end_csv_, campaign_id);
    } else {
        campaign_id = scan.max_id + 1;

        std::ofstream f(start_csv_, std::ios::app);
        if (!f)
            throw std::runtime_error("CampaignRegistry: no se pudo abrir " + start_csv_ + " para escritura");

        f << campaign_id << "," << key << "\n";

        if (!f)
            throw std::runtime_error("CampaignRegistry: fallo al escribir en " + start_csv_);
    }
    // ~FileLock() libera el flock aca.
}

void CampaignRegistry::register_end(const CampaignEndRecord& r)
{
    FileLock lock(lockfile_);

    std::ofstream f(end_csv_, std::ios::app);
    if (!f)
        throw std::runtime_error("CampaignRegistry: no se pudo abrir " + end_csv_ + " para escritura");
    f << joinCsvFields(r.campaign_id, r.total_bitFlips, r.sdc_count,
                        r.duration_seconds, r.l2_P95, r.l2_P99, r.duration)
      << "\n";
    if (!f)
        throw std::runtime_error("CampaignRegistry: fallo al escribir en " + end_csv_);
}
