# Figures of the thesis results chapters. One target per figure; the parameters of each
# block are the ones of scripts/clientCampaigns.py and scripts/serverCampaigns.py.
#
#   make check          # health check of the results dirs, BEFORE plotting
#   make ch1            # every figure of chapter 1 (client side)
#   make ch2            # every figure of chapter 2 (server side)
#   make ev             # the EVIDENCE figures (claims backed up but not shown)
#   make c1_fig07 SHOW=--show
#
# Output: img/<title>.pdf and .png. Chapter 1 files start with c1_, chapter 2 with c2_,
# evidence with ev_.
# scripts/clientCampaigns.py: chapter 1 and the ev_ figures
RES1     ?= ../results_client
# scripts/serverCampaigns.py: chapter 2
RES2     ?= ../results_server
# scripts/TACO_campaings.py: ASPLOS panels (mul_panels, client_panels)
RES      ?= ../results
RES_NN      ?= ../results_NN
SHOW     ?=

CURVE  = python3 bit_curve.py    --results $(RES) $(SHOW)
SHIFT  = python3 encode_shift.py --results $(RES) $(SHOW)
HEAT   = python3 step_heatmap.py --results $(RES) $(SHOW)
REG    = python3 register_map.py --results $(RES) $(SHOW)
YL     = --linthresh 1 --ylabel 'L$$_2$$ norm (symlog)'

  # Every figure averages ALL the repetitions of its config: the collapsed data has no seed
  # columns to filter on. enc_seeds (25x25) shares its config with the other BASE figures.
ENC    = stage in ["encrypt_c0", "encrypt_c1"]

.PHONY: check ch1 ch2 ev all
all: ch1 ch2 ev

check:
	python3 check_results.py $(RES)
	python3 check_results.py $(RES1) / $(RES2)

# ======================================================================================
# Chapter 1: client side
# ======================================================================================
BASE       = library=heaan logN=6 logSlots=5 logQ=60 logDelta=40
CLIENT     = library=heaan logN=6 logSlots=3 logQ=60 logDelta=30 bitsPerCoeff=64
CLIENT_MUL = library=heaan logN=6 logSlots=3 logQ=150 logDelta=30 bitsPerCoeff=170
OFHE       = library=openfhe logN=6 logQ=60 logDelta=30 bitsPerCoeff=64
BOOTP      = library=heaan logN=6 logSlots=3 logQ=840 logDelta=40 bitsPerCoeff=860
# logSlots of the OpenFHE figures (3 or 5)
SL        ?= 3

CH1 = c1_fig01 c1_fig02 c1_fig03 c1_fig04 c1_fig05 c1_fig05b c1_fig06 c1_fig07 c1_fig08 \
      c1_fig09 c1_fig10 c1_fig11 c1_fig12 c1_fig13
.PHONY: $(CH1)
ch1: $(CH1)
$(CH1): RES = $(RES1)
# Seed variability: band = min..max over the 25x25 repetitions of the per-bit curve.
c1_fig01:
	$(CURVE) --title c1_fig01_seeds --where $(BASE) bitsPerCoeff=64 pipeline= \
	    --query '$(ENC)' --per stage --rep_spread $(YL)

c1_fig02:
	$(CURVE) --title c1_fig02_logN \
	    --where library=heaan stage=encrypt_c0 pipeline= logQ=60 logDelta=40 bitsPerCoeff=64 \
	    --query 'logSlots == logN - 1' \
	    --vary logN --labels 'logN=6' 'logN=16' $(YL)

c1_fig03:
	$(SHIFT) --title c1_fig03_encode_libs --where $(subst library=heaan ,,$(BASE)) stage=encode pipeline= \
	    --query '(library == "heaan" and bitsPerCoeff == 128) or (library == "openfhe" and bitsPerCoeff == 64)' \
	    --vary library --labels 'HEAAN (bit $$-$$ logQ)' 'OpenFHE' $(YL)

