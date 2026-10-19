# Figures of the thesis results chapters, one target per figure, numbered in the order the
# figures appear in the text:
#
#   teo  Chapter 5, master curve of the one-bit law
#   c1_  Chapter 6, single-bit faults in the client objects, RNS and NTT
#   mb_  Chapter 6, multi-bit faults (bursts)
#   c2_  Chapter 7, faults inside the homomorphic operations
#   nn_  Chapter 8, the encrypted neural network
#   ev_  claims of the text backed by data but not plotted in the thesis
#
# The parameters of each block are the ones of the campaign groups in scripts/*Campaigns.py.
#
#   make check              # health check of the results dirs, BEFORE plotting
#   make                    # the figures the thesis includes: teo ch1 burst ch2 nn
#   make all                # those and the evidence (ev)
#   make c1_fig07 SHOW=--show
#   make numbers            # every number of the text and tables -> numbers.txt
#
# Output: img/<title>.pdf and .png.
#
# Thesis repo only: data.mk (written by scripts/export_thesis.sh) pins the data release
# and points RES1 / RES2 / RES_NN / RES_BURST at the downloaded copy. In fi-ckks it does not exist.
-include data.mk
# scripts/clientCampaigns.py
RES1      ?= ../results_client
# scripts/serverCampaigns.py
RES2      ?= ../results_server
# scripts/NNCampaigns.py
RES_NN    ?= ../results_NN
# burst_* groups of scripts/clientCampaigns.py and scripts/serverCampaigns.py
RES_BURST ?= ../results_burst
# scripts/TACO_campaings.py: panels of the papers (last section)
RES       ?= ../results
SHOW      ?=

CURVE  = python3 bit_curve.py    --results $(RES) $(SHOW)
SHARE  = python3 slot_share.py   --results $(RES) $(SHOW)
SHIFT  = python3 encode_shift.py --results $(RES) $(SHOW)
HEAT   = python3 step_heatmap.py --results $(RES) $(SHOW)
REG    = python3 register_map.py --results $(RES) $(SHOW)
NN     = python3 nn_sdc_curve.py --results $(RES_NN) $(SHOW)

# y axis of every E_L2 curve: linear below 1e-2, which with inputs in [-1, 1] means values
# off by about 1 % (E_L2 ~ 2^(b - logDelta) / (sqrt(2) rms(z))).
YL      = --linthresh 1e-2 --ylabel '$$E_{L_2}$$ (symlog)'
KLABELS = --labels 'k=1' 'k=2' 'k=4' 'k=8'

# Heatmaps op_step x bit of every coefficient, of the aligned ones and of the other ones,
# one row per pattern. $(1) = title prefix, $(2) = arguments.
define HEAT3
$(HEAT) --title $(1)_heat         $(2) --tol 3 --collapse
$(HEAT) --title $(1)_heat_aligned $(2) --tol 3 --collapse --gap aligned
$(HEAT) --title $(1)_heat_other   $(2) --tol 3 --collapse --gap other --no-legend
endef

# ======================================================================================
# Configurations, one per campaign group (scripts/*Campaigns.py)
# ======================================================================================
# Chapter 6
BASE       = library=heaan logN=6 logSlots=5 logQ=60 logDelta=40
CLIENT_MUL = library=heaan logN=6 logSlots=3 logQ=150 logDelta=30 bitsPerCoeff=170
OFHE       = library=openfhe logN=6 logQ=60 logDelta=30 bitsPerCoeff=64
BOOTP      = library=heaan logN=6 logSlots=3 logQ=840 logDelta=40 bitsPerCoeff=860
# logSlots of the OpenFHE RNS and NTT figures (3 or 5)
SL        ?= 3

# Chapter 7
SERVER = library=heaan logN=6 logSlots=3 logQ=60 logDelta=30
DEPTH  = library=heaan logN=6 logSlots=3 logQ=160 logDelta=30 bitsPerCoeff=324
RESC   = library=heaan logN=6 logSlots=3 logQ=100 logDelta=30 bitsPerCoeff=110
MIX    = add; mul; rot 2; mul; add
# numSamples pins the thesis campaigns (mix_mul*, 50 samples): the explore_mix_* groups
# share the rest of the config with 10 samples and are a separate experiment.
MIXP   = $(BOOTP) numSamples=50

