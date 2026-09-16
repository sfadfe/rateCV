from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RAW = ROOT / "data" / "raw"
FRAMES = ROOT / "data" / "frames"
RESULTS = ROOT / "results"
FIG = RESULTS / "fig"
OVERLAYS = RESULTS / "overlays"
CSV = RESULTS / "timeseries.csv"
PROV = RESULTS / "provenance.jsonl"

R_GAS = 8.314

VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".avi", ".mkv")

FPS = 1.0
JPEG_Q = 2

SMOOTH_K = 9
FOAM_THRESH = 0.22
FOAM_MINLEN = 6
LIQ_THRESH = 0.28
LIQ_MINLEN = 8

BAND_RATIO = 0.70
BAND_WIN = 11
GAP_MAX = 3
SPIKE_MAX_UP = 1.5
MEDIAN_W = 5

H_START = 35.0
H_STOP = 12.0
T_MAX = 120.0
PEAK_WIN = 12.0
FIT_SMOOTH_K = 9

CALIB_STACK_N = 16
CALIB_TICK_TOL = 0.12

REF_TOL = 0.04
REFERENCE = RESULTS / "reference.json"


def _parse_time(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    parts = [float(x) for x in str(v).strip().split(":")]
    if len(parts) > 3:
        raise ValueError(f"시각 형식이 이상하다: {v!r}")
    t = 0.0
    for x in parts:
        t = t * 60 + x
    return t


def _clip(stem: str, t_c: float, start=None, end=None) -> dict:
    s, e = _parse_time(start), _parse_time(end)
    if s is not None and e is not None and e <= s:
        raise ValueError(f"end({end}) 가 start({start}) 보다 앞이다")
    return dict(
        stem=stem,
        T_C=float(t_c),
        label=f"{float(t_c):.1f} °C",
        start=s,
        end=e,
    )


def _span(c: dict) -> str:
    if c["start"] is None and c["end"] is None:
        return ""
    return f"{'' if c['start'] is None else f'{c['start']:g}'}-{'' if c['end'] is None else f'{c['end']:g}'}"


CLIPS_FILE = RAW / "clips.json"
_DEFAULT_CLIPS = {
    "hot": _clip("20260824_142727", 54.7),
    "rt": _clip("20260824_144012", 27.2),
    "cold": _clip("20260824_142918", 14.2),
}


def _load_clips_file(path: Path) -> tuple[dict, str]:
    import json

    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        clips = doc["clips"] if isinstance(doc, dict) and "clips" in doc else doc
        out = {str(n): _clip(str(c["stem"]), float(c["T_C"]), c.get("start"), c.get("end"))
               for n, c in clips.items()}
        team = str(doc.get("team", "")) if isinstance(doc, dict) else ""
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise SystemExit(f"{path} 를 못 읽었다: {e}\n"
                         '  형식: {"team": "3조", "clips": {"hot": {"stem": "영상이름", "T_C": 54.7}}}\n'
                         '  한 영상에 이어 찍었으면: {"stem": "영상이름", "T_C": 54.7, "start": "0:00", "end": "2:30"}')
    if not out:
        raise SystemExit(f"{path} 의 clips 가 비었다")
    dup = {}
    for n, c in out.items():
        dup.setdefault(c["stem"], []).append(n)
    for stem, names in dup.items():
        spans = [bool(_span(out[n])) for n in names]
        if len(names) > 1 and any(spans) and not all(spans):
            raise SystemExit(f"{path}: 영상 {stem} 을 {', '.join(names)} 가 같이 쓴다 — "
                             '"start"/"end" 는 전부 적거나 (수동 구간) 전부 빼라 (자동 분할)')
    return out, team


if CLIPS_FILE.exists():
    CLIPS, TEAM = _load_clips_file(CLIPS_FILE)
    CLIPS_SOURCE = "data/raw/clips.json"
else:
    CLIPS, TEAM, CLIPS_SOURCE = dict(_DEFAULT_CLIPS), "", "builtin"


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


_FILE_ENV = _parse_env_file(ROOT / ".env")


def ensure_dirs() -> None:
    for d in (RAW, FRAMES, RESULTS, FIG, OVERLAYS):
        d.mkdir(parents=True, exist_ok=True)


def stem_groups() -> dict[str, list[str]]:
    g: dict[str, list[str]] = {}
    for n, c in CLIPS.items():
        g.setdefault(c["stem"], []).append(n)
    return g


def frames_dir(name: str) -> Path:
    c = CLIPS[name]
    whole = not _span(c) and len(stem_groups()[c["stem"]]) == 1
    return FRAMES / (c["stem"] if whole else f"{c['stem']}_{name}")


def rel(p: Path) -> str:
    p = Path(p)
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.resolve().as_posix()


def find_videos() -> list[Path]:
    if not RAW.is_dir():
        return []
    return sorted(
        (p for p in RAW.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS),
        key=lambda p: p.name,
    )


def video_of(stem: str) -> Path | None:
    for p in find_videos():
        if p.stem == stem:
            return p
    return None


def clip_of(stem: str) -> str | None:
    for name, cfg in CLIPS.items():
        if cfg["stem"] == stem:
            return name
    return None


def unregistered_videos() -> list[Path]:
    return [p for p in find_videos() if clip_of(p.stem) is None]


def clip_template(video: Path) -> str:
    name = re.sub(r"\W+", "_", video.stem, flags=re.UNICODE).strip("_").lower() or "new"
    return f'    "{name}": {{"stem": "{video.stem}", "T_C": <온도>}},'


_VALUES = {
    "MFOAM_FPS": FPS,
    "MFOAM_CALIB_STACK_N": CALIB_STACK_N,
    "MFOAM_CALIB_TICK_TOL": CALIB_TICK_TOL,
    "MFOAM_JPEG_Q": JPEG_Q,
    "MFOAM_SMOOTH_K": SMOOTH_K,
    "MFOAM_FOAM_THRESH": FOAM_THRESH,
    "MFOAM_FOAM_MINLEN": FOAM_MINLEN,
    "MFOAM_LIQ_THRESH": LIQ_THRESH,
    "MFOAM_LIQ_MINLEN": LIQ_MINLEN,
    "MFOAM_BAND_RATIO": BAND_RATIO,
    "MFOAM_BAND_WIN": BAND_WIN,
    "MFOAM_GAP_MAX": GAP_MAX,
    "MFOAM_SPIKE_MAX_UP": SPIKE_MAX_UP,
    "MFOAM_MEDIAN_W": MEDIAN_W,
    "MFOAM_H_START": H_START,
    "MFOAM_H_STOP": H_STOP,
    "MFOAM_T_MAX": T_MAX,
    "MFOAM_PEAK_WIN": PEAK_WIN,
    "MFOAM_FIT_SMOOTH_K": FIT_SMOOTH_K,
}


def snapshot(keys: list[str]) -> dict[str, str]:
    out = {k: f"{_VALUES[k]:g}" for k in keys if k in _VALUES}
    if "CLIPS" in keys:
        out["CLIPS"] = {
            n: f"{c['stem']},{c['T_C']:g}" + (f",{_span(c)}" if _span(c) else "")
            for n, c in CLIPS.items()
        }
        out["CLIPS_SOURCE"] = CLIPS_SOURCE
        if TEAM:
            out["TEAM"] = TEAM
    return out


EXTRACT_KEYS = ["MFOAM_FPS", "MFOAM_JPEG_Q", "CLIPS"]
MEASURE_KEYS = [
    "MFOAM_CALIB_STACK_N",
    "MFOAM_CALIB_TICK_TOL",
    "MFOAM_SMOOTH_K",
    "MFOAM_FOAM_THRESH",
    "MFOAM_FOAM_MINLEN",
    "MFOAM_LIQ_THRESH",
    "MFOAM_LIQ_MINLEN",
    "CLIPS",
]
ANALYZE_KEYS = [
    "MFOAM_BAND_RATIO",
    "MFOAM_BAND_WIN",
    "MFOAM_GAP_MAX",
    "MFOAM_SPIKE_MAX_UP",
    "MFOAM_MEDIAN_W",
    "MFOAM_H_START",
    "MFOAM_H_STOP",
    "MFOAM_T_MAX",
    "MFOAM_PEAK_WIN",
    "MFOAM_FIT_SMOOTH_K",
    "CLIPS",
]
