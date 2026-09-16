from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import config as C
from .cv import imread

STACK_N = C.CALIB_STACK_N
BAND_Y0, BAND_Y1 = 0.55, 0.95
WIDTH_MIN, WIDTH_MAX = 0.05, 0.25
TICK_N = 10
PPM_MIN, PPM_MAX = 0.30, 0.90
TICK_TOL = C.CALIB_TICK_TOL
FOOT_LO, FOOT_HI = 0.5, 1.3
TICK_MIN = 7
FIT_RMS_MAX = 6.0


def _frame_paths(d: Path) -> list[Path]:
    files = sorted(d.glob("t*.jpg"))
    if not files:
        raise SystemExit(f"프레임 없음: {d} — src/extract.py 를 먼저 돌려라")
    return files


def _gray(path: Path) -> np.ndarray:
    img = imread(path)
    if img is None:
        raise SystemExit(f"읽기 실패: {path}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)


def _pick(files: list[Path], k: int) -> list[Path]:
    step = max(1, len(files) // k)
    return files[::step][:k]


def find_tube(files: list[Path]) -> tuple[int, int]:
    frames = np.stack([_gray(p) for p in _pick(files, STACK_N)])
    sd = frames.std(axis=0)
    h, w = sd.shape
    col = sd[int(h * BAND_Y0) : int(h * BAND_Y1)].mean(axis=0)
    col = cv2.blur(col.reshape(-1, 1), (1, 9)).ravel()

    thr = 0.5 * float(col.max())
    on = col > thr
    runs, i = [], 0
    while i < w:
        if on[i]:
            j = i
            while j < w and on[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    runs = [r for r in runs if int(w * WIDTH_MIN) <= r[1] - r[0] <= int(w * WIDTH_MAX)]
    if not runs:
        raise SystemExit("실린더를 못 찾았다 — 프레임에 관이 제대로 잡혔는지 봐라")
    x0, x1 = max(runs, key=lambda r: float(col[r[0] : r[1]].sum()))
    return int(x0), int(x1)


def find_foot(files: list[Path], x0: int, x1: int) -> int:
    g = np.median(np.stack([_gray(p) for p in _pick(files, STACK_N)]), axis=0)
    h, w = g.shape
    W, cx = x1 - x0, (x0 + x1) // 2
    ref = float(np.median(g[int(h * 0.60) : int(h * 0.70), x0 + 5 : x1 - 5]))
    bg = float(np.median(np.r_[
        g[int(h * 0.60) : int(h * 0.75), max(0, x0 - 70) : max(1, x0 - 10)].ravel(),
        g[int(h * 0.60) : int(h * 0.75), min(w - 1, x1 + 10) : min(w, x1 + 70)].ravel()]))
    thr = (ref + bg) / 2
    lo, hi = max(0, cx - 220), min(w, cx + 220)
    c = (hi - lo) // 2
    for y in range(int(h * 0.85), h):
        row = cv2.blur(g[y, lo:hi].reshape(-1, 1), (1, 7)).ravel() > thr
        if not row[c]:
            continue
        L = c
        while L > 0 and row[L - 1]:
            L -= 1
        R = c
        while R < len(row) - 1 and row[R + 1]:
            R += 1
        if R - L > 1.30 * W:
            return y
    raise SystemExit("받침을 못 찾았다 — 실린더 밑부분이 프레임에 들어오는지 봐라")


def _ink_profile(frames: list[np.ndarray], a: int, b: int) -> np.ndarray:
    acc = None
    for g in frames:
        p = cv2.blur(g[:, a:b].min(axis=1).reshape(-1, 1), (1, 5)).ravel()
        base = cv2.blur(p.reshape(-1, 1), (1, 121)).ravel()
        d = np.maximum(base - p, 0.0)
        d = d / (d.std() + 1e-6)
        acc = d if acc is None else acc + d
    return acc / len(frames)


def _ink_peaks(d: np.ndarray) -> list[int]:
    h = len(d)
    lo, hi = int(h * 0.55), int(h * 0.98)
    cut = float(np.percentile(d[lo:hi], 70))
    peaks: list[int] = []
    for y in range(lo, hi - 1):
        if d[y] >= d[y - 1] and d[y] >= d[y + 1] and d[y] > cut:
            if not peaks or y - peaks[-1] > 20:
                peaks.append(y)
            elif d[y] > d[peaks[-1]]:
                peaks[-1] = y
    return peaks


def _refine(ys: np.ndarray, top: float, P: float, rounds: int = 4):
    hit = idx = None
    for _ in range(rounds):
        grid = top + P * np.arange(TICK_N)
        h, k = [], []
        for m, gy in enumerate(grid):
            j = int(np.argmin(np.abs(ys - gy)))
            if abs(ys[j] - gy) <= TICK_TOL * P and (not h or ys[j] != h[-1]):
                h.append(ys[j])
                k.append(m)
        if len(h) < TICK_MIN:
            return None
        hit, idx = np.array(h, dtype=float), np.array(k, dtype=float)
        P, top = np.polyfit(idx, hit, 1)
    return hit, idx, float(top), float(P)


def _best_ladder(peaks: list[int], d: np.ndarray, p_lo: float, p_hi: float, y_foot: int):
    best = None
    ys = np.array(peaks, dtype=float)
    for i in range(len(peaks)):
        for j in range(i + 1, len(peaks)):
            for span in range(1, TICK_N):
                P = (peaks[j] - peaks[i]) / span
                if not (p_lo <= P <= p_hi):
                    continue
                fit = _refine(ys, float(peaks[i]), P)
                if fit is None:
                    continue
                hit, idx, top, P2 = fit
                if not (FOOT_LO * P2 <= y_foot - (top + 10 * P2) <= FOOT_HI * P2):
                    continue
                rms = float(np.sqrt(np.mean(np.square(hit - (top + P2 * idx)))))
                score = (len(hit), -round(rms, 3), round(float(np.mean(d[hit.astype(int)])), 4))
                if best is None or score > best[0]:
                    best = (score, hit.astype(int).tolist(), top, P2, rms)
    if best is None:
        return None
    return dict(ticks=best[1], y100=best[2], ppm=best[3] / 10.0, rms=best[4])


def find_scale(files: list[Path], x0: int, x1: int, y_foot: int) -> dict:
    frames = [_gray(p) for p in _pick(files, STACK_N)]
    w = frames[0].shape[1]
    W = x1 - x0
    cands = []
    for f in np.arange(0.20, 0.80, 0.05):
        a = x0 + int(W * f)
        b = min(w, a + int(W * 0.45))
        if b - a < 10:
            continue
        d = _ink_profile(frames, a, b)
        peaks = _ink_peaks(d)
        if len(peaks) < TICK_MIN:
            continue
        lad = _best_ladder(peaks, d, PPM_MIN * W, PPM_MAX * W, y_foot)
        if lad is None:
            continue
        strength = float(np.mean(d[lad["ticks"]]) / (np.mean(d[d > 0]) + 1e-9))
        cands.append(dict(n=len(lad["ticks"]), rms=lad["rms"], strength=strength,
                          y100=lad["y100"], ppm=lad["ppm"], band=(a, b), ticks=lad["ticks"]))
    if not cands:
        raise SystemExit("눈금을 못 읽었다 — 프레임에 눈금 숫자가 보이는지 봐라")
    best = max(cands, key=lambda c: (c["n"], -round(c["rms"], 3), round(c["strength"], 3)))
    if best["rms"] > FIT_RMS_MAX:
        raise SystemExit(f"눈금 적합이 나쁘다 (잔차 {best['rms']:.1f} px) — 오버레이로 확인해라")
    return best


def calibrate(d: Path) -> dict:
    return calibrate_files(_frame_paths(d))


def calibrate_files(files: list[Path]) -> dict:
    x0, x1 = find_tube(files)
    y_foot = find_foot(files, x0, x1)
    sc = find_scale(files, x0, x1, y_foot)
    return dict(
        x0=x0,
        x1=x1,
        y100=round(sc["y100"], 2),
        ppm=round(sc["ppm"], 4),
        y_foot=y_foot,
        n_ticks=sc["n"],
        fit_rms=round(sc["rms"], 2),
        ticks=[int(t) for t in sc["ticks"]],
        band=[int(sc["band"][0]), int(sc["band"][1])],
    )


def save_overlay(d: Path, cal: dict, path: Path) -> None:
    img = imread(_frame_paths(d)[0])
    x0, x1, y100, ppm = cal["x0"], cal["x1"], cal["y100"], cal["ppm"]
    cv2.rectangle(img, (x0, int(y100)), (x1, int(y100 + 100 * ppm)), (0, 255, 0), 2)
    for ml in range(0, 101, 10):
        y = int(round(y100 + (100 - ml) * ppm))
        cv2.line(img, (x0 - 12, y), (x1 + 12, y), (255, 0, 255), 1)
        cv2.putText(img, str(ml), (x1 + 16, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (255, 0, 255), 1, cv2.LINE_AA)
    for t in cal["ticks"]:
        cv2.line(img, (x0 - 30, t), (x0 - 14, t), (0, 200, 255), 2)
    y_lo = max(0, int(y100) - 80)
    y_hi = min(img.shape[0], int(y100 + 100 * ppm) + 80)
    crop = img[y_lo:y_hi, max(0, x0 - 60) : min(img.shape[1], x1 + 70)]
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".jpg", crop)
    if not ok:
        raise RuntimeError(f"이미지 인코딩 실패: {path}")
    buf.tofile(str(path))
