#pragma once
#include <string>
#include <cstdint>
#include <limits>
#include <chrono>
#include <sys/file.h>
#include "campaign_helper.h"

struct CampaignStartRecord {
    uint32_t campaign_id;
    CampaignArgs args;
};

struct CampaignEndRecord {
    uint32_t campaign_id;
    uint64_t total_bitFlips;
    uint64_t detected_count;   // injections where OpenFHE's SDC detector fired (always 0 in HEAAN)
    uint64_t duration_minutes;
    double l2_P95;
    double l2_P99;
};

class CampaignRegistry {
public:
    explicit CampaignRegistry(const CampaignArgs& args);

    void register_end(const CampaignEndRecord& rec);

    uint32_t campaign_id;
    bool already_done = false; 
    static std::string csvEscape(const std::string& field);
        // Read-only check, does not create or write anything: a config that is already in
    // campaigns_end.csv can be skipped before paying for setup_campaign + baseline +
    // probe. The real registration still happens through the constructor, after the
    // probe, so an invalid config never leaves a row behind.
    static bool is_already_done(const CampaignArgs& args);

    static std::string makeCampaignKey(const CampaignArgs& args);   // antes no era static
private:
    static constexpr uint32_t kInvalidId = std::numeric_limits<uint32_t>::max();

    std::string start_csv_;
    std::string end_csv_;
    std::string lockfile_;

    class FileLock {
    public:
        explicit FileLock(const std::string& path);
        ~FileLock();
        FileLock(const FileLock&) = delete;
        FileLock& operator=(const FileLock&) = delete;
    private:
        int fd_ = -1;
    };

    struct ScanResult {
        uint32_t existing_id = kInvalidId;
        uint32_t max_id = 0;
    };

    static ScanResult scanCsv(const std::string& csvFile, const std::string& key);
    static bool idInCsv(const std::string& csvFile, uint32_t id);

    void ensureCsvFilesExist();
};
