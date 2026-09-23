# 	python3 bit_curve.py --title logN \
    --where library=heaan stage=<stage> pipeline=<...> logQ=<...> logDelta=<...> \
    --vary logN \
    --labels 'logN=6 – Mean $L_2$' 'logN=16 – Mean $L_2$' \
    --ylabel 'L$_2$ norm (symlog)'

RES   ?= ../results
LIB   ?= heaan
CURVE  = python3 bit_curve.py    --results $(RES)
REG    = python3 register_map.py --results $(RES)
P      = library=$(LIB) logN=6 logSlots=4 logQ=60 logDelta=25 bitsPerCoeff=64
P2      = library=$(LIB) logN=4 logQ=1200 logDelta=35 bitsPerCoeff=1210 logSlots=3 stage=encrypt_c0 pipeline="mul x6; boot"
FLAT   = python3 flat_curve.py   --results $(RES)

seeds:
	python3 bit_curve.py --title enc_seeds --where library=heaan\
		stage=encrypt_c0 logN=6 logQ=60 logDelta=40 logSlots=5 \
		isExhaustive=1 --drop_coeffs N/2 --band std \
		--minmax --linthresh 1 --show


LogDelta:
	python3 bit_curve.py --title logDelta \
	    --where library=heaan stage=encrypt_c0 pipeline= logN=6 logSlots=5 logQ=60 bitsPerCoeff=64 \
	    --query 'logDelta in [25, 35, 45, 55]' \
	    --vary logDelta \
	    --labels 'logDelta=25 Mean $$L_2$$' 'logDelta=35 Mean $$L_2$$' \
	             'logDelta=45 Mean $$L_2$$' 'logDelta=55 Mean $$L_2$$' \
	    --ylabel 'L$$_2$$ norm (symlog)' --linthresh 1 --show

LogQ:
	python3 bit_curve.py --title logQ \
	    --where library=heaan stage=encrypt_c0 pipeline= logN=6 logSlots=5 \
	    --query 'logDelta == 0.75 * logQ and bitsPerCoeff == 1.25 * logQ' \
	    --vary logQ --xnorm over_q \
	    --labels 'logQ=40 Mean $$L_2$$' 'logQ=60 Mean $$L_2$$' \
	             'logQ=80 Mean $$L_2$$' 'logQ=100 Mean $$L_2$$' \
	    --ylabel 'L$$_2$$ norm (symlog)' --linthresh 1 --show

PlainVsCipher:
	python3 encode_shift.py --title plain_vs_cipher \
	    --where library=heaan pipeline= logN=6 logSlots=5 logQ=60 logDelta=40 \
	    --query '(stage == "encode" and bitsPerCoeff == 128) or (stage in ["encrypt_c0", "encrypt_c1"] and bitsPerCoeff == 64)' \
	    --vary stage \
	    --ylabel 'L$$_2$$ norm (symlog)' --linthresh 1 --show

LibCompare:
	python3 encode_shift.py --title plain_heaan_vs_openfhe \
	    --where stage=encode pipeline= logN=6 logSlots=5 logQ=60 logDelta=40 \
	    --query '(library == "heaan" and bitsPerCoeff == 128) or (library == "openfhe" and bitsPerCoeff == 64)' \
	    --vary library \
	    --labels 'HEAAN (bit $$-$$ logQ)' 'OpenFHE' \
	    --ylabel 'L$$_2$$ norm (symlog)' --linthresh 1 --show

LogSlotsC0:
	python3 bit_curve.py --title logSlots \
	    --where library=heaan stage=encrypt_c0 pipeline= logN=6 logQ=60 logDelta=40 \
	    --query 'logSlots in [3, 4, 5]' \
	    --vary logSlots --split gap \
	    --labels 'logSlots=3 Mean $$L_2$$' 'logSlots=4 Mean $$L_2$$' 'logSlots=5 Mean $$L_2$$' \
	    --ylabel 'L$$_2$$ norm (symlog)' --linthresh 1 --show

LogSlotsC1:
	python3 bit_curve.py --title logSlots \
	    --where library=heaan stage=encrypt_c1 pipeline= logN=6 logQ=60 logDelta=40 \
	    --query 'logSlots in [3, 4, 5]' \
	    --vary logSlots --split gap \
	    --labels 'logSlots=3 Mean $$L_2$$' 'logSlots=4 Mean $$L_2$$' 'logSlots=5 Mean $$L_2$$' \
	    --ylabel 'L$$_2$$ norm (symlog)' --linthresh 1 --show

