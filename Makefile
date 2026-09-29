JOBS ?= 10
LOG  ?= campaigns.log
NN_DATA := $(or $(FI_NN_DATA),workloads/nn/data)


.PHONY: build campaigns client server nn check nn_data

build:
	cmake --build build -j

# MNIST is downloaded once. The weights are trained only if they are missing: they are
# committed, and retraining (e.g. on a GPU) gives different weights and different results.
$(NN_DATA)/mnist_test.csv:
	bash workloads/nn/download_mnist.sh
$(NN_DATA)/weights/W1.csv: | $(NN_DATA)/mnist_test.csv
	python3 workloads/nn/train.py

nn_data: $(NN_DATA)/weights/W1.csv


# '-': a failed campaign does not stop the next script. Failures are printed and
# check_results.py lists them afterwards.
campaigns: build nn_data
	-python3 scripts/clientCampaigns.py all --jobs $(JOBS) 2>&1 | tee -a $(LOG)
	-python3 scripts/serverCampaigns.py all --jobs $(JOBS) 2>&1 | tee -a $(LOG)
	-python3 scripts/NNCampaigns.py all --jobs $(JOBS) 2>&1 | tee -a $(LOG)

client: build ; python3 scripts/clientCampaigns.py all --jobs $(JOBS)
server: build ; python3 scripts/serverCampaigns.py all --jobs $(JOBS)
nn:     build nn_data ; python3 scripts/NNCampaigns.py all --jobs $(JOBS)

# After the campaigns: unfinished / missing / uneven campaigns, then refresh the caches.
check:
	-python3 analysis/check_results.py results_client
	-python3 analysis/check_results.py results_server
	-python3 analysis/check_results.py results_NN
	python3 analysis/collapse.py results_client
	python3 analysis/collapse.py results_server
	python3 analysis/collapse.py results_NN
