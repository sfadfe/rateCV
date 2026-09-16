from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfoam import calib
from mfoam import config as C
from mfoam import cv as mcv
from mfoam import prov
from mfoam import split


def install_hint(tool: str) -> str:
    if sys.platform == "win32":
        how = "winget install Gyan.FFmpeg  (또는 choco install ffmpeg) 후 새 터미널에서 실행"
    elif sys.platform == "darwin":
        how = "brew install ffmpeg"
    else:
        how = "sudo apt install ffmpeg"
    return f"{tool} 없음 (PATH 에 없다). {how}"


def probe(mp4: Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,nb_frames,duration",
            "-of", "json", str(mp4),
        ],
        capture_output=True, text=True, check=True,
        encoding="utf-8", errors="replace",
    ).stdout
    s = json.loads(out)["streams"][0]
    return dict(
        width=int(s["width"]),
        height=int(s["height"]),
        r_frame_rate=s["r_frame_rate"],
        nb_frames=int(s.get("nb_frames", 0)),
        duration=float(s.get("duration", 0.0)),
    )


def reuse(dst: Path, prev_digest: str | None) -> dict | None:
    if not (dst.exists() and any(dst.glob("t*.jpg"))):
        return None
    t = prov.tree_digest(dst)
    if prev_digest is not None and t["digest"] == prev_digest:
        print(f"skip {dst.name} (이미 있음, 기록과 일치. --force 로 재추출)")
        return t
    print(f"{dst.name}: 프레임이 있지만 서명된 추출 기록과 다르다 — 다시 뽑는다")
    return None


def extract_one(mp4: Path, dst: Path, force: bool, prev_digest: str | None,
                start: float | None = None, end: float | None = None) -> dict:
    if not force:
        t = reuse(dst, prev_digest)
        if t is not None:
            return t
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:g}"]
    cmd += ["-i", str(mp4)]
    if end is not None:
        cmd += ["-t", f"{end - (start or 0.0):g}"]
    cmd += [
        "-vf", f"fps={C.FPS:g}", "-q:v", str(C.JPEG_Q),
        "-start_number", "0", str(dst / "t%04d.jpg"), "-y",
    ]
    subprocess.run(cmd, check=True)
    t = prov.tree_digest(dst)
    span = "" if start is None and end is None else f"  구간 {start or 0:g}-{'' if end is None else f'{end:g}'} s"
    print(f"{dst.name}: {t['n']} 프레임  digest={t['digest'][:16]}{span}")
    return t


def extract_auto(mp4: Path, stem: str, names: list[str], force: bool, prev: dict | None) -> dict:
    dsts = {n: C.frames_dir(n) for n in names}
    if not force:
        got = {n: reuse(d, ((prev or {}).get("outputs", {}).get(n) or {}).get("digest")) for n, d in dsts.items()}
        if all(t is not None for t in got.values()):
            return {n: dict(dir=C.rel(dsts[n]), split="auto",
                            start=prev["outputs"][n].get("start"), end=prev["outputs"][n].get("end"), **got[n])
                    for n in names}
    full = C.FRAMES / f"{stem}__all"
    extract_one(mp4, full, True, None)
    files = sorted(full.glob("t*.jpg"))
    segs = split.segments(files, len(names))
    out = {}
    for n, (a, b) in zip(names, segs):
        d = dsts[n]
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        for j, k in enumerate(range(a, b + 1)):
            shutil.copyfile(files[k], d / f"t{j:04d}.jpg")
        t = prov.tree_digest(d)
        print(f"{d.name}: {t['n']} 프레임  digest={t['digest'][:16]}  자동 구간 {a // 60}:{a % 60:02d}-{b // 60}:{b % 60:02d}")
        out[n] = dict(dir=C.rel(d), split="auto", start=a, end=b, **t)
    shutil.rmtree(full, ignore_errors=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="RAW 폴더의 영상을 찾아 프레임으로 뽑는다")
    ap.add_argument("--force", action="store_true", help="기존 프레임 지우고 재추출")
    args = ap.parse_args()

    C.ensure_dirs()
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(install_hint(tool))

    videos = C.find_videos()
    if not videos:
        raise SystemExit(
            f"영상 없음: {C.RAW}\n"
            f"  이 폴더에 영상을 넣고 다시 실행해라 (확장자 {' '.join(C.VIDEO_EXTS)})"
        )

    missing = [(n, c["stem"]) for n, c in C.CLIPS.items() if C.video_of(c["stem"]) is None]
    if missing:
        raise SystemExit(
            f"data/raw/clips.json 에 적힌 원본이 {C.RAW} 에 없다:\n"
            + "\n".join(f"  {n}: {stem}" for n, stem in missing)
        )

    prev = prov.latest("extract")
    if prev is not None and (prev["tag"] == prov.UNSIGNED or
                             (prov.signed() and prov._tag(prev) != prev["tag"])):
        prev = None

    inputs, outputs = {}, {}

    def video_info(mp4: Path) -> dict:
        return dict(mp4=mp4.name, sha256=prov.sha256_file(mp4), bytes=mp4.stat().st_size, **probe(mp4))

    for stem, names in C.stem_groups().items():
        mp4 = C.video_of(stem)
        info = video_info(mp4)
        spans = {n: (C.CLIPS[n]["start"], C.CLIPS[n]["end"]) for n in names}
        if len(names) > 1 and all(s == (None, None) for s in spans.values()):
            print(f"{mp4.name}: 클립 {len(names)}개가 한 영상 — 붓는 순간을 찾아 자동으로 나눈다 (순서 {' → '.join(names)})")
            for n in names:
                inputs[n] = dict(info)
            outputs.update(extract_auto(mp4, stem, names, args.force, prev))
            continue
        for n in names:
            start, end = spans[n]
            dst = C.frames_dir(n)
            prev_digest = ((prev or {}).get("outputs", {}).get(n) or {}).get("digest")
            inputs[n] = dict(info, **({} if start is None else dict(start=start)), **({} if end is None else dict(end=end)))
            outputs[n] = dict(dir=C.rel(dst), **extract_one(mp4, dst, args.force, prev_digest, start, end))

    for mp4 in C.unregistered_videos():
        dst = C.FRAMES / mp4.stem
        prev_digest = ((prev or {}).get("outputs", {}).get(mp4.stem) or {}).get("digest")
        inputs[mp4.stem] = video_info(mp4)
        outputs[mp4.stem] = dict(dir=C.rel(dst), **extract_one(mp4, dst, args.force, prev_digest))

    e = prov.append(
        "extract",
        params=C.snapshot(C.EXTRACT_KEYS),
        inputs=inputs,
        outputs=outputs,
        code=[Path(__file__), Path(C.__file__), Path(prov.__file__),
              Path(split.__file__), Path(calib.__file__), Path(mcv.__file__)],
        notes="ffmpeg fps=1 q:v=2 start_number=0; 회전은 ffmpeg 자동 적용; "
              "한 영상 여러 클립이면 전체를 뽑은 뒤 붓는 순간으로 나눠 복사 (outputs.start/end 는 초)",
        include_ffmpeg=True,
    )
    print(f"\nprovenance seq={e['seq']} tag={e['tag'][:16]}")

    extra = C.unregistered_videos()
    if extra:
        print("\n프레임은 뽑았지만 data/raw/clips.json 에 없는 영상이다 — 측정 단계에서 빠진다.")
        print('아래 줄을 data/raw/clips.json 의 "clips" 안에 넣고 온도를 채워라 (ROI·눈금은 measure 가 자동으로 잰다):')
        for v in extra:
            print("  " + C.clip_template(v))


if __name__ == "__main__":
    main()
