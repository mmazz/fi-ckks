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
#
# Thesis repo only: data.mk (written by scripts/export_thesis.sh) pins the data release
# and points RES1 / RES2 / RES_NN / RES_BURST at the downloaded copy. In fi-ckks it does not exist.
-include data.mk
# scripts/clientCampaigns.py: chapter 1 and the ev_ figures
RES1     ?= ../results_client
# scripts/serverCampaigns.py: chapter 2
RES2     ?= ../results_server
# scripts/TACO_campaings.py: ASPLOS panels (mul_panels, client_panels)
RES      ?= ../results
RES_NN      ?= ../results_NN
RES_BURST   ?= ../results_burst
SHOW     ?=

CURVE  = python3 bit_curve.py    --results $(RES) $(SHOW)
SHARE  = python3 slot_share.py   --results $(RES) $(SHOW)
SHIFT  = python3 encode_shift.py --results $(RES) $(SHOW)
HEAT   = python3 step_heatmap.py --results $(RES) $(SHOW)
REG    = python3 register_map.py --results $(RES) $(SHOW)
# en rango [-1,1] 10⁻²	valores corridos 1 %
# L2 ≈ 2^(b − logΔ) / (√2 · rms de la entrada)
YL     = --linthresh 1e-2 --ylabel 'L$$_2$$ norm (symlog)'

