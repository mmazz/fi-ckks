#!/usr/bin/env python3
"""bit_curve.py, but HEAAN's 'encode' curve keeps only the bits above logQ, shifted down by
logQ, so it lines up with the other curves. Same CLI as bit_curve.py. The logDelta / logQ
lines are off: x means something different for the shifted curve.

  python3 encode_shift.py --title heaan_vs_openfhe --vary library \
      --where stage=encode pipeline= logN=6 logSlots=5 logQ=60 logDelta=40
  python3 encode_shift.py --title plain_vs_cipher --vary stage --band std \
      --where library=heaan pipeline= logN=6 logSlots=5 logQ=60 logDelta=40 bitsPerCoeff=64 \
      --query 'stage in ["encode", "encrypt_c0", "encrypt_c1"]'
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
import bit_curve as bc  # noqa: E402


def main():
    args = bc.parse_args()
    args.no_refs = True
    camps = bc.select_campaigns(args)
    try:
        data = bc.load_curve_data(camps, args.results, args.vary, args.drop_coeffs, args.metric,
                                  args.stat, args.rep_spread)
    except ValueError as e:
        sys.exit(f"ERROR: {e}\n  -> pin the column that differs with --where / --query")

    # HEAAN encode: keep only the bits above logQ and shift them so the first one lands at 1.
    shifted = (data["library"] == "heaan") & (data["stage"] == "encode")
    data = data[~shifted | (data["bit"] > data["logQ"])].copy()
    shifted = (data["library"] == "heaan") & (data["stage"] == "encode")
    data.loc[shifted, "bit"] -= data.loc[shifted, "logQ"]

    bc.make_figure(data, args.vary, args, args.title)


if __name__ == "__main__":
    main()
