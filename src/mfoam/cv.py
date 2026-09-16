from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import config as C


def imread(path: Path | str) -> np.ndarray | None:
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def imwrite(path: Path | str, img: np.ndarray) -> None:
    p = Path(path)
    ok, buf = cv2.imencode(p.suffix or ".jpg", img)
    if not ok:
        raise RuntimeError(f"이미지 인코딩 실패: {p}")
    buf.tofile(str(p))


def smooth(x: np.ndarray, k: int | None = None) -> np.ndarray:
    k = C.SMOOTH_K if k is None else k
    k = k if k % 2 else k + 1
    ker = np.ones(k) / k
    pad = k // 2
    return np.convolve(np.pad(x, pad, mode="edge"), ker, mode="valid")


def first_run(arr: np.ndarray, thresh: float, min_len: int) -> int | None:
    above = arr > thresh
    i, n = 0, len(above)
    while i < n:
        if above[i]:
            j = i
            while j < n and above[j]:
                j += 1
            if j - i >= min_len:
                return i
            i = j
        else:
            i += 1
    return None


def y_to_ml(y: float, y100: float, ppm: float) -> float:
    return 100.0 - (y - y100) / ppm


def measure(bgr: np.ndarray, cfg: dict) -> dict:
    h_img = bgr.shape[0]
    x0, x1 = cfg["x0"], cfg["x1"]
    y100, ppm = cfg["y100"], cfg["ppm"]
    y0ml = int(y100 + 100 * ppm)
    y_top = max(0, int(y100) - 50)
    y_bot = min(h_img, y0ml + 40)
    w = x1 - x0
    cx0 = x0 + int(w * 0.28)
    cx1 = x0 + int(w * 0.72)
    strip = bgr[y_top:y_bot, cx0:cx1]
    hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    foam = ((H >= 5) & (H <= 45) & (V >= 95) & (S >= 10) & (S <= 110)).astype(np.float32)
    liquid = ((V <= 85) & (S >= 35) & (H <= 30)).astype(np.float32)
    foam_s = smooth(foam.mean(axis=1))
    liq_s = smooth(liquid.mean(axis=1))
    nan = float("nan")

    fi = first_run(foam_s, C.FOAM_THRESH, C.FOAM_MINLEN)
    if fi is None:
        return dict(foam_ml=nan, liq_ml=nan, band_fill=nan, fy=None, ly=None)
    fy = y_top + int(fi)
    foam_ml = y_to_ml(fy, y100, ppm)

    li_rel = first_run(liq_s[int(fi) + 10 :], C.LIQ_THRESH, C.LIQ_MINLEN)
    if li_rel is None:
        ly, liq_ml = None, nan
        band_end = min(len(foam_s), int(y0ml - y_top))
    else:
        ly = y_top + int(fi) + 10 + int(li_rel)
        liq_ml = y_to_ml(ly, y100, ppm)
        band_end = int(ly - y_top)

    band = foam_s[int(fi) : max(int(fi) + 1, band_end)]
    band_fill = float(band.mean()) if band.size else nan

    return dict(
        foam_ml=float(foam_ml),
        liq_ml=float(liq_ml),
        band_fill=band_fill,
        fy=fy,
        ly=ly,
    )