# One config per server operation, read by the c2_ and ev_ figures and by `make explore`.
OP_add       = $(SERVER) bitsPerCoeff=64 stage=add "pipeline=add x2" op_depth=1
# The second pmul of "pmul x2", at level 90.
OP_pmul      = $(subst logQ=60,logQ=120,$(SERVER)) bitsPerCoeff=124 stage=pmul "pipeline=pmul x2" op_depth=1
OP_mul       = $(SERVER) bitsPerCoeff=124 stage=mul pipeline=mul
OP_rescale   = $(RESC) stage=rescale "pipeline=mul x2"
OP_rot       = $(SERVER) bitsPerCoeff=124 stage=rot "pipeline=rot 2"
# Persistent fault (stages *_non_transient), only in the steps where it differs from the
# read fault (*_STEPS_NONTRANSIENT in scripts/serverCampaigns.py). Same configs as above.
OP_pmul_nt   = $(subst logQ=60,logQ=120,$(SERVER)) bitsPerCoeff=124 stage=pmul_non_transient "pipeline=pmul x2" op_depth=1
OP_mul_nt    = $(SERVER) bitsPerCoeff=124 stage=mul_non_transient pipeline=mul
OP_rot_nt    = $(SERVER) bitsPerCoeff=124 stage=rot_non_transient "pipeline=rot 2"
# OpenFHE (SERVER_OPENFHE in scripts/serverCampaigns.py): the second add of "add x2" with one
# limb and no NTT (mult_depth=0) or in RNS (mult_depth=3, 4 limbs), and the second mul of
# "mul x2" in RNS (3 limbs left after the first rescale). A mul always needs RNS in OpenFHE.
OFHE_SRV        = $(OFHE) logSlots=3 withNTT=0 attackModeSKA=1
OP_add_ofhe     = $(OFHE_SRV) mult_depth=0 stage=add "pipeline=add x2" op_depth=1
OP_add_ofhe_rns = $(OFHE_SRV) mult_depth=3 stage=add "pipeline=add x2" op_depth=1
OP_mul_ofhe_rns = $(OFHE_SRV) mult_depth=3 stage=mul "pipeline=mul x2" op_depth=1

OP_mul_depth = $(DEPTH) stage=mul "pipeline=mul x3"
OP_mix       = $(MIXP) stage=mul "pipeline=$(MIX)"
OP_mix_boot  = $(MIXP) stage=mul "pipeline=$(MIX); boot"
OP_boot      = $(BOOTP) stage=boot "pipeline=mul x4; boot"
OP_boot_eval = $(subst logSlots=3,logSlots=2,$(BOOTP)) stage=boot_eval "pipeline=mul x4; boot"

# Every figure averages ALL the repetitions of its config: the collapsed data has no seed
# columns to filter on. enc_seeds (25x25) shares its config with the other BASE figures.
ENC     = stage in ["encrypt_c0", "encrypt_c1"]
ENC_DEC = stage in ["encrypt_c0", "encrypt_c1", "decode"]

.PHONY: thesis all check stats numbers ch1 burst ch2 nn ev
# Default goal: the figures the thesis includes (see "Incremental build").
thesis: img/.thesis.done
all: thesis ev

check:
	python3 check_results.py $(RES1)
	python3 check_results.py $(RES2)
	python3 check_results.py $(RES_NN)
	python3 check_results.py $(RES_BURST)

# Every number the thesis quotes, from the same data as the figures: one text file with a
# section per chapter (4 to 8), the configuration and the statistic behind each number.
# NUM_ONLY=6 7 limits it to those chapters.
NUM_ONLY ?=
numbers:
	python3 thesis_numbers.py --client $(RES1) --server $(RES2) --burst $(RES_BURST) \
	    --nn $(RES_NN) --out numbers.txt $(if $(NUM_ONLY),--only $(NUM_ONLY))

# Slot statistics. Needs the raw results dirs, not the collapsed release (fi-ckks only).
stats:
	python3 slot_stats.py $(RES1) $(RES2)
	python3 slot_stats.py $(RES1) --by stage logMin logMax
	python3 slot_stats.py $(RES2) --by stage op_step

# ======================================================================================
# Chapter 5, analytical model: master curve of the one-bit law, every configuration where
# the fault reaches the output added (client and server releases). It also prints the fit.
# ======================================================================================
_teo:
	@mkdir -p img
	python3 master_curve.py --client $(RES1) --server $(RES2) --plot img/teo_ley_maestra.pdf

# ======================================================================================
# Chapter 6, single-bit faults (c1_): the objects that enter or leave the pipeline.
# ======================================================================================
CH1 = c1_fig01 c1_fig02 c1_fig03 c1_fig04 c1_fig05 c1_fig06 c1_fig07 c1_fig08 c1_fig09 \
      c1_fig10 c1_fig11 c1_fig12 c1_fig13 c1_fig14 c1_fig15 c1_fig16 c1_fig17 c1_fig18
ch1: $(CH1)
$(addprefix _,$(CH1)): RES = $(RES1)

# Encoded plaintext, HEAAN vs OpenFHE (one limb, no NTT). HEAAN is shifted by logQ: its
# encode works mod qQ.
_c1_fig01:
	$(SHIFT) --title c1_fig01_encode_libs --where $(subst library=heaan ,,$(BASE)) stage=encode pipeline= \
	    --query '(library == "heaan" and bitsPerCoeff == 128) or (library == "openfhe" and bitsPerCoeff == 64 and attackModeSKA == 1)' \
	    --vary library --labels 'HEAAN (bit $$-$$ logQ)' 'OpenFHE' $(YL)

# Seed variability: band = min..max per bit over every coefficient and repetition.
_c1_fig02:
	$(CURVE) --title c1_fig02_seeds --where $(BASE) bitsPerCoeff=64 pipeline= \
	    --query '$(ENC)' --per stage --raw_spread $(YL)

# Encoded plaintext (shifted by logQ), c0, c1 and the plaintext before decoding. --order:
# the labels follow the order of the curves, alphabetical without it.
_c1_fig03:
	$(SHIFT) --title c1_fig03_encode_c0_c1_dec --where $(BASE) pipeline= \
	    --query '(stage == "encode" and bitsPerCoeff == 128) or ($(ENC_DEC) and bitsPerCoeff == 64)' \
	    --vary stage --order encode encrypt_c0 encrypt_c1 decode \
	    --labels 'encode (bit $$-$$ logQ)' 'encrypt_c0' 'encrypt_c1' 'decode' $(YL)

