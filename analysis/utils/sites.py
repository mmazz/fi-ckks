"""Numbered injection sites for the side-by-side register maps.

Each enum is one figure. Every member is one panel:
    value = (panel number, stage, op_step)

The panel number is the one drawn in the red circle under the panel, i.e. the number of
that register in your datapath diagram. It only has to be unique inside its enum.

To add a figure: write a new enum and register it in DIAGRAMS.
"""
from enum import Enum


class ClientSite(Enum):
    """Client-side registers, in pipeline order (e.g. the mul_taco group)."""
    ENCODE     = (1, "encode", 0)
    ENCRYPT_C0 = (3, "encrypt_c0", 0)
    ENCRYPT_C1 = (4, "encrypt_c1", 0)
    DECRYPT_C0 = (7, "decrypt_c0", 0)
    DECRYPT_C1 = (8, "decrypt_c1", 0)
    DECODE     = (9, "decode", 0)


# Both HEAAN mult stages use the same op_step indices; they differ in the restores:
#   "mul_asplos" -> Scheme::multBitFlipAsplos  (group op_mul, op_mul_depth)
#   "mul"        -> Scheme::multBitFlip        (group asplos_mul: restores the inputs)
MUL = "mul_asplos"


class MulSite(Enum):
    """Registers of the HEAAN homomorphic multiplication.

    op_step is the flipIfStep() index in the fork. The member name says which register
    is flipped and right before which operation.
    PLACEHOLDER NUMBERING: number = op_step + 1. Replace it with the numbers of your
    datapath figure.
    """
    C1_AX_IN       = (1,  MUL, 0)    # c1.ax  before a1 + b1
    C1_BX_IN       = (2,  MUL, 1)    # c1.bx  before a1 + b1
    C2_AX_IN       = (3,  MUL, 2)    # c2.ax  before a2 + b2
    C2_BX_IN       = (4,  MUL, 3)    # c2.bx  before a2 + b2
    AXBX1          = (5,  MUL, 4)    # a1+b1  before (a1+b1)(a2+b2)
    AXBX2          = (6,  MUL, 5)    # a2+b2  before (a1+b1)(a2+b2)
    C1_AX_AXAX     = (7,  MUL, 6)    # c1.ax  before a1*a2
    C2_AX_AXAX     = (8,  MUL, 7)    # c2.ax  before a1*a2
    C1_BX_BXBX     = (9,  MUL, 8)    # c1.bx  before b1*b2
    C2_BX_BXBX     = (10, MUL, 9)    # c2.bx  before b1*b2
    AXAX_KEY_AX    = (11, MUL, 10)   # axax   before axax*key.ax
    KEY_AX         = (12, MUL, 11)   # key.ax before axax*key.ax
    AXAX_KEY_BX    = (13, MUL, 12)   # axax   before axax*key.bx
    KEY_BX         = (14, MUL, 13)   # key.bx before axax*key.bx
    AXMULT_SHIFT   = (15, MUL, 14)   # axmult before >> logQ
    BXMULT_SHIFT   = (16, MUL, 15)   # bxmult before >> logQ
    AXMULT_ADD     = (17, MUL, 16)   # axmult before += axbx1
    AXBX1_ADD      = (18, MUL, 17)   # axbx1  before axmult += axbx1
    AXMULT_SUB_BB  = (19, MUL, 18)   # axmult before -= bxbx
    BXBX_SUB       = (20, MUL, 19)   # bxbx   before axmult -= bxbx
    AXMULT_SUB_AA  = (21, MUL, 20)   # axmult before -= axax
    AXAX_SUB       = (22, MUL, 21)   # axax   before axmult -= axax
    BXMULT_ADD     = (23, MUL, 22)   # bxmult before += bxbx
    BXBX_ADD       = (24, MUL, 23)   # bxbx   before bxmult += bxbx
    AXMULT_OUT     = (25, MUL, 24)   # axmult output (before rescale)
    BXMULT_OUT     = (26, MUL, 25)   # bxmult output (before rescale)


DIAGRAMS = {
    "client": ClientSite,
    "mul": MulSite,
}


def select_sites(diagram, numbers=None):
    """[(number, stage, op_step)] for the requested panels, in the requested order.

    numbers=None -> every member of the enum, in declaration order.
    """
    if diagram not in DIAGRAMS:
        raise ValueError(f"unknown diagram {diagram!r}; available: {list(DIAGRAMS)}")
    sites = [member.value for member in DIAGRAMS[diagram]]
    by_number = {num: (num, stage, step) for num, stage, step in sites}
    if len(by_number) != len(sites):
        raise ValueError(f"diagram {diagram!r} repeats a panel number")
    if numbers is None:
        return sites
    if len(numbers) != len(set(numbers)):
        raise ValueError(f"--panels has repeated numbers: {numbers}")
    missing = [n for n in numbers if n not in by_number]
    if missing:
        raise ValueError(f"diagram {diagram!r} has no panel(s) {missing}; "
                         f"available: {sorted(by_number)}")
    return [by_number[n] for n in numbers]