c1_fig04:
	$(SHIFT) --title c1_fig04_encode_c0_c1 --where $(BASE) pipeline= \
	    --query '((stage == "encode" and bitsPerCoeff == 128) or ($(ENC) and bitsPerCoeff == 64))' \
	    --vary stage $(YL)

c1_fig05:
	$(CURVE) --title c1_fig05_logDelta \
	    --where library=heaan stage=encrypt_c0 pipeline= logN=6 logSlots=5 logQ=60 bitsPerCoeff=64 logMin=0 \
	    --query 'logDelta in [25, 35, 45, 55]' --vary logDelta $(YL)

# Same data, x = bit - logDelta: the curves should collapse into one.
c1_fig05b:
	$(CURVE) --title c1_fig05b_logDelta_shift \
	    --where library=heaan stage=encrypt_c0 pipeline= logN=6 logSlots=5 logQ=60 bitsPerCoeff=64 logMin=0 \
	    --query 'logDelta in [25, 35, 45, 55]' --vary logDelta --xnorm minus_delta $(YL)

c1_fig06:
	$(CURVE) --title c1_fig06_logQ --where library=heaan stage=encrypt_c0 pipeline= logN=6 logSlots=5 \
	    --query 'logDelta == 0.75 * logQ and bitsPerCoeff == 1.25 * logQ' \
	    --vary logQ --xnorm over_q $(YL)

c1_fig07:
	$(CURVE) --title c1_fig07_logSlots \
	    --where library=heaan pipeline= logN=6 logQ=60 logDelta=40 bitsPerCoeff=64 \
	    --query '$(ENC) and logSlots in [3, 4, 5]' \
	    --vary logSlots --split gap --per stage $(YL)

c1_fig08:
	$(CURVE) --title c1_fig08_input \
	    --where library=heaan pipeline= logN=6 logSlots=5 logQ=60 logDelta=20 bitsPerCoeff=64 \
	    --query 'logMax == logMin + 1 and $(ENC)' --vary logMin --per stage $(YL)

c1_fig09:
	$(CURVE) --title c1_fig09_add_rot \
	    --where library=heaan "pipeline=add; rot 3" logN=6 logQ=60 logDelta=30 bitsPerCoeff=64 \
	    --query 'logSlots in [3, 4, 5]' --vary logSlots --split gap --per stage $(YL)

c1_fig10:
	$(CURVE) --title c1_fig10_mul --where $(CLIENT_MUL) \
	    --query 'pipeline in ["mul", "mul x2", "mul x3"] and $(ENC)' \
	    --vary pipeline --split gap --per stage $(YL)

c1_fig11:
	$(CURVE) --title c1_fig11_boot --where $(BOOTP) \
	    --query 'pipeline in ["mul x4", "mul x4; boot"] and $(ENC)' \
	    --vary pipeline --per stage $(YL)

c1_fig12:
	$(CURVE) --title c1_fig12_rns_add_rot \
	    --where $(OFHE) "pipeline=add; rot 3" mult_depth=3 withNTT=0 logSlots=$(SL) \
	    --vary limb --per stage $(YL)

c1_fig13:
	$(CURVE) --title c1_fig13_ntt \
	    --where $(OFHE) "pipeline=add; rot 3" mult_depth=0 withNTT=1 logSlots=$(SL) \
	    --per stage $(YL)

# ======================================================================================
# Chapter 2: server side. Base figure of each op = heatmap op_step x bit (it also prints
# the patterns and one representative per pattern), then the curves of a few steps.
# ======================================================================================
SERVER = library=heaan logN=6 logSlots=3 logQ=60 logDelta=30
DEPTH  = library=heaan logN=6 logSlots=3 logQ=160 logDelta=30 bitsPerCoeff=324
RESC   = library=heaan logN=6 logSlots=3 logQ=100 logDelta=30 bitsPerCoeff=110
MIX    = add; mul; rot 2; mul; add