# Does a fault break every slot or only a few? Per bit: no slot / some / every slot > 1 %.
_c1_fig04:
	$(SHARE) --title c1_fig04_share --where $(BASE) bitsPerCoeff=64 pipeline= --query '$(ENC)' --vary stage

# logN = 6 vs 16, fault in c0.
_c1_fig05:
	$(CURVE) --title c1_fig05_logN \
	    --where library=heaan stage=encrypt_c0 pipeline= logQ=60 logDelta=40 bitsPerCoeff=64 \
	    --query 'logSlots == logN - 1' --vary logN --labels 'logN=6' 'logN=16' $(YL)

# logDelta in {25, 35, 45, 55}, x = bit - logDelta: the curves collapse into one.
_c1_fig06:
	$(CURVE) --title c1_fig06_logDelta_shift \
	    --where library=heaan stage=encrypt_c0 pipeline= logN=6 logSlots=5 logQ=60 bitsPerCoeff=64 logMin=0 \
	    --query 'logDelta in [25, 35, 45, 55]' --vary logDelta --xnorm minus_delta $(YL)

# logQ in {40, 60, 80, 100} with logDelta = 3/4 logQ, x = bit / logQ.
_c1_fig07:
	$(CURVE) --title c1_fig07_logQ --where library=heaan stage=encrypt_c0 pipeline= logN=6 logSlots=5 \
	    --query 'logDelta == 0.75 * logQ and bitsPerCoeff == 1.25 * logQ' --vary logQ --xnorm over_q $(YL)

# 8, 16 and 32 slots: aligned vs non-aligned coefficients.
_c1_fig08:
	$(CURVE) --title c1_fig08_logSlots \
	    --where library=heaan pipeline= logN=6 logQ=60 logDelta=40 bitsPerCoeff=64 \
	    --query '$(ENC) and logSlots in [3, 4, 5]' --vary logSlots --split gap --per stage $(YL)

# Input magnitude: uniform in [2^logMin, 2^(logMin + 1)].
_c1_fig09:
	$(CURVE) --title c1_fig09_input \
	    --where library=heaan pipeline= logN=6 logSlots=5 logQ=60 logDelta=20 bitsPerCoeff=64 \
	    --query 'logMax == logMin + 1 and $(ENC)' --vary logMin --per stage $(YL)

# A fault before "add; rot 3", 8, 16 and 32 slots.
_c1_fig10:
	$(CURVE) --title c1_fig10_add_rot \
	    --where library=heaan "pipeline=add; rot 3" logN=6 logQ=60 logDelta=30 bitsPerCoeff=64 \
	    --query 'logSlots in [3, 4, 5]' --vary logSlots --split gap --per stage $(YL)

# Same in OpenFHE (one limb, no NTT), with the bit from which its SDC detector fires.
_c1_fig11:
	$(CURVE) --title c1_fig11_add_rot_openfhe \
	    --where $(OFHE) "pipeline=add; rot 3" mult_depth=0 withNTT=0 \
	    --query 'logSlots in [3, 4, 5]' --vary logSlots --split gap --per stage --detect_onset $(YL)

# A fault before 1, 2 and 3 ciphertext multiplications.
_c1_fig12:
	$(CURVE) --title c1_fig12_mul --where $(CLIENT_MUL) \
	    --query 'pipeline in ["mul", "mul x2", "mul x3"] and $(ENC)' \
	    --vary pipeline --split gap --per stage $(YL)

# mul vs pmul: a ciphertext operand leaks a c0 fault to the non-aligned coefficients
# through its noise, a plaintext one does not. One figure per component.
_c1_fig13:
	$(CURVE) --title c1_fig13_pmul_c0 --where $(CLIENT_MUL) stage=encrypt_c0 \
	    --query 'pipeline in ["mul", "pmul", "mul x3", "pmul x3"]' --vary pipeline --split gap $(YL)
	$(CURVE) --title c1_fig13_pmul_c1 --where $(CLIENT_MUL) stage=encrypt_c1 \
	    --query 'pipeline in ["mul", "pmul", "mul x3", "pmul x3"]' --vary pipeline --split gap $(YL)

# 4 muls, with and without bootstrapping at the end. --size_step: the curve without boot
# is drawn behind with bigger dots, so it shows as a ring where the two coincide.
_c1_fig14:
	$(CURVE) --title c1_fig14_boot --where $(BOOTP) \
	    --query 'pipeline in ["mul x4", "mul x4; boot"] and $(ENC)' \
	    --vary pipeline --per stage --labels '4 mul' '4 mul + boot' --size_step 60 \
	    --xlim 0 300 --ymax 1e6 --lines --boot_cutoff $(YL)

