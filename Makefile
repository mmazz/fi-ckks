JOBS ?= 8
LOG  ?= campaigns.log

.PHONY: build campaigns client server nn check

build:
	cmake --build build -j

# '-': a failed campaign does not stop the next script. Failures are printed and
# check_results.py lists them afterwards.
campaigns: build
	-python3 scripts/clientCampaigns.py all --jobs $(JOBS) 2>&1 | tee -a $(LOG)
	-python3 scripts/serverCampaigns.py all --jobs $(JOBS) 2>&1 | tee -a $(LOG)
	-python3 scripts/NNCampaigns.py all --jobs $(JOBS) 2>&1 | tee -a $(LOG)

client: build ; python3 scripts/clientCampaigns.py all --jobs $(JOBS)
server: build ; python3 scripts/serverCampaigns.py all --jobs $(JOBS)
nn:     build ; python3 scripts/NNCampaigns.py all --jobs $(JOBS)

# After the campaigns: unfinished / missing / uneven campaigns, then refresh the caches.
check:
	-python3 analysis/check_results.py results_client
	-python3 analysis/check_results.py results_server
	-python3 analysis/check_results.py results_NN
	python3 analysis/collapse.py results_client
	python3 analysis/collapse.py results_server
	python3 analysis/collapse.py results_NN
