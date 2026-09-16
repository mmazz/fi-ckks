RES   ?= ../results
LIB   ?= heaan
CURVE  = python3 bit_curve.py    --results $(RES)
REG    = python3 register_map.py --results $(RES)
P      = library=$(LIB) logN=6 logSlots=4 logQ=60 logDelta=25 bitsPerCoeff=64
P2      = library=$(LIB) logN=4 logQ=1200 logDelta=35 bitsPerCoeff=1210 logSlots=3 stage=encrypt_c0 pipeline="mul x6; boot"

# --- cliente ---
encrypt_c0:      ; $(CURVE) --title encrypt_c0 --where $(P) stage=encrypt_c0 pipeline=
encrypt_c0_reg:  ; $(REG)   --title encrypt_c0 --where $(P) stage=encrypt_c0 pipeline= --show
encrypt_c0_reg_mul:  ; $(REG)   --title encrypt_c0 --where $(P) stage=encrypt_c0 pipeline=mul --show
encrypt_c1:      ; $(CURVE) --title encrypt_c1 --where $(P) stage=encrypt_c1 pipeline=
encrypt_c1_reg:  ; $(REG)   --title encrypt_c1 --where $(P) stage=encrypt_c1 pipeline= --show
encrypt_c1_reg_mul:  ; $(REG)   --title encrypt_c1 --where $(P) stage=encrypt_c1 pipeline=mul --show
gap:          ; $(CURVE) --title gap        --where $(P) stage=encrypt_c0 pipeline= --split gap
seeds:        ; $(CURVE) --title seeds      --where $(P) stage=encrypt_c0 pipeline= --vary seed
stages:       ; $(CURVE) --title stages     --where $(P) pipeline= --vary stage
logQ:         ; $(CURVE) --title logQ       --where library=$(LIB) logN=6 stage=encrypt_c0 pipeline= --vary logQ --xnorm over_q
libs:         ; $(CURVE) --title libs       --where logN=6 logQ=60 stage=encrypt_c0 pipeline= --vary library
boot: 		  ; $(REG)   --title boot --where  $(P2) --show
# --- servidor: una figura por op_step ---
PS = library=$(LIB) logN=6 logSlots=4 logQ=120 logDelta=40 bitsPerCoeff=144
add_inside:   ; $(CURVE) --title add_inside --where $(PS) stage=add "pipeline=add x2" --per op_step --split gap
mul_inside:   ; $(CURVE) --title mul_inside --where $(PS) stage=mul pipeline=mul      --per op_step --split gap
mul_reg:      ; $(REG)   --title mul_inside --where $(PS) stage=mul pipeline=mul      --op_step all