# 1 to 5 muls before the boot (boot_sweep + the "mul x4; boot" of the boot group).
_c1_fig15:
	$(CURVE) --title c1_fig15_boot_sweep --where $(BOOTP) \
	    --query 'pipeline in ["mul; boot", "mul x2; boot", "mul x3; boot", "mul x4; boot", "mul x5; boot"] and $(ENC)' \
	    --vary pipeline --per stage \
	    --order 'mul; boot' 'mul x2; boot' 'mul x3; boot' 'mul x4; boot' 'mul x5; boot' \
	    --labels '1 mul + boot' '2 mul + boot' '3 mul + boot' '4 mul + boot' '5 mul + boot' \
	    --xlim 0 300 --lines --boot_cutoff $(YL)

# RNS (4 limbs), "add; rot 3", one curve per limb.
_c1_fig16:
	$(CURVE) --title c1_fig16_rns_add_rot \
	    --where $(OFHE) "pipeline=add; rot 3" mult_depth=3 withNTT=0 logSlots=$(SL) \
	    --vary limb --per stage --split gap --detect_onset --drop_coeffs 0 $(YL)

# RNS, "add x2; pmul x3; rot 3", one curve per logSlots.
_c1_fig17:
	$(CURVE) --title c1_fig17_add_pmul_rotRNS \
	    --where $(OFHE) "pipeline=add x2; pmul x3; rot 3" mult_depth=3 withNTT=0 \
	    --query 'logSlots in [3, 4, 5]' --vary logSlots --split gap --per stage \
	    --detect_onset --drop_coeffs 0 $(YL)

# NTT, one limb, "add; rot 3". c0 and c1 go side by side: half-width panels.
_c1_fig18:
	$(CURVE) --title c1_fig18_ntt \
	    --where $(OFHE) "pipeline=add; rot 3" mult_depth=0 withNTT=1 logSlots=$(SL) --per stage \
	    --size half $(YL)

# ======================================================================================
# Chapter 6, multi-bit faults (mb_, burst_* groups). A burst of k = amountBits bits from
# bit b should act as a single flip of its top bit b + k - 1: with --xnorm top_bit every
# k lands on the k = 1 curve.
# ======================================================================================
MB = mb_fig01_enc mb_fig02_boot_top mb_fig02_boot_cut
burst: $(MB)
$(addprefix _,$(MB)): RES = $(RES_BURST)

# Ciphertext without operations (config of c1_fig03), x = top bit of the burst.
_mb_fig01_enc:
	$(CURVE) --title mb_fig01_enc --where $(BASE) bitsPerCoeff=64 pipeline= --query '$(ENC)' \
	    --vary amountBits --per stage --xnorm top_bit --split gap $(KLABELS) $(YL)

# Near the boot cut (config of c1_fig14), c1 only. x = top bit of the burst: the curves
# no longer collapse, each one drops at cut + k - 1.
_mb_fig02_boot_top:
	$(CURVE) --title mb_fig02_boot_top --where $(BOOTP) "pipeline=mul x4; boot" stage=encrypt_c1 \
	    --vary amountBits --xnorm top_bit --xlim 200 225 --boot_cutoff --lines --split gap $(KLABELS) $(YL)

# Same data, x = first bit b of the burst: every k drops at the same bit, the cut. Same
# x range as mb_fig02_boot_top, so the two panels go side by side.
_mb_fig02_boot_cut:
	$(CURVE) --title mb_fig02_boot_cut --where $(BOOTP) "pipeline=mul x4; boot" stage=encrypt_c1 \
	    --vary amountBits --xlim 200 225 --boot_cutoff --lines --split gap $(KLABELS) $(YL)

# ======================================================================================
# Chapter 7, server side (c2_). Each operation: heatmap op_step x bit with one row per
# pattern, then the E_L2 curves of one step per pattern.
# ======================================================================================
CH2 = c2_fig01 c2_fig02 c2_fig03 c2_fig04 c2_fig05 c2_fig05b c2_fig06 c2_fig07
ch2: $(CH2)
$(addprefix _,$(CH2)): RES = $(RES2)

# Steps drawn as curves, one per pattern of the heatmap.
ADD_SHOW  ?= 0, 2
PMUL_SHOW ?= 0, 1, 4
# One per behavior of the summary table: breaks a cancellation, key, before the shift, output.
MUL_SHOW  ?= 0, 11, 14, 24
ROT_SHOW  ?= 0, 1, 2, 3, 6
# The mul of the mixed pipeline drawn in c2_fig06 (0 = first, 1 = second).
MIX_DEPTH ?= 0

_c2_fig01:
	$(call HEAT3,c2_fig01_add,--where $(OP_add))
	$(CURVE) --title c2_fig01_add --where $(OP_add) --query 'op_step in [$(ADD_SHOW)]' --vary op_step --split gap $(YL)

_c2_fig02:
	$(call HEAT3,c2_fig02_pmul,--where $(OP_pmul))
	$(CURVE) --title c2_fig02_pmul --where $(OP_pmul) --query 'op_step in [$(PMUL_SHOW)]' --vary op_step --split gap $(YL)

_c2_fig03:
	$(call HEAT3,c2_fig03_mul,--where $(OP_mul))
	$(CURVE) --title c2_fig03_mul --where $(OP_mul) --query 'op_step in [$(MUL_SHOW)]' --vary op_step --split gap $(YL)

_c2_fig04:
	$(call HEAT3,c2_fig04_rescale,--where $(OP_rescale) --per op_depth)
	$(CURVE) --title c2_fig04_rescale --where $(OP_rescale) --vary op_step --per op_depth --split gap $(YL)

