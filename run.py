import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BIN = ROOT / "bin"
RESULTS = ROOT / "results"
LOG = RESULTS / "run_log.txt"
OUT = RESULTS / "results.txt"
STEPS = ["extract", "measure", "analyze", "verify", "pack"]

# 콘솔에는 ASCII 만 찍는다 (Windows 콘솔·파이프 인코딩 문제). 단계 출력은 LOG, 결과값은 OUT.
NEED = (3, 12)
if sys.version_info[:2] != NEED:
    raise SystemExit(f"Python {NEED[0]}.{NEED[1]} required (found {sys.version.split()[0]}).")

if BIN.is_dir():
    CODE = BIN

    def prog(step: str) -> Path:
        return BIN / f"{step}.pyc"
else:
    CODE = ROOT / "src"
    sys.path.insert(0, str(CODE))
    from mfoam import prov

    if not prov.signed():
        raise SystemExit("No signing key. Put MFOAM_PROV_KEY in .env (README.md 1-5).")

    def prog(step: str) -> Path:
        return ROOT / "src" / f"{step}.py"


def results_text() -> str:
    if str(CODE) not in sys.path:
        sys.path.insert(0, str(CODE))
    from mfoam import config as C

    an = None
    for line in (RESULTS / "provenance.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line)
            if e["stage"] == "analyze":
                an = e
    fits, arr = an["outputs"]["fits"], an["outputs"]["arrhenius"]

    row = "{:<6} {:>6} {:>7}  {:<13} {:>6} {:>7} {:>4}  {:<6}  {:<10} {:>7} {:>6}"
    lines = [row.format("clip", "T_C", "T_K", "k (1/s)", "t0 (s)", "h0 (mL)", "n",
                        "R2", "RMSE(ln h)", "dropped", "filled")]
    for name, cfg in C.CLIPS.items():
        f = fits[name]
        lines.append(row.format(name, f"{cfg['T_C']:g}", f"{cfg['T_C'] + 273.15:.2f}", f"{f['k']:.6e}",
                                f"{f['t0']:.0f}", f"{f['h0']:.2f}", f["n"], f"{f['r2']:.4f}",
                                f"{f['rmse']:.4f}", f["dropped"], f["filled"]))
    lines.append("")
    if arr is None:
        lines.append("Arrhenius: skipped (needs 2+ clips at different temperatures)")
    else:
        lines += [
            f"Ea             = {arr['Ea'] / 1000:.2f} kJ/mol  ({arr['Ea']:.1f} J/mol)",
            f"A              = {arr['A']:.6e} 1/s",
            f"Arrhenius R2   = {arr['r2']:.4f}",
            f"Arrhenius RMSE = {arr['rmse']:.4f}  (ln k)",
        ]
    return "\n".join(lines) + "\n"


RESULTS.mkdir(exist_ok=True)
OUT.unlink(missing_ok=True)
env = dict(os.environ, PYTHONIOENCODING="utf-8")
with LOG.open("w", encoding="utf-8") as log:
    for step in STEPS:
        args = [sys.executable, str(prog(step))]
        if step == "extract" and "--force" in sys.argv[1:]:
            args.append("--force")
        if step == "pack":
            args.append("--no-video")
        print(f"{step:<8} ...", end=" ", flush=True)
        log.write(f"\n===== {step} =====\n")
        log.flush()
        t = time.monotonic()
        r = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, env=env)
        if r.returncode != 0:
            print("FAILED")
            raise SystemExit(f"\n{step} failed (exit code {r.returncode}). "
                             f"See results/run_log.txt for the message.")
        print(f"ok ({time.monotonic() - t:.0f} s)")

text = results_text()
OUT.write_text(text, encoding="utf-8", newline="\n")
print("\n" + text)
print("Done.")
print("  results : results/results.txt")
print("  log     : results/run_log.txt")
print("  submit  : submit_*.zip in this folder")
