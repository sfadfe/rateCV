from __future__ import annotations

import numpy as np

from . import config as C


def rmse(y: np.ndarray, yhat: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y - yhat) ** 2)))


def linreg(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    slope, intercept = np.polyfit(x, y, 1)
    yhat = intercept + slope * x
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return float(slope), float(intercept), r2


def median_filter(x: np.ndarray, w: int | None = None) -> np.ndarray:
    w = C.MEDIAN_W if w is None else w
    n = len(x)
    out = np.empty_like(x)
    r = w // 2
    for i in range(n):
        sl = x[max(0, i - r) : min(n, i + r + 1)]
        out[i] = np.nanmedian(sl) if np.isfinite(sl).any() else np.nan
    return out


def moving_avg(x: np.ndarray, k: int | None = None) -> np.ndarray:
    k = C.FIT_SMOOTH_K if k is None else k
    k = k if k % 2 else k + 1
    ker = np.ones(k) / k
    pad = k // 2
    return np.convolve(np.pad(x, pad, mode="edge"), ker, mode="valid")


def spike_cap(h: np.ndarray, max_up: float | None = None) -> np.ndarray:
    max_up = C.SPIKE_MAX_UP if max_up is None else max_up
    out = h.copy()
    last = None
    for i in range(len(out)):
        if not np.isfinite(out[i]):
            continue
        if last is None:
            last = out[i]
            continue
        if out[i] > last + max_up:
            out[i] = last
        else:
            last = out[i]
    return out


def gate(h: np.ndarray, band_fill: np.ndarray) -> np.ndarray:
    out = h.copy()
    ratio = band_fill / median_filter(band_fill, C.BAND_WIN)
    out[~(np.isfinite(ratio) & (ratio >= C.BAND_RATIO))] = np.nan
    return out


def interpolate(t: np.ndarray, h: np.ndarray) -> tuple[np.ndarray, int]:
    out = h.copy()
    idx = np.where(np.isfinite(out))[0]
    filled = 0
    for a, b in zip(idx[:-1], idx[1:]):
        if not 0 < b - a - 1 <= C.GAP_MAX:
            continue
        for j in range(a + 1, b):
            out[j] = out[a] + (out[b] - out[a]) * (t[j] - t[a]) / (t[b] - t[a])
            filled += 1
    return out, filled


def correct_h(h: np.ndarray) -> np.ndarray:
    return moving_avg(spike_cap(h))


def fit_first_order(t: np.ndarray, h: np.ndarray) -> dict:
    poured = np.isfinite(h) & (h >= C.H_START)
    if not np.any(poured):
        raise RuntimeError(f"h >= {C.H_START} mL 인 프레임이 없다 — 거품 검출 실패")
    i_start = int(np.argmax(poured))
    peak_win = (t >= t[i_start]) & (t <= t[i_start] + C.PEAK_WIN) & np.isfinite(h)
    i0 = int(np.where(peak_win)[0][np.argmax(h[peak_win])])
    t0 = float(t[i0])

    mask = (t >= t0) & np.isfinite(h) & ((t - t0) <= C.T_MAX)
    tt = t[mask] - t0
    hv = correct_h(h[mask])
    keep = hv >= C.H_STOP
    tt, hv = tt[keep], hv[keep]
    if len(tt) < 3:
        raise RuntimeError(f"적합 구간 프레임 {len(tt)}개 — 너무 적다")

    y = np.log(hv)
    slope, intercept, r2 = linreg(tt, y)
    yhat = intercept + slope * tt
    return dict(
        k=-slope,
        h0=float(hv[0]),
        t0=t0,
        n=len(tt),
        r2=r2,
        rmse=rmse(y, yhat),
        slope=slope,
        intercept=intercept,
        t_fit=tt,
        h_fit=hv,
        y_fit=y,
    )


def arrhenius(fits: dict) -> dict:
    names = list(C.CLIPS)
    T = np.array([C.CLIPS[n]["T_C"] + 273.15 for n in names])
    k = np.array([fits[n]["k"] for n in names])
    invT = 1.0 / T
    lnk = np.log(k)
    slope, intercept, r2 = linreg(invT, lnk)
    lnk_fit = intercept + slope * invT
    return dict(
        names=names,
        T=T,
        k=k,
        invT=invT,
        lnk=lnk,
        lnk_fit=lnk_fit,
        slope=slope,
        intercept=intercept,
        r2=r2,
        rmse=rmse(lnk, lnk_fit),
        Ea=-slope * C.R_GAS,
        A=float(np.exp(intercept)),
    )
