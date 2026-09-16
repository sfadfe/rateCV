import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BIN = ROOT / "bin"
STEPS = ["extract", "measure", "analyze", "verify", "pack"]

NEED = (3, 12)
if sys.version_info[:2] != NEED:
    raise SystemExit(f"Python {NEED[0]}.{NEED[1]} 이 필요하다 (지금 {sys.version.split()[0]}).")

if BIN.is_dir():
    def prog(step: str) -> Path:
        return BIN / f"{step}.pyc"
else:
    sys.path.insert(0, str(ROOT / "src"))
    from mfoam import prov

    if not prov.signed():
        raise SystemExit("서명키 없음. .env 에 MFOAM_PROV_KEY 를 적어라 (README.md 1-5).")

    def prog(step: str) -> Path:
        return ROOT / "src" / f"{step}.py"

for step in STEPS:
    args = [sys.executable, str(prog(step))]
    if step == "extract" and "--force" in sys.argv[1:]:
        args.append("--force")
    if step == "pack" and "--no-video" in sys.argv[1:]:
        args.append("--no-video")
    print(f"\n===== {step} =====", flush=True)
    r = subprocess.run(args)
    if r.returncode != 0:
        raise SystemExit(f"\n{step} 단계에서 멈췄다 (코드 {r.returncode}). 위 메시지를 봐라.")

print("\n전부 끝. results/summary.txt 와 이 폴더에 생긴 submit_*.zip 이 결과물이다.")