LogInput:
	python3 bit_curve.py --title logInput \
	    --where library=heaan pipeline= logN=6 logSlots=5 logQ=60 logDelta=20 bitsPerCoeff=64 \
	    --query 'logMax == logMin + 1 and stage in ["encrypt_c0", "encrypt_c1"]' \
	    --vary logMin --per stage \
	    --ylabel 'L$$_2$$ norm (symlog)' --linthresh 1 --show
# --- cliente ---
encrypt_c0:      ; $(CURVE) --title encrypt_c0 --where $(P) stage=encrypt_c0 pipeline=
encrypt_c0_reg:  ; $(REG)   --title encrypt_c0 --where $(P) stage=encrypt_c0 pipeline= --show
encrypt_c0_reg_mul:  ; $(REG)   --title encrypt_c0 --where $(P) stage=encrypt_c0 pipeline=mul --show
encrypt_c1:      ; $(CURVE) --title encrypt_c1 --where $(P) stage=encrypt_c1 pipeline=
encrypt_c1_reg:  ; $(REG)   --title encrypt_c1 --where $(P) stage=encrypt_c1 pipeline= --show
encrypt_c1_reg_mul:  ; $(REG)   --title encrypt_c1 --where $(P) stage=encrypt_c1 pipeline=mul --show
gap:          ; $(CURVE) --title gap        --where $(P) stage=encrypt_c0 pipeline= --split gap
#seeds:        ; $(CURVE) --title seeds      --where $(P) stage=encrypt_c-1 pipeline= --vary seed
stages:       ; $(CURVE) --title stages     --where $(P) pipeline= --vary stage
logQ:         ; $(CURVE) --title logQ       --where library=$(LIB) logN=6 stage=encrypt_c0 pipeline= --vary logQ --xnorm over_q
libs:         ; $(CURVE) --title libs       --where logN=6 logQ=60 stage=encrypt_c0 pipeline= --vary library
boot: 		  ; $(REG)   --title boot --where  $(P2) --show

# same thing but as two curves on one axes, which is easier to compare than two panels
gap_vary:     ; $(CURVE) --title gap_vary   --where $(P) stage=encrypt_c0 pipeline= --vary gap_aligned
# --- naive scan: no averaging, one point per (coeff, bit) ---
flat:         ; $(FLAT)  --title flat       --where $(P) stage=encrypt_c0 pipeline= --color gap
flat_bit:     ; $(FLAT)  --title flat_bit   --where $(P) stage=encrypt_c0 pipeline= --color gap --order bit
# --- rate curves: how OFTEN a flip is visible, next to how big it is ---
sdc:          ; $(CURVE) --title sdc        --where $(P) stage=encrypt_c0 pipeline= --metric is_sdc --vary gap_aligned
bad:          ; $(CURVE) --title bad        --where $(P) stage=encrypt_c0 pipeline= --metric frac_bad --vary gap_aligned
detector:     ; $(CURVE) --title detector   --where library=openfhe stage=encrypt_c0 pipeline= --metric detected
# --- servidor: una figura por op_step ---
PS = library=$(LIB) logN=6 logSlots=4 logQ=120 logDelta=40 bitsPerCoeff=144
add_inside:   ; $(CURVE) --title add_inside --where $(PS) stage=add "pipeline=add x2" --per op_step --split gap
mul_inside:   ; $(CURVE) --title mul_inside --where $(PS) stage=mul pipeline=mul      --per op_step --split gap
mul_reg:      ; $(REG)   --title mul_inside --where $(PS) stage=mul pipeline=mul      --op_step all


test: ; python3 register_map.py --where library=heaan logN=4 logSlots=2 logQ=60 logDelta=40  bitsPerCoeff=64 stage=encrypt_c0 pipeline="add x2; rot 2" --results "../results" --show
test1: ; python3 register_map.py --where library=heaan logN=4 logSlots=2 logQ=60 logDelta=40  bitsPerCoeff=64 stage=encrypt_c1 pipeline="add x2; rot 2" --results "../results" --show
test2: ; python3 register_map.py --where library=openfhe logN=4 logSlots=2 logQ=60 logDelta=40  bitsPerCoeff=64 stage=encrypt_c0 pipeline="add x2; rot 2" --results "../results" --show
test3: ; python3 register_map.py --where library=openfhe logN=4 logSlots=2 logQ=60 logDelta=40  bitsPerCoeff=64 stage=encrypt_c1 pipeline="add x2; rot 2" --results "../results" --show