_c2_fig05:
	$(call HEAT3,c2_fig05_rot,--where $(OP_rot))
	$(CURVE) --title c2_fig05_rot --where $(OP_rot) --query 'op_step in [$(ROT_SHOW)]' --vary op_step --split gap $(YL)
# Persistent fault in the mul, in the steps where it differs from the read fault. Same
# config as c2_fig03: its rows compare with the same steps there.
_c2_fig05b:
	$(call HEAT3,c2_fig05b_mul_persistent,--where $(OP_mul_nt))
# Mixed pipeline with and without the final boot, one figure per op_step of the mul
# number MIX_DEPTH. The thesis puts two steps side by side: half-width panels. Without the
# boot the error reaches 1e216: above 1e6 it is drawn as triangles, as in c1_fig14.
_c2_fig06:
	$(call HEAT3,c2_fig06_mix_boot,--where $(OP_mix_boot) --per op_depth)
	$(CURVE) --title c2_fig06_mix_boot --where $(MIXP) stage=mul op_depth=$(MIX_DEPTH) \
	    --query 'pipeline in ["$(MIX)", "$(MIX); boot"]' --vary pipeline --per op_step \
	    --labels 'without boot' 'with boot' --size_step 60 --ymax 1e6 --boot_cutoff \
	    --size half $(YL)
	$(CURVE) --title c2_fig06_mix_boot_gap --where $(MIXP) stage=mul op_depth=$(MIX_DEPTH) \
	    --query 'pipeline in ["$(MIX)", "$(MIX); boot"]' --vary pipeline --per op_step --split gap $(YL)

# Inside the boot: between its stages, and inside EvalExp (logSlots = 2). Random campaigns:
# above the dense window around the boot cut (logq_boot + 4 logDelta = 210, +-8 bits) the
# bits are sparse, so from BOOT_GROUP up to logQ they go into one column (--group).
BOOT_GROUP ?= 240
_c2_fig07:
	$(call HEAT3,c2_fig07_boot,--where $(OP_boot) --group $(BOOT_GROUP))
	$(call HEAT3,c2_fig07_boot_eval,--where $(OP_boot_eval) --group $(BOOT_GROUP))

# ======================================================================================
# Chapter 8, neural network (nn_): probability that a flip changes the class, per bit of
# the client objects (scripts/NNCampaigns.py).
# ======================================================================================

NN_HEAAN = library=heaanNN
NNF  = nn_client nn_internal nn_profile
NN_B = nn_l2 nn_tolerance
nn: $(NNF)
nn_b: nn_client $(NN_B)
# bit_curve.py ($(CURVE)) reads $(RES)
$(addprefix _,$(NNF) $(NN_B)): RES = $(RES_NN)

_nn_client:
	$(NN) --title nn_client_heaan --where $(NN_HEAAN) --split gap
_nn_internal:
	$(NN) --title nn_internal_heaan --where $(NN_HEAAN) --mode map --stages hidden_layer cheby_tanh3
_nn_profile:
	$(NNP) --title nn_profile_heaan --where $(NN_HEAAN)
_nn_l2:
	$(CURVE) --title nn_l2_heaan --where $(NN_HEAAN) \
	    --query 'stage in ["encrypt_c0", "encrypt_c1", "decrypt_c0"]' --vary stage \
	    --order encrypt_c0 encrypt_c1 decrypt_c0 \
	    --labels '$$c_0$$ (encrypt)' '$$c_1$$ (encrypt)' '$$c_0$$ (before decrypt)' \
	    --split gap --stat median --yscale log --xlim 0 60 \
	    --ylabel 'median $$E_{L_2}$$ of the logits'
_nn_tolerance:
	$(NN) --title nn_tolerance_heaan --where $(NN_HEAAN) --mode tolerance


# ======================================================================================
# Evidence (ev_): claims of the text backed by data but not plotted in the thesis.
# ======================================================================================
EV_CLIENT = ev_decrypt ev_decode ev_dec_mul ev_mul_rns ev_detector ev_encode_ska ev_logDelta_c1 \
            ev_logQ_c1 ev_add_pmul_rot ev_rns_pmul ev_rns_add_pmul_rot_limb
EV_SERVER = ev_mul_depth ev_mix ev_mul_openfhe
EV_BURST  = ev_mb_enc_shift ev_mb_rns ev_mb_boot ev_mb_op_mul
EV = $(EV_CLIENT) $(EV_SERVER) $(EV_BURST)
ev: $(EV)
$(addprefix _,$(EV_CLIENT)): RES = $(RES1)
$(addprefix _,$(EV_SERVER)): RES = $(RES2)
$(addprefix _,$(EV_BURST)):  RES = $(RES_BURST)

# Null pipeline: decrypt_cX lands on top of encrypt_cX.
_ev_decrypt:
	$(CURVE) --title ev_decrypt --where $(BASE) bitsPerCoeff=64 pipeline= \
	    --query 'stage in ["encrypt_c0", "decrypt_c0", "encrypt_c1", "decrypt_c1"]' --vary stage $(YL)

# Null pipeline: decode vs encode.
_ev_decode:
	$(CURVE) --title ev_decode --where $(BASE) bitsPerCoeff=128 pipeline= \
	    --query 'stage in ["encode", "decode"]' --vary stage $(YL)

