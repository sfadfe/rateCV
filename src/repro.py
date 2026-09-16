from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfoam import config as C
from mfoam import prov

STEPS = ["measure", "analyze"]


def run(step: str) -> None:
    r = subprocess.run([sys.executable, str(Path(__file__).with_name(step + Path(__file__).suffix))],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        raise SystemExit(f"{step} 실패")


def snapshot() -> dict[str, str]:
    out = {
        "timeseries.csv 값": prov.csv_digest(C.CSV),
        "timeseries.csv 파일": prov.sha256_file(C.CSV),
        "summary.txt": prov.sha256_file(C.RESULTS / "summary.txt"),
    }
    for p in sorted(C.FIG.glob("*.png")):
        out[f"fig/{p.name}"] = prov.sha256_file(p)
    out["overlays/"] = prov.tree_digest(C.OVERLAYS)["digest"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="중간 산출물을 지우지 않는다")
    args = ap.parse_args()

    runs = []
    for i in (1, 2):
        if not args.keep:
            shutil.rmtree(C.FIG, ignore_errors=True)
            shutil.rmtree(C.OVERLAYS, ignore_errors=True)
        for step in STEPS:
            print(f"{i}회차 {step} …")
            run(step)
        runs.append(snapshot())

    a, b = runs
    bad = 0
    print()
    for k in a:
        same = a[k] == b[k]
        bad += not same
        print(f"  {'ok' if same else '!!'} {k:24s} {a[k][:16]}" + ("" if same else f" != {b[k][:16]}"))
    print()
    if bad:
        raise SystemExit(f"{bad} 개가 두 번 돌렸을 때 달라진다 — 재현 안 됨")
    print("두 번 돌린 결과가 전부 같다 — 재현 됨")


if __name__ == "__main__":
    main()
