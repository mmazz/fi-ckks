"""Helpers para definir y correr campanias de fi-ckks.

Una corrida es un dict de flags del binario (sin '--'), mas 'binary' (nombre en build/bin).
Valores None o "" no se pasan. El registry de --results_dir saltea las campanias que ya
terminaron, asi que volver a correr un grupo es seguro: solo corre lo que falta.
"""
import argparse
import fnmatch
import itertools
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "build" / "bin"


def grid(fixed, **sweep):
    """Producto cartesiano: grid(base, stage=["a", "b"], seed=[1, 2]) -> 4 corridas."""
    keys = list(sweep)
    return [{**fixed, **dict(zip(keys, combo))}
            for combo in itertools.product(*(list(sweep[k]) for k in keys))]


def command(run):
    run = dict(run)
    cmd = [str(BIN_DIR / run.pop("binary"))]
    for key, value in run.items():
        if value is None or value == "":
            continue
        cmd += [f"--{key}", str(value)]
    return cmd

def dedupe(runs):
    """Drop repeated configs. Two identical runs launched in parallel get the same
    campaign_id and write the same data file, so they must never both be scheduled."""
    seen, out = set(), []
    for r in runs:
        key = tuple(sorted((k, str(v)) for k, v in r.items() if v is not None and v != ""))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def select(groups, patterns):
    """Group names from the command line. Accepts exact names, 'all' and shell-style
    patterns ('*_taco', 'Open_*'), so a whole family of groups runs with one argument."""
    names = []
    for p in patterns:
        hits = list(groups) if p == "all" else fnmatch.filter(groups, p)
        if not hits:
            sys.exit(f"no group matches '{p}'. Available: {list(groups)}")
        names += [n for n in hits if n not in names]
    return names

def run_all(runs, jobs, dry_run):
    cmds = [command(r) for r in runs]
    if dry_run:
        for cmd in cmds:
            print(shlex.join(cmd))
        return 0

    failed = 0
    start = time.time()
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(subprocess.run, cmd, capture_output=True, text=True): cmd for cmd in cmds}
        for i, fut in enumerate(as_completed(futures), 1):
            cmd, res = futures[fut], fut.result()
            status = "OK  " if res.returncode == 0 else "FAIL"
            print(f"[{i}/{len(cmds)} {time.time() - start:7.0f}s] {status} {shlex.join(cmd[1:])}", flush=True)
            if res.returncode != 0:
                failed += 1
                for line in (res.stderr or res.stdout).strip().splitlines()[-3:]:
                    print(f"        {line}")
    print(f"{len(cmds) - failed} ok, {failed} fail")
    return failed


def main(groups, description):
    ap = argparse.ArgumentParser(description=description,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("groups", nargs="*", help="groups to run")
    ap.add_argument("--jobs", type=int, default=1, help="parallel processes")
    ap.add_argument("--dry-run", action="store_true", help="only prints the comands")
    args = ap.parse_args()

    if not args.groups:
        for name, runs in groups.items():
            print(f"{name:24s} {len(runs):5d} runs")
        return
    names = select(groups, args.groups)
    runs = [r for n in names for r in groups[n]]
    unique = dedupe(runs)
    if len(unique) < len(runs):
        print(f"{len(runs) - len(unique)} repeated run(s) dropped (same config in more than one group)",
              file=sys.stderr)
    runs = unique

    sys.exit(1 if run_all(runs, args.jobs, args.dry_run) else 0)