# Steps shown as curves: one per pattern, taken from what step_heatmap.py prints.
ADD_SHOW  ?= 0, 2
MUL_SHOW  ?= 0, 1, 4, 11, 14, 24
ROT_SHOW  ?= 0, 1, 3, 6, 10
MIX_DEPTH ?= 0

CH2 = c2_fig01 c2_fig02 c2_fig02b c2_fig03 c2_fig04 c2_fig05 c2_fig06 c2_fig07
.PHONY: $(CH2)
ch2: $(CH2)
$(CH2): RES = $(RES2)

c2_fig01:
	$(HEAT)  --title c2_fig01_add_heat         --where $(SERVER) bitsPerCoeff=64 stage=add "pipeline=add x2" --tol 3
	$(HEAT)  --title c2_fig01_add_heat_aligned --where $(SERVER) bitsPerCoeff=64 stage=add "pipeline=add x2" --gap aligned --tol 3
	$(HEAT)  --title c2_fig01_add_heat_other   --where $(SERVER) bitsPerCoeff=64 stage=add "pipeline=add x2" --gap other --tol 3
	$(CURVE) --title c2_fig01_add      --where $(SERVER) bitsPerCoeff=64 stage=add "pipeline=add x2" \
	    --query 'op_step in [$(ADD_SHOW)]' --vary op_step --split gap $(YL)

c2_fig02:
	$(HEAT)  --title c2_fig02_mul_heat         --where $(SERVER) bitsPerCoeff=124 stage=mul_asplos pipeline=mul --tol 3
	$(HEAT)  --title c2_fig02_mul_heat_aligned --where $(SERVER) bitsPerCoeff=124 stage=mul_asplos pipeline=mul --gap aligned --tol 3
	$(HEAT)  --title c2_fig02_mul_heat_other   --where $(SERVER) bitsPerCoeff=124 stage=mul_asplos pipeline=mul --gap other --tol 3
	$(CURVE) --title c2_fig02_mul      --where $(SERVER) bitsPerCoeff=124 stage=mul_asplos pipeline=mul \
	    --query 'op_step in [$(MUL_SHOW)]' --vary op_step $(YL)
	$(CURVE) --title c2_fig02_mul_gap  --where $(SERVER) bitsPerCoeff=124 stage=mul_asplos pipeline=mul \
	    --query 'op_step in [$(MUL_SHOW)]' --vary op_step --split gap $(YL)

# Which mul of the chain is hit: x = bit - logq of the level where that mul runs.
c2_fig02b:
	$(HEAT)  --title c2_fig02b_mul_depth_heat         --where $(DEPTH) stage=mul_asplos "pipeline=mul x3" --per op_depth --tol 3
	$(HEAT)  --title c2_fig02b_mul_depth_heat_aligned --where $(DEPTH) stage=mul_asplos "pipeline=mul x3" --per op_depth --gap aligned --tol 3
	$(HEAT)  --title c2_fig02b_mul_depth_heat_other   --where $(DEPTH) stage=mul_asplos "pipeline=mul x3" --per op_depth --gap other --tol 3
	$(CURVE) --title c2_fig02b_mul_depth      --where $(DEPTH) stage=mul_asplos "pipeline=mul x3" \
	    --vary op_depth --per op_step --xnorm minus_level $(YL)
	$(CURVE) --title c2_fig02b_mul_depth_gap  --where $(DEPTH) stage=mul_asplos "pipeline=mul x3" \
	    --vary op_depth --per op_step --xnorm minus_level --split gap $(YL)

c2_fig03:
	$(HEAT)  --title c2_fig03_rescale_heat         --where $(RESC) stage=rescale "pipeline=mul x2" --per op_depth --tol 3
	$(HEAT)  --title c2_fig03_rescale_heat_aligned --where $(RESC) stage=rescale "pipeline=mul x2" --per op_depth --gap aligned --tol 3
	$(HEAT)  --title c2_fig03_rescale_heat_other   --where $(RESC) stage=rescale "pipeline=mul x2" --per op_depth --gap other --tol 3
	$(CURVE) --title c2_fig03_rescale      --where $(RESC) stage=rescale "pipeline=mul x2" \
	    --vary op_step --per op_depth $(YL)
	$(CURVE) --title c2_fig03_rescale_gap  --where $(RESC) stage=rescale "pipeline=mul x2" \
	    --vary op_step --per op_depth --split gap $(YL)

