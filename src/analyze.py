from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfoam import config as C
from mfoam import fit as F
from mfoam import prov


def load_csv(path: Path) -> dict:
    raw = np.genfromtxt(path, delimiter=",", names=True, dtype=None, encoding="utf-8")
    out = {}
    for name in C.CLIPS:
        m = raw["clip"] == name
        if not m.any():
            raise SystemExit(f"CSV 에 clip={name} 행이 없다")
        out[name] = dict(
            t=raw["t_s"][m].astype(float),
            foam=raw["foam_mL"][m].astype(float),
            liq=raw["liq_mL"][m].astype(float),
            h=raw["h_mL"][m].astype(float),
            band=raw["band_fill"][m].astype(float),
        )
    return out


def prepare(d: dict, t: np.ndarray) -> tuple[np.ndarray, int, int]:
    h = F.gate(d["h"], d["band"])
    dropped = int(np.isfinite(d["h"]).sum() - np.isfinite(h).sum())
    h, filled = F.interpolate(t, h)
    return F.median_filter(h), dropped, filled


def plot_ln(fits: dict, path: Path, with_fit: bool) -> None:
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    for name, cfg in C.CLIPS.items():
        f = fits[name]
        (line,) = ax.plot(f["t_fit"], f["y_fit"], lw=1.5, label=cfg["label"])
        if with_fit:
            tt = np.linspace(0.0, float(f["t_fit"].max()), 200)
            ax.plot(tt, f["intercept"] + f["slope"] * tt, "--", lw=1.1, color=line.get_color())
    ax.set_xlabel("t / s")
    ax.set_ylabel("ln h")
    ax.set_title("ln h – t")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_arrhenius(arr: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    xx = np.linspace(arr["invT"].min() * 0.985, arr["invT"].max() * 1.015, 80)
    yy = arr["intercept"] + arr["slope"] * xx
    ax.plot(xx, yy, "k-", lw=1.2, label="Arrhenius")
    ax.plot(arr["invT"], arr["lnk"], "o", ms=7, c="k", zorder=3, label="exp")
    for inv, lnk, cfg in zip(arr["invT"], arr["lnk"], C.CLIPS.values()):
        ax.annotate(cfg["label"], (inv, lnk), textcoords="offset points", xytext=(7, -9))
    pad_x = 0.08 * (xx.max() - xx.min())
    pad_y = 0.18 * (yy.max() - yy.min())
    ax.set_xlim(xx.min() - pad_x, xx.max() + pad_x)
    ax.set_ylim(yy.min() - pad_y, yy.max() + pad_y)
    ax.set_xlabel("1/T / K$^{-1}$")
    ax.set_ylabel("ln k")
    ax.set_title("ln k – 1/T")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def summary_text(fits: dict, arr: dict | None, dropped: dict, filled: dict) -> str:
    temps = " / ".join(f"{c['T_C']:g}" for c in C.CLIPS.values())
    lines = [f"McCol foam  {temps} C", ""]
    for name in C.CLIPS:
        f = fits[name]
        T = C.CLIPS[name]["T_C"] + 273.15
        lines.append(
            f"{C.CLIPS[name]['label']}: T={T:.2f} K  k={f['k']:.6e} s^-1  "
            f"t0={f['t0']:.0f} s  h0={f['h0']:.2f} mL  n={f['n']}  "
            f"R2={f['r2']:.4f}  RMSE(ln h)={f['rmse']:.4f}  "
            f"오검출={dropped[name]} 보간={filled[name]}"
        )
    if arr is None:
        lines += ["", "클립이 1개 — 아레니우스 적합 생략 (서로 다른 온도 2개 이상 필요)"]
    else:
        lines += [
            "",
            f"Ea = {arr['Ea']:.1f} J/mol = {arr['Ea'] / 1000:.2f} kJ/mol",
            f"A  = {arr['A']:.6e} s^-1",
            f"Arrhenius R2 = {arr['r2']:.4f}",
            f"Arrhenius RMSE (ln k) = {arr['rmse']:.4f}",
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    C.ensure_dirs()
    if not C.CLIPS:
        raise SystemExit("data/raw/clips.json 의 clips 가 비었다 — src/extract.py 안내대로 추가해라")
    if not C.CSV.exists():
        raise SystemExit(f"{C.rel(C.CSV)} 없음 — src/measure.py 를 먼저 돌려라")
    csv_hash = prov.require_csv_unchanged(C.CSV)
    data = load_csv(C.CSV)

    fits, dropped, filled = {}, {}, {}
    for name in C.CLIPS:
        t = data[name]["t"]
        h, dropped[name], filled[name] = prepare(data[name], t)
        fits[name] = F.fit_first_order(t, h)
        f = fits[name]
        print(
            f"{C.CLIPS[name]['label']}: t0={f['t0']:.0f}s  h0={f['h0']:.1f} mL  "
            f"k={f['k']:.4e} s^-1  n={f['n']}  R2={f['r2']:.4f}  "
            f"RMSE={f['rmse']:.4f}  오검출={dropped[name]} 보간={filled[name]}"
        )

    arr = F.arrhenius(fits) if len(C.CLIPS) >= 2 else None
    plot_ln(fits, C.FIG / "fig_ln.png", with_fit=False)
    plot_ln(fits, C.FIG / "fig_ln_fit.png", with_fit=True)
    figs = ["fig_ln.png", "fig_ln_fit.png"]
    if arr is not None:
        plot_arrhenius(arr, C.FIG / "fig_arrhenius.png")
        figs.append("fig_arrhenius.png")

    text = summary_text(fits, arr, dropped, filled)
    with (C.RESULTS / "summary.txt").open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    e = prov.append(
        "analyze",
        params=C.snapshot(C.ANALYZE_KEYS),
        inputs=dict(csv=dict(path=C.rel(C.CSV), value_sha256=csv_hash)),
        outputs=dict(
            fits={
                n: dict(
                    k=fits[n]["k"],
                    t0=fits[n]["t0"],
                    h0=fits[n]["h0"],
                    n=fits[n]["n"],
                    r2=fits[n]["r2"],
                    rmse=fits[n]["rmse"],
                    dropped=dropped[n],
                    filled=filled[n],
                )
                for n in C.CLIPS
            },
            arrhenius=(
                None
                if arr is None
                else dict(Ea=arr["Ea"], A=arr["A"], r2=arr["r2"], rmse=arr["rmse"])
            ),
            fig={n: prov.sha256_file(C.FIG / n) for n in figs},
            summary_sha256=prov.sha256_file(C.RESULTS / "summary.txt"),
        ),
        code=[
            Path(__file__),
            Path(C.__file__),
            Path(F.__file__),
            Path(prov.__file__),
        ],
        notes="band_fill 상대 정제 → 선형 보간 → 중앙값 필터 → 1차 적합 → 아레니우스",
    )
    print("\n" + text)
    print(f"provenance seq={e['seq']} tag={e['tag'][:16]}")


if __name__ == "__main__":
    main()
