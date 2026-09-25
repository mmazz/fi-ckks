

.PHONY: campaigns
campaigns:
	python3 scripts/clientCampaigns.py all --jobs 8
	python3 scripts/serverCampaigns.py all --jobs 8