c2_fig04:
	$(HEAT)  --title c2_fig04_rot_heat         --where $(SERVER) bitsPerCoeff=124 stage=rot_asplos "pipeline=rot 2" --tol 3
	$(HEAT)  --title c2_fig04_rot_heat_aligned --where $(SERVER) bitsPerCoeff=124 stage=rot_asplos "pipeline=rot 2" --gap aligned --tol 3
	$(HEAT)  --title c2_fig04_rot_heat_other   --where $(SERVER) bitsPerCoeff=124 stage=rot_asplos "pipeline=rot 2" --gap other --tol 3
	$(CURVE) --title c2_fig04_rot      --where $(SERVER) bitsPerCoeff=124 stage=rot_asplos "pipeline=rot 2" \
	    --query 'op_step in [$(ROT_SHOW)]' --vary op_step --split gap $(YL)


# Mixed pipeline, fault in the 1st or the 2nd mul.
c2_fig05:
	$(HEAT)  --title c2_fig05_mix_heat         --where $(BOOTP) stage=mul_asplos "pipeline=$(MIX)" --per op_depth --tol 3
	$(HEAT)  --title c2_fig05_mix_heat_aligned --where $(BOOTP) stage=mul_asplos "pipeline=$(MIX)" --per op_depth --gap aligned --tol 3
	$(HEAT)  --title c2_fig05_mix_heat_other   --where $(BOOTP) stage=mul_asplos "pipeline=$(MIX)" --per op_depth --gap other --tol 3
	$(CURVE) --title c2_fig05_mix      --where $(BOOTP) stage=mul_asplos "pipeline=$(MIX)" \
	    --vary op_depth --per op_step --xnorm minus_level $(YL)
	$(CURVE) --title c2_fig05_mix_gap  --where $(BOOTP) stage=mul_asplos "pipeline=$(MIX)" \
	    --vary op_depth --per op_step --xnorm minus_level --split gap $(YL)

# Same, with and without the final boot (one figure per op_step, mul number MIX_DEPTH).
c2_fig06:
	$(HEAT)  --title c2_fig06_mix_boot_heat         --where $(BOOTP) stage=mul_asplos "pipeline=$(MIX); boot" --per op_depth --tol 3
	$(HEAT)  --title c2_fig06_mix_boot_heat_aligned --where $(BOOTP) stage=mul_asplos "pipeline=$(MIX); boot" --per op_depth --gap aligned --tol 3
	$(HEAT)  --title c2_fig06_mix_boot_heat_other   --where $(BOOTP) stage=mul_asplos "pipeline=$(MIX); boot" --per op_depth --gap other --tol 3
	$(CURVE) --title c2_fig06_mix_boot      --where $(BOOTP) stage=mul_asplos op_depth=$(MIX_DEPTH) \
	    --query 'pipeline in ["$(MIX)", "$(MIX); boot"]' --vary pipeline --per op_step $(YL)
	$(CURVE) --title c2_fig06_mix_boot_gap  --where $(BOOTP) stage=mul_asplos op_depth=$(MIX_DEPTH) \
	    --query 'pipeline in ["$(MIX)", "$(MIX); boot"]' --vary pipeline --per op_step --split gap $(YL)