# A fault at decryption only sees the level the pipeline ends at, not the pipeline: after
# "mul x3" (logQ=150) the level is 60, the same as the null pipeline at logQ=60. The second
# curve needs the dec_after_mul campaigns at logDelta=30, logSlots=3 (not in the release).
_ev_dec_mul:
	$(CURVE) --title ev_dec_mul --where library=heaan logN=6 logSlots=3 logDelta=30 \
	    --query 'stage in ["decrypt_c0", "decrypt_c1"] and ((pipeline == "mul x3" and logQ == 150) or (pipeline == "" and logQ == 60))' \
	    --vary pipeline --per stage $(YL)

# RNS + mul: probability of SDC per bit (every bit breaks the output).
_ev_mul_rns:
	$(CURVE) --title ev_mul_rns --where $(OFHE) pipeline=mul mult_depth=3 withNTT=0 logSlots=$(SL) \
	    --metric is_sdc --per stage

# OpenFHE SDC detector: E_L2 per bit and the mean bit from which the detector fires (p10..p90
# over the coefficients shaded). Single limb, so the onset is not trivially bit 0.
_ev_detector:
	$(CURVE) --title ev_detector --where library=openfhe logN=6 logSlots=5 logQ=60 logDelta=40 \
	    bitsPerCoeff=64 mult_depth=0 withNTT=0 attackModeSKA=1 stage=encode pipeline= --detect_onset $(YL)

# OpenFHE encode without its decoding noise (plain_cmp_nonoise, attackModeSKA=0) should
# coincide with HEAAN: the factor 1.37 of c1_fig01 is that noise.
_ev_encode_ska:
	$(SHIFT) --title ev_encode_ska --where $(subst library=heaan ,,$(BASE)) stage=encode pipeline= \
	    --query '(library == "heaan" and bitsPerCoeff == 128) or (library == "openfhe" and bitsPerCoeff == 64)' \
	    --vary library attackModeSKA --labels 'HEAAN (bit $$-$$ logQ)' 'OpenFHE, no decode noise' 'OpenFHE' $(YL)

# c1 versions of c1_fig06 and c1_fig07.
_ev_logDelta_c1:
	$(CURVE) --title ev_logDelta_c1 \
	    --where library=heaan stage=encrypt_c1 pipeline= logN=6 logSlots=5 logQ=60 bitsPerCoeff=64 logMin=0 \
	    --query 'logDelta in [25, 35, 45, 55]' --vary logDelta --xnorm minus_delta $(YL)

_ev_logQ_c1:
	$(CURVE) --title ev_logQ_c1 --where library=heaan stage=encrypt_c1 pipeline= logN=6 logSlots=5 \
	    --query 'logDelta == 0.75 * logQ and bitsPerCoeff == 1.25 * logQ' --vary logQ --xnorm over_q $(YL)

# The pipeline of c1_fig17 in HEAAN, without RNS.
_ev_add_pmul_rot:
	$(CURVE) --title ev_add_pmul_rot \
	    --where library=heaan "pipeline=add x2; pmul x3; rot 3" logN=6 logQ=150 logDelta=30 bitsPerCoeff=170 \
	    --query 'logSlots in [3, 4, 5]' --vary logSlots --split gap --per stage $(YL)

# RNS, one curve per limb: pmul alone, and the pipeline of c1_fig17.
_ev_rns_pmul:
	$(CURVE) --title ev_rns_pmul --where $(OFHE) pipeline=pmul mult_depth=3 withNTT=0 logSlots=$(SL) \
	    --vary limb --per stage --split gap --detect_onset --drop_coeffs 0 $(YL)

_ev_rns_add_pmul_rot_limb:
	$(CURVE) --title ev_rns_add_pmul_rot_limb \
	    --where $(OFHE) "pipeline=add x2; pmul x3; rot 3" mult_depth=3 withNTT=0 logSlots=$(SL) \
	    --vary limb --per stage --split gap --detect_onset --drop_coeffs 0 $(YL)

# Chain of three muls, fault in each one: x = bit - logq of the level where that mul runs.
_ev_mul_depth:
	$(call HEAT3,ev_mul_depth,--where $(OP_mul_depth) --per op_depth)
	$(CURVE) --title ev_mul_depth --where $(OP_mul_depth) --vary op_depth --per op_step \
	    --xnorm minus_level --split gap $(YL)

# Mixed pipeline without the boot, fault in the first or the second mul.
_ev_mix:
	$(call HEAT3,ev_mix,--where $(OP_mix) --per op_depth)
	$(CURVE) --title ev_mix --where $(OP_mix) --vary op_depth --per op_step \
	    --xnorm minus_level --split gap $(YL)
# The mul of OpenFHE (RNS): every bit of every limb destroys the output, so the rows only
# split by where the fault lands. Added to c0 after the tensor product (d0, key switching
# output added to d0, output c0: steps 4, 7, 9) it stays in its coefficient and the gap
# protects the non-aligned ones; everywhere else it reaches every coefficient.
_ev_mul_openfhe:
	$(call HEAT3,ev_mul_openfhe,--where $(OP_mul_ofhe_rns))