# Heatmaps of every coefficient, of the aligned ones and of the other ones.
# $(1) = title prefix, $(2) = arguments for the three, $(3) = arguments for aligned/other only
define HEAT3
$(HEAT) --title $(1)_heat         $(2) --tol 3
$(HEAT) --title $(1)_heat_aligned $(2) $(3) --gap aligned --tol 3
$(HEAT) --title $(1)_heat_other   $(2) $(3) --gap other   --tol 3 --no-legend
endef
define CURVE3
$(CURVE) --title $(1)         $(2) --split gap
endef
# What a thesis figure reads: the plotting scripts, this Makefile and the data. A figure
# is replotted only when one of them is newer than its stamp (see "Incremental build").
FIG_DEPS = Makefile $(wildcard *.py utils/*.py) \
           $(wildcard $(RES1)/campaigns_*.csv $(RES2)/campaigns_*.csv $(RES_NN)/campaigns_*.csv $(RES_BURST)/campaigns_*.csv)
# Every figure averages ALL the repetitions of its config: the collapsed data has no seed
# columns to filter on. enc_seeds (25x25) shares its config with the other BASE figures.
ENC    = stage in ["encrypt_c0", "encrypt_c1"]
ENC_DEC    = stage in ["encrypt_c0", "encrypt_c1", "decode"]

.PHONY: check ch1 ch2 ev nn burst all
all: ch1 ch2 ev nn burst


check:
	python3 check_results.py $(RES1)
	python3 check_results.py $(RES2)
	python3 check_results.py $(RES_NN)
	python3 check_results.py $(RES_BURST)

stats:
	python3 slot_stats.py ../results_client ../results_server
	python3 slot_stats.py ../results_client --by stage logMin logMax
	python3 slot_stats.py ../results_server --by stage op_step
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
      c1_fig09 c1_fig09b c1_fig09c c1_fig09d c1_fig10 c1_fig10b c1_fig11 c1_fig11b c1_fig12 c1_fig12b c1_fig12c c1_fig13 c1_share
.PHONY: $(CH1)
ch1: $(CH1)
$(addprefix _,$(CH1)): RES = $(RES1)
	
# Seed variability: band = min..max per bit over every coefficient and repetition.
_c1_fig01:
	$(CURVE) --title c1_fig01_seeds --where $(BASE) bitsPerCoeff=64 pipeline= \
	    --query '$(ENC)' --per stage --raw_spread $(YL)

_c1_fig02:
	$(CURVE) --title c1_fig02_logN \
	    --where library=heaan stage=encrypt_c0 pipeline= logQ=60 logDelta=40 bitsPerCoeff=64 \
	    --query 'logSlots == logN - 1' \
	    --vary logN --labels 'logN=6' 'logN=16' $(YL)

_c1_fig03:
	$(SHIFT) --title c1_fig03_encode_libs --where $(subst library=heaan ,,$(BASE)) stage=encode pipeline= \
	    --query '(library == "heaan" and bitsPerCoeff == 128) or (library == "openfhe" and bitsPerCoeff == 64)' \
	    --vary library --labels 'HEAAN (bit $$-$$ logQ)' 'OpenFHE' $(YL)


_c1_fig04:
	$(SHIFT) --title c1_fig04_encode_c0_c1_dec --where $(BASE) pipeline= \
	    --query '((stage == "encode" and bitsPerCoeff == 128) or ($(ENC_DEC) and bitsPerCoeff == 64))' \
	    --vary stage --labels 'encode (bit $$-$$ logQ)' 'encrypt_c0' 'encrypt_c1' 'decode' $(YL)

_c1_fig05:
	$(CURVE) --title c1_fig05_logDelta \
	    --where library=heaan stage=encrypt_c0 pipeline= logN=6 logSlots=5 logQ=60 bitsPerCoeff=64 logMin=0 \
	    --query 'logDelta in [25, 35, 45, 55]' --vary logDelta $(YL)

# Same data, x = bit - logDelta: the curves should collapse into one.
_c1_fig05b:
	$(CURVE) --title c1_fig05b_logDelta_shift \
	    --where library=heaan stage=encrypt_c0 pipeline= logN=6 logSlots=5 logQ=60 bitsPerCoeff=64 logMin=0 \
	    --query 'logDelta in [25, 35, 45, 55]' --vary logDelta --xnorm minus_delta $(YL)

# May be better to show c1
_c1_fig05c:
	$(CURVE) --title c1_fig05b_logDelta_shift \
	    --where library=heaan stage=encrypt_c1 pipeline= logN=6 logSlots=5 logQ=60 bitsPerCoeff=64 logMin=0 \
	    --query 'logDelta in [25, 35, 45, 55]' --vary logDelta --xnorm minus_delta $(YL)

_c1_fig06:
	$(CURVE) --title c1_fig06_logQ --where library=heaan stage=encrypt_c0 pipeline= logN=6 logSlots=5 \
	    --query 'logDelta == 0.75 * logQ and bitsPerCoeff == 1.25 * logQ' \
	    --vary logQ --xnorm over_q $(YL)
_c1_fig06b:
	$(CURVE) --title c1_fig06_logQ --where library=heaan stage=encrypt_c1 pipeline= logN=6 logSlots=5 \
	    --query 'logDelta == 0.75 * logQ and bitsPerCoeff == 1.25 * logQ' \
	    --vary logQ --xnorm over_q $(YL)

_c1_fig07:
	$(CURVE) --title c1_fig07_logSlots \
	    --where library=heaan pipeline= logN=6 logQ=60 logDelta=40 bitsPerCoeff=64 \
	    --query '$(ENC) and logSlots in [3, 4, 5]' \
	    --vary logSlots --split gap --per stage $(YL)

_c1_fig08:
	$(CURVE) --title c1_fig08_input \
	    --where library=heaan pipeline= logN=6 logSlots=5 logQ=60 logDelta=20 bitsPerCoeff=64 \
	    --query 'logMax == logMin + 1 and $(ENC)' --vary logMin --per stage $(YL)

_c1_fig09:
	$(CURVE) --title c1_fig09_add_rot \
	    --where library=heaan "pipeline=add; rot 3" logN=6 logQ=60 logDelta=30 bitsPerCoeff=64 \
	    --query 'logSlots in [3, 4, 5]' --vary logSlots --split gap --per stage $(YL)

_c1_fig09b:
	$(CURVE) --title c1_fig09_add_pmul_rot \
	    --where library=heaan "pipeline=add x2; pmul x3; rot 3" logN=6 logQ=150 logDelta=30 bitsPerCoeff=170 \
	    --query 'logSlots in [3, 4, 5]' --vary logSlots --split gap --per stage $(YL)

_c1_fig09c:
	$(CURVE) --title c1_fig09_add_rotOpen \
	    --where $(OFHE) "pipeline=add; rot 3" mult_depth=0 withNTT=0 \
	    --query 'logSlots in [3, 4, 5]' --vary logSlots --split gap --per stage $(YL) --detect_onset

_c1_fig09d:
	$(CURVE) --title c1_fig09_add_pmul_rotRNS \
	    --where $(OFHE) "pipeline=add x2; pmul x3; rot 3" mult_depth=3 withNTT=0  \
	    --query 'logSlots in [3, 4, 5]' --vary logSlots --split gap --per stage $(YL) --detect_onset --drop_coeffs 0


_c1_fig10:
	$(CURVE) --title c1_fig10_mul --where $(CLIENT_MUL) \
	    --query 'pipeline in ["mul", "mul x2", "mul x3"] and $(ENC)' \
	    --vary pipeline --split gap --per stage $(YL)

# # FIG 10b: c0 gaps, a ciphertext operand (mul) leaks the fault through its noise, a plaintext one (pmul) does not.
_c1_fig10b:
	$(CURVE) --title c1_fig10b_pmul_c0 --where $(CLIENT_MUL) \
	    --query 'stage == "encrypt_c0" and pipeline in ["mul", "pmul", "mul x3", "pmul x3"]' \
	    --vary pipeline --split gap $(YL)
	$(CURVE) --title c1_fig10b_pmul_c1 --where $(CLIENT_MUL) \
	    --query 'stage == "encrypt_c1" and pipeline in ["mul", "pmul", "mul x3", "pmul x3"]' \
	    --vary pipeline --split gap $(YL)

_c1_fig11:
	$(CURVE) --title c1_fig11_boot --where $(BOOTP) \
	    --query 'pipeline in ["mul x4", "mul x4; boot"] and $(ENC)' \
	    --vary pipeline --per stage --labels '4 mul' '4 mul + boot' \
	    --xlim 0 300 --ymax 1e6 --lines --boot_cutoff $(YL)

# Boot after 1 to 5 muls (boot_sweep + the "mul x4; boot" of the boot group).
_c1_fig11b:
	$(CURVE) --title c1_fig11b_boot_sweep --where $(BOOTP) \
	    --query 'pipeline in ["mul; boot", "mul x2; boot", "mul x3; boot", "mul x4; boot", "mul x5; boot"] and $(ENC)' \
	    --vary pipeline --per stage \
	    --order 'mul; boot' 'mul x2; boot' 'mul x3; boot' 'mul x4; boot' 'mul x5; boot' \
	    --labels '1 mul + boot' '2 mul + boot' '3 mul + boot' '4 mul + boot' '5 mul + boot' \
	    --xlim 0 300 --lines --boot_cutoff $(YL)

_c1_fig12:
	$(CURVE) --title c1_fig12_rns_add_rot \
	    --where $(OFHE) "pipeline=add; rot 3" mult_depth=3 withNTT=0 logSlots=$(SL) \
	    --vary limb --per stage --split gap $(YL) --detect_onset --drop_coeffs 0

_c1_fig12b:
	$(CURVE) --title c1_fig12_rns_pmul \
		--where $(OFHE) "pipeline=pmul" mult_depth=3 withNTT=0 logSlots=$(SL) --drop_coeffs 0\
		--vary limb --per stage --split gap --detect_onset $(YL)  

_c1_fig12c:
	$(CURVE) --title c1_fig12_rns_add_pmul_rot \
	    --where $(OFHE) "pipeline=add x2; pmul x3; rot 3" mult_depth=3 withNTT=0 logSlots=$(SL) \
	    --vary limb --per stage $(YL) --split gap --detect_onset --drop_coeffs 0

_c1_fig13:
	$(CURVE) --title c1_fig13_ntt \
	    --where $(OFHE) "pipeline=add; rot 3" mult_depth=0 withNTT=1 logSlots=$(SL) \
	    --per stage $(YL)
# Does a fault break every slot or only a few? Per bit: no slot / some / every slot > 1 %.
_c1_share:
	$(SHARE) --title c1_share --where $(BASE) bitsPerCoeff=64 pipeline= --query '$(ENC)' --vary stage
# ======================================================================================
# Chapter 2: server side. Base figure of each op = heatmap op_step x bit (it also prints
# the patterns and one representative per pattern), then the curves of a few steps.
# ======================================================================================
SERVER = library=heaan logN=6 logSlots=3 logQ=60 logDelta=30
DEPTH  = library=heaan logN=6 logSlots=3 logQ=160 logDelta=30 bitsPerCoeff=324
RESC   = library=heaan logN=6 logSlots=3 logQ=100 logDelta=30 bitsPerCoeff=110
MIX    = add; mul; rot 2; mul; add
# numSamples pins the thesis campaigns (mix_mul*, 50 samples): the explore_mix_* groups
# share the rest of the config with 10 samples and are a separate experiment.
MIXP   = $(BOOTP) numSamples=50

# Steps shown as curves: one per pattern, taken from what step_heatmap.py prints.
ADD_SHOW  ?= 0, 2
MUL_SHOW  ?= 0, 1, 4, 11, 14, 24
ROT_SHOW  ?= 0, 1, 3, 6, 10
MIX_DEPTH ?= 0
MUL_ROWS = 0-9;10,12;11,13;14;15;16-21,24;22,23,25

CH2 = c2_fig01 c2_fig02 c2_fig02b c2_fig02c c2_fig03 c2_fig04 c2_fig05 c2_fig06 c2_fig07
.PHONY: $(CH2)
ch2: $(CH2)
$(addprefix _,$(CH2)): RES = $(RES2)


F01_WHERE  = --where $(SERVER) op_depth=1 bitsPerCoeff=64 stage=add "pipeline=add x2"
F02_WHERE  = --where $(SERVER_MUL) bitsPerCoeff=124 stage=mul op_depth=1 "pipeline=mul x2"
F02B_WHERE = --where $(DEPTH) stage=mul "pipeline=mul x3"
F02C_WHERE = --where $(SERVER_MUL) bitsPerCoeff=124 stage=pmul op_depth=1 "pipeline=pmul x2"
F03_WHERE  = --where $(RESC) stage=rescale "pipeline=mul x2"
F04_WHERE  = --where $(SERVER) bitsPerCoeff=124 stage=rot "pipeline=rot 2"
F05_WHERE  = --where $(MIXP) stage=mul "pipeline=$(MIX)"
F06_WHERE  = --where $(MIXP) stage=mul "pipeline=$(MIX); boot"
F07_WHERE  = --where $(BOOTP) stage=boot "pipeline=mul x4; boot"
F07E_WHERE = --where $(subst logSlots=3,logSlots=2,$(BOOTP)) stage=boot_eval "pipeline=mul x4; boot"

_c2_fig01:
	$(call HEAT3,c2_fig01_add,$(F01_WHERE))
	$(CURVE) --title c2_fig01_add $(F01_WHERE) --query 'op_step in [$(ADD_SHOW)]' --vary op_step --split gap $(YL)

_c2_fig02:
	$(call HEAT3,c2_fig02_mul,$(F02_WHERE),--rows "$(MUL_ROWS)")
	$(CURVE) --title c2_fig02_mul     $(F02_WHERE) --query 'op_step in [$(MUL_SHOW)]' --vary op_step $(YL)
	$(CURVE) --title c2_fig02_mul_gap $(F02_WHERE) --query 'op_step in [$(MUL_SHOW)]' --vary op_step --split gap $(YL)

# Which mul of the chain is hit: x = bit - logq of the level where that mul runs.
_c2_fig02b:
	$(call HEAT3,c2_fig02b_mul_depth,$(F02B_WHERE) --per op_depth)
	$(CURVE) --title c2_fig02b_mul_depth     $(F02B_WHERE) --vary op_depth --per op_step --xnorm minus_level $(YL)
	$(CURVE) --title c2_fig02b_mul_depth_gap $(F02B_WHERE) --vary op_depth --per op_step --xnorm minus_level --split gap $(YL)

_c2_fig02c:
	$(call HEAT3,c2_fig02_pmul,$(F02C_WHERE),--rows "$(MUL_ROWS)")
	$(CURVE) --title c2_fig02_pmul     $(F02C_WHERE) --query 'op_step in [$(MUL_SHOW)]' --vary op_step $(YL)
	$(CURVE) --title c2_fig02_pmul_gap $(F02C_WHERE) --query 'op_step in [$(MUL_SHOW)]' --vary op_step --split gap $(YL)

_c2_fig03:
	$(call HEAT3,c2_fig03_rescale,$(F03_WHERE) --per op_depth)
	$(CURVE) --title c2_fig03_rescale     $(F03_WHERE) --vary op_step --per op_depth $(YL)
	$(CURVE) --title c2_fig03_rescale_gap $(F03_WHERE) --vary op_step --per op_depth --split gap $(YL)

_c2_fig04:
	$(call HEAT3,c2_fig04_rot,$(F04_WHERE))
	$(CURVE) --title c2_fig04_rot $(F04_WHERE) --query 'op_step in [$(ROT_SHOW)]' --vary op_step --split gap $(YL)

# Mixed pipeline, fault in the 1st or the 2nd mul.
_c2_fig05:
	$(call HEAT3,c2_fig05_mix,$(F05_WHERE) --per op_depth)
	$(CURVE) --title c2_fig05_mix     $(F05_WHERE) --vary op_depth --per op_step --xnorm minus_level $(YL)
	$(CURVE) --title c2_fig05_mix_gap $(F05_WHERE) --vary op_depth --per op_step --xnorm minus_level --split gap $(YL)

# Same, with and without the final boot (one figure per op_step, mul number MIX_DEPTH).
_c2_fig06:
	$(call HEAT3,c2_fig06_mix_boot,$(F06_WHERE) --per op_depth)
	$(CURVE) --title c2_fig06_mix_boot --where $(MIXP) stage=mul op_depth=$(MIX_DEPTH) \
	    --query 'pipeline in ["$(MIX)", "$(MIX); boot"]' --vary pipeline --per op_step $(YL)
	$(CURVE) --title c2_fig06_mix_boot_gap --where $(MIXP) stage=mul op_depth=$(MIX_DEPTH) \
	    --query 'pipeline in ["$(MIX)", "$(MIX); boot"]' --vary pipeline --per op_step --split gap $(YL)

_c2_fig07:
	$(call HEAT3,c2_fig07_boot,$(F07_WHERE))
	$(call HEAT3,c2_fig07_boot_eval,$(F07E_WHERE))
	
# ======================================================================================
# Multi-bit faults (burst_* groups). A burst of k = amountBits bits from bit b should act
# as a single flip of its top bit b+k-1: with --xnorm top_bit every k lands on the k=1
# curve. Each figure reuses the config of a single-bit one (named next to it).
# ======================================================================================
MB = mb_enc_shift mb_enc mb_rns mb_boot mb_op_mul
.PHONY: $(MB)
burst: $(MB)
$(addprefix _,$(MB)): RES = $(RES_BURST)

# x = first bit of the burst: each curve is the k=1 one shifted left by k-1 (c1_fig01 config).
MB_ENC_SHIFT_ARGS = --where $(BASE) bitsPerCoeff=64 pipeline= \
    --query '$(ENC)' --vary amountBits --per stage $(YL)

# Same data, x = top bit of the burst: the curves collapse into one.
MB_ENC_ARGS = --where $(BASE) bitsPerCoeff=64 pipeline= \
    --query '$(ENC)' --vary amountBits --per stage --xnorm top_bit $(YL)

# RNS (c1_fig12 config), averaged over the limbs.
MB_RNS_ARGS = --where $(OFHE) "pipeline=add; rot 3" mult_depth=3 withNTT=0 logSlots=3 \
    --query '$(ENC)' --vary amountBits --per stage --xnorm top_bit $(YL)

# Through bootstrapping (c1_fig11 config), the only non-linear step.
MB_BOOT_ARGS = --where $(BOOTP) "pipeline=mul x4; boot" \
    --query '$(ENC)' --vary amountBits --per stage --xnorm top_bit $(YL)

# Inside mul (c2_fig02 config): one figure per op_step of MUL_REPR.
MB_OP_MUL_ARGS = --where $(SERVER) bitsPerCoeff=124 stage=mul pipeline=mul \
    --vary amountBits --per op_step --xnorm top_bit $(YL)

.PHONY: _mb_enc_shift _mb_enc _mb_rns _mb_boot _mb_op_mul

_mb_enc_shift:
	$(call CURVE3,mb_enc_shift,$(MB_ENC_SHIFT_ARGS))

_mb_enc:
	$(call CURVE3,mb_enc,$(MB_ENC_ARGS))

_mb_rns:
	$(call CURVE3,mb_rns,$(MB_RNS_ARGS))

_mb_boot:
	$(call CURVE3,mb_boot,$(MB_BOOT_ARGS))

_mb_op_mul:
	$(call CURVE3,mb_op_mul,$(MB_OP_MUL_ARGS))
# ======================================================================================
# Exploration: every op_step of one operation, to draw conclusions before choosing
# the representative steps. Output: img/ex_<OP>_*.
#   make explore OP=mul                    heatmaps + one curve and one map per op_step
#   make explore_cmp OP=mul STEPS=4,24,25  those steps together in one figure
#   make explore_all
# OP: add mul rot rescale mul_depth mix mix_boot boot boot_eval
# ======================================================================================
EXP_add       = $(SERVER) bitsPerCoeff=64 stage=add "pipeline=add x2"
EXP_mul       = $(SERVER) bitsPerCoeff=124 stage=mul pipeline=mul
EXP_rot       = $(SERVER) bitsPerCoeff=124 stage=rot "pipeline=rot 2"
EXP_rescale   = $(RESC) stage=rescale "pipeline=mul x2"
EXP_mul_depth = $(DEPTH) stage=mul "pipeline=mul x3"
EXP_mix       = $(BOOTP) stage=mul "pipeline=$(MIX)" numSamples=10
EXP_mix_boot  = $(BOOTP) stage=mul "pipeline=$(MIX); boot" numSamples=10
EXP_boot      = $(BOOTP) stage=boot "pipeline=mul x4; boot"
EXP_boot_eval = $(subst logSlots=3,logSlots=2,$(BOOTP)) stage=boot_eval "pipeline=mul x4; boot"

# Operations whose campaigns sweep op_depth too: one heatmap per depth, one curve per depth.
DEPTH_OPS = rescale mul_depth mix mix_boot
IS_DEPTH  = $(filter $(OP),$(DEPTH_OPS))
# register_map needs one config per figure: pick the depth with OPD (default 0).
OPD      ?= 0
OP       ?= mul
STEPS    ?=

EXP_WHERE = $(EXP_$(OP))
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
	for op in add mul rot rescale mul_depth mix mix_boot boot boot_eval; do \
	    $(MAKE) explore OP=$$op || exit 1; done

comma := ,
# ======================================================================================
# Evidence: claims made in the text, not plotted in the thesis
# ======================================================================================
EV = ev_decrypt ev_decode ev_dec_mul ev_mul_rns ev_detector
.PHONY: $(EV)
ev: $(EV)
$(addprefix _,$(EV)): RES = $(RES1)

# Null pipeline: decrypt_cX lands on top of encrypt_cX.
_ev_decrypt:
	$(CURVE) --title ev_decrypt --where $(BASE) bitsPerCoeff=64 pipeline= \
	    --query 'stage in ["encrypt_c0", "decrypt_c0", "encrypt_c1", "decrypt_c1"]' \
	    --vary stage $(YL)

# Null pipeline: decode vs encode.
_ev_decode:
	$(CURVE) --title ev_decode --where $(BASE) bitsPerCoeff=128 pipeline= \
	    --query 'stage in ["encode", "decode"]' --vary stage $(YL)

# A fault at decryption only sees the level the pipeline ends at, not the pipeline:
# after "mul x3" (logQ=150) the level is 60 = the null pipeline at logQ=60.
_ev_dec_mul:
	$(CURVE) --title ev_dec_mul --where library=heaan logN=6 logSlots=3 logDelta=30 \
	    --query 'stage in ["decrypt_c0", "decrypt_c1"] and ((pipeline == "mul x3" and logQ == 150) or (pipeline == "" and logQ == 60))' \
	    --vary pipeline --per stage $(YL)

# RNS + mul: probability of SDC per bit (the "it breaks everything" claim).
_ev_mul_rns:
	$(CURVE) --title ev_mul_rns --where $(OFHE) pipeline=mul mult_depth=3 withNTT=0 logSlots=$(SL) \
	    --metric is_sdc --per stage

# OpenFHE SDC detector: L2 per bit with the mean bit from which the detector fires
# (p10..p90 over the coefficients shaded). Single limb, so the onset is not trivially bit 0.
_ev_detector:
	$(CURVE) --title ev_detector --where library=openfhe logN=6 logSlots=5 logQ=60 logDelta=40 \
	    bitsPerCoeff=64 mult_depth=0 withNTT=0 stage=encode pipeline= --detect_onset $(YL)
# ======================================================================================
# Neural network: P(SDC) per bit of the client registers (scripts/NNCampaigns.py)
# ======================================================================================
NN  = python3 nn_sdc_curve.py --results $(RES_NN) $(SHOW)
NNF = nn_client nn_client_stack nn_client_ofhe nn_client_ofhe_stack
.PHONY: $(NNF)
nn: $(NNF)

_nn_client:            ; $(NN) --title nn_client_heaan         --where library=heaanNN
_nn_client_stack:      ; $(NN) --title nn_client_heaan_stack   --where library=heaanNN --mode stack
_nn_client_ofhe:       ; $(NN) --title nn_client_openfhe       --where library=openfheNN
_nn_client_ofhe_stack: ; $(NN) --title nn_client_openfhe_stack --where library=openfheNN --mode stack
# ======================================================================================
# Incremental build of the thesis figures: `make c1_fig01` runs the recipe _c1_fig01 only
# when img/.c1_fig01.done is older than FIG_DEPS. Delete img/ (or one stamp) to force it.
# ======================================================================================
FIGS = $(CH1) $(CH2) $(EV) $(NNF) $(MB)
.PHONY: $(addprefix _,$(FIGS))
$(FIGS): %: img/.%.done
img/.%.done: $(FIG_DEPS)
	$(MAKE) --no-print-directory _$*
	@mkdir -p img && touch $@

	
# ======================================================================================
# Not thesis: other papers and workloads
# ======================================================================================


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

RNSEnc:
	python3 register_map.py --results ../results_client --show \
	    --title rnsEnc_$(TS)$ \
	    --where library=openfhe logN=6 logSlots=4 logQ=60 logDelta=30 bitsPerCoeff=64 mult_depth=4 \
	    stage=$(TS)
	
# TACO: boot sweep as register maps, one panel per pipeline, common color scale.
# Reads the thesis campaigns (groups boot + boot_sweep of clientCampaigns.py, config
# BOOTP): results_taco only has "mul x4" and "mul x4; boot" with logSlots=3.
TACO_BOOT_PIPES  = "mul x4" "mul; boot" "mul x2; boot" "mul x3; boot" "mul x4; boot" "mul x5; boot"
TACO_BOOT_LABELS = "4 mul" "1 mul + boot" "2 mul + boot" "3 mul + boot" "4 mul + boot" "5 mul + boot"
taco_boot_map:
	for s in encrypt_c0 encrypt_c1; do \
	    python3 register_map_compare.py --results $(RES1) $(SHOW) --title taco_boot_map_$$s \
	        --where $(BOOTP) stage=$$s --vary pipeline --values $(TACO_BOOT_PIPES) \
	        --labels $(TACO_BOOT_LABELS) --ylim 0 300 --boot_cutoff --fill_bits  --taco\
	        $$( [ $$s = encrypt_c1 ] && echo --no-legend ); \
	done

# c1_fig10b as register maps (paper format). Panels ordered so each mul sits next to its
# pmul. One figure per stage; the legend only on c0, so c1 can be stacked below it.
FIG10B_PIPES  = "mul" "pmul" "mul x3" "pmul x3"
FIG10B_LABELS = "1 mul" "1 pmul" "3 mul" "3 pmul"
taco_pmul_map:
	for s in encrypt_c0 encrypt_c1; do \
	    python3 register_map_compare.py --results $(RES1) $(SHOW) --title taco_pmul_map_$$s \
	        --where $(CLIENT_MUL) stage=$$s --vary pipeline --values $(FIG10B_PIPES)  --taco \
	        --labels $(FIG10B_LABELS) \
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
$(patsubst %,img/.%.done,$(FIGS)) explore explore_cmp: $(DATA_STAMP)
endif