c2_fig07:
	$(HEAT) --title c2_fig07_boot_heat         --where $(BOOTP) stage=boot "pipeline=mul x4; boot" --tol 3
	$(HEAT) --title c2_fig07_boot_heat_aligned --where $(BOOTP) stage=boot "pipeline=mul x4; boot" --gap aligned --tol 3
	$(HEAT) --title c2_fig07_boot_heat_other   --where $(BOOTP) stage=boot "pipeline=mul x4; boot" --gap other --tol 3
	$(HEAT) --title c2_fig07_boot_eval_heat         --where $(subst logSlots=3,logSlots=2,$(BOOTP)) stage=boot_eval "pipeline=mul x4; boot" --tol 3
	$(HEAT) --title c2_fig07_boot_eval_heat_aligned --where $(subst logSlots=3,logSlots=2,$(BOOTP)) stage=boot_eval "pipeline=mul x4; boot" --gap aligned --tol 3
	$(HEAT) --title c2_fig07_boot_eval_heat_other   --where $(subst logSlots=3,logSlots=2,$(BOOTP)) stage=boot_eval "pipeline=mul x4; boot" --gap other --tol 3
# ======================================================================================
# Evidence: claims made in the text, not plotted in the thesis
# ======================================================================================
EV = ev_decrypt ev_decode ev_dec_mul ev_mul_rns
.PHONY: $(EV)
ev: $(EV)
$(EV): RES = $(RES1)

# Null pipeline: decrypt_cX lands on top of encrypt_cX.
ev_decrypt:
	$(CURVE) --title ev_decrypt --where $(BASE) bitsPerCoeff=64 pipeline= \
	    --query 'stage in ["encrypt_c0", "decrypt_c0", "encrypt_c1", "decrypt_c1"]' \
	    --vary stage $(YL)

# Null pipeline: decode vs encode.
ev_decode:
	$(CURVE) --title ev_decode --where $(BASE) bitsPerCoeff=128 pipeline= \
	    --query 'stage in ["encode", "decode"]' --vary stage $(YL)

# A fault at decryption only sees the level the pipeline ends at, not the pipeline:
# after "mul x3" (logQ=150) the level is 60 = the null pipeline at logQ=60.
ev_dec_mul:
	$(CURVE) --title ev_dec_mul --where library=heaan logN=6 logSlots=3 logDelta=30 \
	    --query 'stage in ["decrypt_c0", "decrypt_c1"] and ((pipeline == "mul x3" and logQ == 150) or (pipeline == "" and logQ == 60))' \
	    --vary pipeline --per stage $(YL)

# RNS + mul: probability of SDC per bit (the "it breaks everything" claim).
ev_mul_rns:
	$(CURVE) --title ev_mul_rns --where $(OFHE) pipeline=mul mult_depth=3 withNTT=0 logSlots=$(SL) \
	    --metric is_sdc --per stage

# ======================================================================================
# Not thesis: other papers and workloads
# ======================================================================================
NN = python3 nn_sdc_curve.py --results $(RES_NN) $(SHOW)
nn_client:       ; $(NN) --title nn_client_heaan       --where library=heaanNN
nn_client_stack: ; $(NN) --title nn_client_heaan_stack --where library=heaanNN --mode stack
nn_client_ofhe:  ; $(NN) --title nn_client_openfhe     --where library=openfheNN

# ASPLOS: datapath figure, panels chosen by their number in utils/sites.py
CMP = python3 register_map_compare.py --results $(RES) $(SHOW)
PA  = library=heaan logN=6 logSlots=3 logQ=60 logDelta=25 bitsPerCoeff=64
mul_panels:    ; $(CMP) --title mul_panels    --diagram mul    --panels 1 3 4 7 8 9 --no-legend --where $(PA) "pipeline=add; mul"
client_panels: ; $(CMP) --title client_panels --diagram client --where library=heaan logN=6 logSlots=5 logQ=60 logDelta=25 bitsPerCoeff=64 pipeline=mul

# TACO: register map of one (stage, pipeline), e.g.
#   make taco TS=decrypt_c1 "TP=mul x3; boot"
TS ?= encrypt_c0
TP ?= mul x3; boot
taco:
	python3 register_map.py --results ../results_taco $(SHOW) --title taco_$(TS) \
	    --where library=heaan logN=6 logSlots=4 logQ=840 logDelta=40 bitsPerCoeff=860 \
	    stage=$(TS) "pipeline=$(TP)"
