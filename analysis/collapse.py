#!/usr/bin/env python3
"""Refresh the collapsed cache of a raw results dir by hand (see utils/collapse.py).

The plotting scripts already do this on their own every time they read a raw dir; this
command is for writing the cache somewhere else (the thesis repo) or rebuilding it.

    python3 collapse.py ../results                       # -> ../results/collapsed/
    python3 collapse.py ../results --out ../thesis/data  # the dir that goes to the thesis
    python3 collapse.py ../results --force               # rewrite every experiment
"""
import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from utils.collapse import collapse_dir  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw", help="results dir written by the C++ binaries")
    ap.add_argument("--out", default=None, help="default: <raw>/collapsed")
    ap.add_argument("--force", action="store_true", help="rewrite every experiment")
    args = ap.parse_args()
    collapse_dir(args.raw, args.out, force=args.force)
