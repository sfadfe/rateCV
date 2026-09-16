from __future__ import annotations

import json
import py_compile
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mfoam import config as C
from mfoam import prov

ROOT = C.ROOT
DIST = ROOT / "dist"
TEMPL = ROOT / "tools" / "dist"
PY_FILES = ["extract.py", "measure.py", "analyze.py", "verify.py", "pack.py", "repro.py",
            "mfoam/__init__.py", "mfoam/config.py", "mfoam/prov.py", "mfoam/calib.py",
            "mfoam/cv.py", "mfoam/fit.py", "mfoam/split.py"]
KEY_LINE = "_EMBEDDED_KEY: str | None = None"


def embed_key(src: str, key: str) -> str:
    assert src.count(KEY_LINE) == 1, "prov.py 의 _EMBEDDED_KEY 줄을 못 찾았다"
    return src.replace(KEY_LINE, f"_EMBEDDED_KEY: str | None = {key!r}")


CLIPS_TEMPLATE = {
    "team": "이름",
    "clips": {
        "cold": {"stem": "얼음물_영상이름_확장자빼고", "T_C": 15.0},
        "rt": {"stem": "상온_영상이름_확장자빼고", "T_C": 25.0},
        "hot": {"stem": "물중탕_영상이름_확장자빼고", "T_C": 55.0},
    },
}


def main() -> None:
    key = C._FILE_ENV.get("MFOAM_PROV_KEY", "")
    if not key:
        raise SystemExit(".env 에 MFOAM_PROV_KEY 가 없다")
    if prov.latest("analyze")["tag"] == prov.UNSIGNED:
        raise SystemExit("최신 analyze 기록이 미서명이다 — 키 넣고 다시 돌려라")

    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "data" / "raw").mkdir(parents=True)
    (DIST / "results").mkdir()

    for rel in PY_FILES:
        src = ROOT / "src" / rel
        text = src.read_text(encoding="utf-8")
        dst_py = DIST / "src" / rel
        dst_py.parent.mkdir(parents=True, exist_ok=True)
        dst_py.write_text(text, encoding="utf-8", newline="\n")

        if rel == "mfoam/prov.py":
            tmp = DIST / "_prov_keyed.py"
            tmp.write_text(embed_key(text, key), encoding="utf-8", newline="\n")
            src = tmp
        pyc = DIST / "bin" / Path(rel).with_suffix(".pyc")
        pyc.parent.mkdir(parents=True, exist_ok=True)
        py_compile.compile(str(src), cfile=str(pyc), dfile=rel, doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        if rel == "mfoam/prov.py":
            src.unlink()

    for name in ("run.py", "run.bat", "run.sh"):
        shutil.copy(ROOT / name, DIST / name)
    shutil.copy(TEMPL / "README.md", DIST / "README.md")
    shutil.copy(ROOT / "requirements.txt", DIST / "requirements.txt")
    (DIST / "data" / "raw" / "여기에_영상_넣기.txt").write_text(
        "README.md 3번 참고. 영상을 이 폴더에 넣고 clips.json 에 파일 이름(확장자 빼고)과 물 온도를 적는다.\n",
        encoding="utf-8")
    (DIST / "data" / "raw" / "clips.json").write_text(
        json.dumps(CLIPS_TEMPLATE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    n = sum(1 for _ in (DIST / "bin").rglob("*.pyc"))
    print(f"dist/ 생성  pyc {n}개 (Python {ver} 전용)  키 내장  clips.json 틀")


if __name__ == "__main__":
    main()
