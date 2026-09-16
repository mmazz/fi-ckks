#pragma once
#include <vector>
#include <optional>
#include "campaign_helper.h"
#include "args.h"
#include "metrics.h"
#include "injector.h"
#include <algorithm>
#include <functional>
#include <cstddef>
#include <complex>

using cdouble = std::complex<double>;
struct CampaignArgs;

struct IterationResult {
    std::vector<double> values;
    bool detected;
};

struct BackendContext {
    virtual ~BackendContext() = default;
};

std::vector<double>
get_reference_output(const BackendContext* ctx);


BackendContext* setup_campaign(const CampaignArgs& args);

IterationResult run_iteration(
    BackendContext* ctx,
    const CampaignArgs& args,
    Injector& inj
);

void destroy_campaign(BackendContext* ctx);

void backend_prepare_args(CampaignArgs& args);

