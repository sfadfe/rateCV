from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import calib
from . import config as C
from . import cv as mcv

MOTION_MIN = 2.5
MOTION_K = 5.0
QUIET_MIN_S = 12
HEAD_S = 10
RESET_BUSY_S = 5
PRE_S = 3


def motion(files: list[Path]) -> np.ndarray:
    prev, out = None, []
    for fp in files:
        img = mcv.imread(fp)
        if img is None:
            raise SystemExit(f"읽기 실패: {fp}")
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        g = cv2.resize(g, (max(1, g.shape[1] // 8), max(1, g.shape[0] // 8)), interpolation=cv2.INTER_AREA).astype(np.float32)
        out.append(0.0 if prev is None else float(np.mean(np.abs(g - prev))))
        prev = g
    return np.array(out)


def height_series(files: list[Path], cal: dict) -> np.ndarray:
    cfg = {k: cal[k] for k in ("x0", "x1", "y100", "ppm")}
    foam, liq = [], []
    for fp in files:
        img = mcv.imread(fp)
        if img is None:
            raise SystemExit(f"읽기 실패: {fp}")
        m = mcv.measure(img, cfg)
        foam.append(m["foam_ml"])
        liq.append(m["liq_ml"])
    foam = np.array(foam, dtype=float)
    liq = np.array(liq, dtype=float)
    both = np.isfinite(foam) & np.isfinite(liq) & (foam - liq >= 20.0)
    liq_ref = float(np.nanmedian(liq[both])) if both.sum() >= 5 else float(np.nanmedian(liq))
    h = foam - np.where(np.isfinite(liq), liq, liq_ref)
    h[~np.isfinite(foam)] = np.nan
    return h


def quiet_runs(busy: np.ndarray) -> list[tuple[int, int]]:
    runs, i, n = [], 0, len(busy)
    while i < n:
        if busy[i]:
            i += 1
            continue
        j = i
        while j < n and not busy[j]:
            j += 1
        runs.append((i, j))
        i = j
    return runs


def _walk_back(a: int, busy: np.ndarray, floor: int) -> int:
    i = a - 1
    while i > floor:
        if busy[i]:
            i -= 1
            continue
        j = i
        while j > floor and not busy[j]:
            j -= 1
        if i - j + 1 >= QUIET_MIN_S:
            break
        i = j
    return max(floor, i + 1)


def experiments(files: list[Path]) -> tuple[list[dict], np.ndarray]:
    m = motion(files)
    thr = max(MOTION_MIN, MOTION_K * float(np.median(m[1:]))) if len(m) > 1 else MOTION_MIN
    busy = m > thr
    exps: list[dict] = []
    for a, b in quiet_runs(busy):
        if b - a < QUIET_MIN_S:
            continue
        if exps and int(busy[exps[-1]["decay_end"] : a].sum()) < RESET_BUSY_S:
            exps[-1]["decay_end"] = b
            continue
        floor = exps[-1]["decay_end"] if exps else 0
        start = max(floor, _walk_back(a, busy, floor - 1) - PRE_S)
        try:
            cal = calib.calibrate_files(files[start:b])
        except SystemExit:
            continue
        h = height_series(files[a : a + HEAD_S], cal)
        if not np.isfinite(h).any():
            continue
        h0 = float(np.nanmedian(h))
        if h0 < C.H_START:
            continue
        exps.append(dict(start=start, quiet=a, decay_end=b, h0=h0))
    return exps, busy


def segments(files: list[Path], n: int) -> list[tuple[int, int]]:
    d = files[0].parent
    exps, busy = experiments(files)
    found = ", ".join(f"{e['quiet'] // 60}:{e['quiet'] % 60:02d} (h≈{e['h0']:.0f} mL)" for e in exps) or "없음"
    print(f"{d.name}: 거품이 꺼지기 시작하는 구간 {len(exps)}개  {found}")
    if len(exps) != n:
        raise SystemExit(
            f"{d.name}: 실험을 {len(exps)}개 찾았다 (clips.json 은 {n}개)\n"
            "  실험 사이에 관을 비우고 20 초 이상 두었는지, 촬영 중 카메라 앞을 가리지 않았는지 봐라.\n"
            '  안 되면 data/raw/clips.json 의 각 클립에 "start"/"end" 를 분:초로 적어라 (예: "start": "3:10", "end": "5:40")')
    starts = [e["start"] for e in exps]
    last = len(files) - 1
    return [(s, (starts[i + 1] - 1) if i + 1 < len(starts) else last) for i, s in enumerate(starts)]