# Bursts, x = first bit: each curve is the k = 1 one shifted left by k - 1.
_ev_mb_enc_shift:
	$(CURVE) --title ev_mb_enc_shift --where $(BASE) bitsPerCoeff=64 pipeline= --query '$(ENC)' \
	    --vary amountBits --per stage --split gap $(KLABELS) $(YL)

# Bursts in RNS (config of c1_fig16), averaged over the limbs.
_ev_mb_rns:
	$(CURVE) --title ev_mb_rns --where $(OFHE) "pipeline=add; rot 3" mult_depth=3 withNTT=0 logSlots=3 \
	    --query '$(ENC)' --vary amountBits --per stage --xnorm top_bit --split gap $(KLABELS) $(YL)

# Bursts through the boot (config of c1_fig14), both components.
_ev_mb_boot:
	$(CURVE) --title ev_mb_boot --where $(BOOTP) "pipeline=mul x4; boot" \
	    --query '$(ENC)' --vary amountBits --per stage --xnorm top_bit --split gap $(KLABELS) $(YL)

# Bursts inside the mul (config of c2_fig03), one figure per representative step.
_ev_mb_op_mul:
	$(CURVE) --title ev_mb_op_mul --where $(OP_mul) \
	    --vary amountBits --per op_step --xnorm top_bit --split gap $(KLABELS) $(YL)

