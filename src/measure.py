from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfoam import calib
from mfoam import config as C
from mfoam import cv as mcv
from mfoam import prov

OVERLAY_SEC = {10, 20, 30, 45, 60, 90, 120, 180, 240, 300}
LIQ_REF_MIN_H = 20.0
LIQ_REF_MIN_N = 5


def save_overlay(img, m: dict, cfg: dict, name: str, sec: int) -> None:
    vis = img.copy()
    cv2.rectangle(vis, (cfg["x0"], 0), (cfg["x1"], vis.shape[0]), (0, 255, 0), 2)
    cv2.line(vis, (cfg["x0"], m["fy"]), (cfg["x1"], m["fy"]), (0, 255, 255), 3)
    if m["ly"] is not None:
        cv2.line(vis, (cfg["x0"], m["ly"]), (cfg["x1"], m["ly"]), (0, 0, 255), 3)
    y100 = int(cfg["y100"])
    crop = vis[y100 - 40 : y100 + 850, max(0, cfg["x0"] - 40) : cfg["x1"] + 40]
    mcv.imwrite(C.OVERLAYS / f"ov_{name}_t{sec:03d}.jpg", crop)


def track_clip(name: str, cfg: dict, overlay: bool = True) -> dict:
    d = C.frames_dir(name)
    files = sorted(d.glob("t*.jpg"))
    if not files:
        raise SystemExit(f"프레임 없음: {d} — src/extract.py 를 먼저 돌려라")

    t, foam, liq, band = [], [], [], []
    for fp in files:
        sec = int(fp.stem[1:])
        img = mcv.imread(fp)
        if img is None:
            raise SystemExit(f"읽기 실패: {fp}")
        m = mcv.measure(img, cfg)
        t.append(float(sec))
        foam.append(m["foam_ml"])
        liq.append(m["liq_ml"])
        band.append(m["band_fill"])
        if overlay and sec in OVERLAY_SEC and m["fy"] is not None:
            save_overlay(img, m, cfg, name, sec)

    t = np.array(t, dtype=float)
    foam = np.array(foam, dtype=float)
    liq = np.array(liq, dtype=float)
    band = np.array(band, dtype=float)

    good = np.isfinite(foam) & np.isfinite(liq) & (foam - liq >= LIQ_REF_MIN_H)
    liq_ref = float(np.nanmedian(liq[good] if good.sum() >= LIQ_REF_MIN_N else liq))

    h = foam - liq_ref
    h[~np.isfinite(foam)] = np.nan
    return dict(t=t, foam=foam, liq=liq, band=band, h=h, liq_ref=liq_ref, n=len(files))


def write_csv(data: dict) -> int:
    p = prov.CSV_PRECISION
    rows = 0
    C.CSV.parent.mkdir(parents=True, exist_ok=True)
    with C.CSV.open("w", encoding="utf-8", newline="\n") as f:
        f.write("clip,t_s,foam_mL,liq_mL,h_mL,band_fill\n")
        for name, d in data.items():
            for i in range(len(d["t"])):
                f.write(
                    f"{name},"
                    f"{d['t'][i]:.{p['t_s']}f},"
                    f"{d['foam'][i]:.{p['foam_mL']}f},"
                    f"{d['liq'][i]:.{p['liq_mL']}f},"
                    f"{d['h'][i]:.{p['h_mL']}f},"
                    f"{d['band'][i]:.{p['band_fill']}f}\n"
                )
                rows += 1
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-overlay", action="store_true", help="오버레이 이미지 생략")
    args = ap.parse_args()
    overlay = not args.no_overlay
    C.ensure_dirs()
    if not C.CLIPS:
        raise SystemExit("data/raw/clips.json 의 clips 가 비었다 — src/extract.py 안내대로 추가해라")

    data, inputs, outputs, cals = {}, {}, {}, {}
    for name, cfg in C.CLIPS.items():
        cal = calib.calibrate(C.frames_dir(name))
        cals[name] = cal
        cfg = dict(cfg, **{k: cal[k] for k in ("x0", "x1", "y100", "ppm")})
        if overlay:
            calib.save_overlay(C.frames_dir(name), cal, C.OVERLAYS / f"cal_{name}.jpg")
        print(
            f"{name:>4} 눈금 자동측정  x={cal['x0']}..{cal['x1']}  "
            f"y100={cal['y100']:.1f}  1 mL={cal['ppm']:.3f} px  "
            f"(눈금 {cal['n_ticks']}개, 잔차 {cal['fit_rms']:.1f} px)"
        )
        d = track_clip(name, cfg, overlay)
        data[name] = d
        inputs[name] = dict(
            dir=C.rel(C.frames_dir(name)), **prov.tree_digest(C.frames_dir(name))
        )
        outputs[name] = dict(
            n=d["n"],
            calib=dict(x0=cal["x0"], x1=cal["x1"], y100=cal["y100"], ppm=cal["ppm"],
                       y_foot=cal["y_foot"], n_ticks=cal["n_ticks"], fit_rms=cal["fit_rms"]),
            liq_ref=round(d["liq_ref"], 3),
            n_foam=int(np.isfinite(d["foam"]).sum()),
            n_liq=int(np.isfinite(d["liq"]).sum()),
        )
        print(
            f"{name:>4} {cfg['stem']}  n={d['n']}  liq_ref={d['liq_ref']:.1f} mL  "
            f"거품검출={outputs[name]['n_foam']}"
        )

    rows = write_csv(data)
    outputs["csv"] = dict(
        path=C.rel(C.CSV),
        rows=rows,
        value_sha256=prov.csv_digest(C.CSV),
        file_sha256=prov.sha256_file(C.CSV),
    )
    if overlay:
        outputs["overlays"] = dict(dir=C.rel(C.OVERLAYS), **prov.tree_digest(C.OVERLAYS))

    e = prov.append(
        "measure",
        params=C.snapshot(C.MEASURE_KEYS),
        inputs=inputs,
        outputs=outputs,
        code=[
            Path(__file__),
            Path(calib.__file__),
            Path(C.__file__),
            Path(mcv.__file__),
            Path(prov.__file__),
        ],
        notes="CV 측정만. ROI·눈금은 프레임에서 자동 측정. 프레임 게이트/평활/적합은 analyze 단계.",
    )
    print(f"\n{C.rel(C.CSV)}  {rows} 행")
    print(f"값 해시 {outputs['csv']['value_sha256'][:16]}")
    print(f"provenance seq={e['seq']} tag={e['tag'][:16]}")

    extra = C.unregistered_videos()
    if extra:
        print('\n설정 없는 영상은 측정에서 빠졌다 — data/raw/clips.json 의 "clips" 에 아래 줄을 추가해라:')
        for v in extra:
            print("  " + C.clip_template(v))


if __name__ == "__main__":
    main()