# ======================================================================================
# Incremental build: `make c1_fig01` runs the recipe _c1_fig01 only when img/.c1_fig01.done
# is older than FIG_DEPS (the plotting scripts, this Makefile and the data). Delete img/
# (or one stamp) to force it. The _ recipes are not .PHONY on purpose: a figure without
# its recipe stops with "No rule to make target" instead of leaving a stamp and no figure.
# ======================================================================================
FIG_DEPS = Makefile $(wildcard *.py utils/*.py) \
           $(wildcard $(RES1)/campaigns_*.csv $(RES2)/campaigns_*.csv $(RES_NN)/campaigns_*.csv $(RES_BURST)/campaigns_*.csv)
THESIS_FIGS = teo $(CH1) $(MB) $(CH2) $(NNF)
FIGS = $(THESIS_FIGS) $(EV)
.PHONY: $(FIGS)
# Touched only when a figure of the thesis was replotted: the thesis Makefile depends on it,
# so the PDF is recompiled when a figure changes and not otherwise.
img/.thesis.done: $(patsubst %,img/.%.done,$(THESIS_FIGS))
	@mkdir -p img && touch $@
$(FIGS): %: img/.%.done
img/.%.done: $(FIG_DEPS)
	$(MAKE) --no-print-directory _$*
	@mkdir -p img && touch $@

# ======================================================================================
# Exploration: every op_step of one operation, to draw conclusions before choosing the
# representative steps. Output: img/ex_<OP>_*.
#   make explore OP=mul                    heatmaps + one curve and one map per op_step
#   make explore_cmp OP=mul STEPS=4,24,25  those steps together in one figure
#   make explore_all
# ======================================================================================
EXP_OPS = add pmul mul rot rescale mul_depth mix mix_boot boot boot_eval
# The mixed pipelines are explored with the explore_mix_* groups (10 samples, more steps
# than the thesis campaigns); the other operations with the config of their figure.
EXP_mix      = $(BOOTP) stage=mul "pipeline=$(MIX)" numSamples=10
EXP_mix_boot = $(BOOTP) stage=mul "pipeline=$(MIX); boot" numSamples=10
EXP_WHERE    = $(or $(EXP_$(OP)),$(OP_$(OP)))

# Operations whose campaigns sweep op_depth too: one heatmap per depth, one curve per depth.
DEPTH_OPS = rescale mul_depth mix mix_boot
IS_DEPTH  = $(filter $(OP),$(DEPTH_OPS))
# register_map needs one config per figure: pick the depth with OPD (default 0).
OPD      ?= 0
OP       ?= mul
STEPS    ?=
comma    := ,

EXP_HEAT  = $(HEAT) --where $(EXP_WHERE) --tol 3 $(if $(IS_DEPTH),--per op_depth)
EXP_STEPS = $(if $(STEPS),--query 'op_step in [$(STEPS)]')

.PHONY: explore explore_cmp explore_all
explore explore_cmp explore_all: RES = $(RES2)

explore:
	$(EXP_HEAT) --title ex_$(OP)_heat
	$(EXP_HEAT) --title ex_$(OP)_heat_aligned --gap aligned
	$(EXP_HEAT) --title ex_$(OP)_heat_other   --gap other --no-legend
	$(CURVE) --title ex_$(OP) --where $(EXP_WHERE) $(EXP_STEPS) \
	    --per op_step $(if $(IS_DEPTH),--vary op_depth) --split gap $(YL)
	$(REG) --title ex_$(OP)_map --where $(EXP_WHERE) $(if $(IS_DEPTH),op_depth=$(OPD)) \
	    $(if $(STEPS),--op_step $(STEPS))

explore_cmp:
	$(CURVE) --title ex_$(OP)_cmp_$(subst $(comma),_,$(STEPS)) \
	    --where $(EXP_WHERE) $(if $(IS_DEPTH),op_depth=$(OPD)) $(EXP_STEPS) \
	    --vary op_step --split gap $(YL)

explore_all:
	for op in $(EXP_OPS); do $(MAKE) explore OP=$$op || exit 1; done

# ======================================================================================
# Not in the thesis: the papers (ASPLOS, TACO) and workloads without data in the release
# ======================================================================================
.PHONY: nn_client_ofhe nn_client_ofhe_stack rns_enc mul_panels client_panels taco taco_boot_map taco_pmul_map

# OpenFHE network (openfhe_* groups of scripts/NNCampaigns.py, not run yet).
nn_client_ofhe:       ; $(NN) --title nn_client_openfhe       --where library=openfheNN
nn_client_ofhe_stack: ; $(NN) --title nn_client_openfhe_stack --where library=openfheNN --mode stack

# Register map of an RNS encryption, e.g. make rns_enc TS=encrypt_c1
rns_enc:
	python3 register_map.py --results $(RES1) $(SHOW) --title rns_enc_$(TS) \
	    --where library=openfhe logN=6 logSlots=4 logQ=60 logDelta=30 bitsPerCoeff=64 mult_depth=4 stage=$(TS)

# ASPLOS: datapath figure, panels chosen by their number in utils/sites.py
CMP = python3 register_map_compare.py --results $(RES) $(SHOW)
PA  = library=heaan logN=6 logSlots=3 logQ=60 logDelta=25 bitsPerCoeff=64
mul_panels:    ; $(CMP) --title mul_panels    --diagram mul    --panels 1 3 4 7 8 9 --no-legend --where $(PA) "pipeline=add; mul"
client_panels: ; $(CMP) --title client_panels --diagram client --where library=heaan logN=6 logSlots=5 logQ=60 logDelta=25 bitsPerCoeff=64 pipeline=mul

# TACO: register map of one (stage, pipeline), group boot_client_taco, e.g.
#   make taco TS=decrypt_c1 "TP=mul x4; boot"
TS ?= encrypt_c0
TP ?= mul x4; boot
# encode is swept from logQ up to logQ + 860 (see TACO_campaings.py)
TB  = $(if $(filter encode,$(TS)),1700,860)
taco:
	python3 register_map.py --results ../results_taco $(SHOW) \
	    --title taco_$(TS)$(if $(findstring boot,$(TP)),_boot) \
	    --where library=heaan logN=6 logSlots=3 logQ=840 logDelta=40 bitsPerCoeff=$(TB) \
	    stage=$(TS) "pipeline=$(TP)"

# TACO: boot sweep as register maps, one panel per pipeline, common color scale.
# Reads the thesis campaigns (groups boot + boot_sweep of clientCampaigns.py, config
# BOOTP): results_taco only has "mul x4" and "mul x4; boot" with logSlots=3.
TACO_BOOT_PIPES  = "mul x4" "mul; boot" "mul x2; boot" "mul x3; boot" "mul x4; boot" "mul x5; boot"
TACO_BOOT_LABELS = "4 mul" "1 mul + boot" "2 mul + boot" "3 mul + boot" "4 mul + boot" "5 mul + boot"
taco_boot_map:
	for s in encrypt_c0 encrypt_c1; do \
	    python3 register_map_compare.py --results $(RES1) $(SHOW) --title taco_boot_map_$$s \
	        --where $(BOOTP) stage=$$s --vary pipeline --values $(TACO_BOOT_PIPES) \
	        --labels $(TACO_BOOT_LABELS) --ylim 0 300 --boot_cutoff --fill_bits --taco \
	        $$( [ $$s = encrypt_c1 ] && echo --no-legend ) || exit 1; \
	done

# c1_fig13 as register maps (paper format). Panels ordered so each mul sits next to its
# pmul. One figure per stage; the legend only on c0, so c1 can be stacked below it.
PMUL_MAP_PIPES  = "mul" "pmul" "mul x3" "pmul x3"
PMUL_MAP_LABELS = "1 mul" "1 pmul" "3 mul" "3 pmul"
taco_pmul_map:
	for s in encrypt_c0 encrypt_c1; do \
	    python3 register_map_compare.py --results $(RES1) $(SHOW) --title taco_pmul_map_$$s \
	        --where $(CLIENT_MUL) stage=$$s --vary pipeline --values $(PMUL_MAP_PIPES) --taco \
	        --labels $(PMUL_MAP_LABELS) \
	        $$( [ $$s = encrypt_c1 ] && echo --no-legend ) || exit 1; \
	done

# ======================================================================================
# Thesis repo only: download the pinned data release before plotting. The stamp file
# carries DATA_TAG, so moving the pin downloads again; otherwise it is fetched once.
# ======================================================================================
ifdef DATA_URL
DATA_STAMP = ../data/.tag_$(DATA_TAG)
.PHONY: data
data: $(DATA_STAMP)
# tar -m: the files get the extraction time, not the one stored in the release. If the
# release was made on a machine whose clock is ahead, the stored times are in the future
# and every figure would look out of date on every run.
$(DATA_STAMP):
	rm -rf ../data.tmp && mkdir -p ../data.tmp
	curl -fsSL "$(DATA_URL)" | tar -xzm -C ../data.tmp
	rm -rf ../data && mv ../data.tmp ../data
	touch $@
$(patsubst %,img/.%.done,$(FIGS)) explore explore_cmp numbers: $(DATA_STAMP)
endif
