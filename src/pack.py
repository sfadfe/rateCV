from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfoam import config as C
from mfoam import prov

FORMAT = "mfoam-submit-1"
STORED_EXT = {".jpg", ".jpeg", ".png", ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".zip"}


def preflight() -> tuple[dict, dict, dict]:
    if not prov.signed():
        raise SystemExit("서명키 없음 — .env 에 MFOAM_PROV_KEY 를 적고 run.bat 으로 돌려라")
    ex, me, an = prov.latest("extract"), prov.latest("measure"), prov.latest("analyze")
    for stage, e in (("extract", ex), ("measure", me), ("analyze", an)):
        if e is None:
            raise SystemExit(f"{stage} 기록 없음 — run.bat 을 처음부터 돌려라")
        if e["tag"] == prov.UNSIGNED:
            raise SystemExit(f"{stage} 기록이 미서명 — run.bat 으로 다시 돌려라")
        if prov._tag(e) != e["tag"]:
            raise SystemExit(f"{stage} 기록의 서명이 틀리다 — results/provenance.jsonl 을 손댔다")
    if not ex["seq"] < me["seq"] < an["seq"]:
        raise SystemExit("기록 순서가 extract → measure → analyze 가 아니다 — run.bat 을 다시 돌려라")

    bad = []
    clips_now = C.snapshot(["CLIPS"])["CLIPS"]
    for stage, e in (("extract", ex), ("measure", me), ("analyze", an)):
        if e["params"].get("CLIPS") != clips_now:
            bad.append(f"{stage} 이후 data/raw/clips.json 이 바뀌었다")
    for name, cfg in C.CLIPS.items():
        d = C.frames_dir(name)
        got = prov.tree_digest(d)["digest"] if d.is_dir() else None
        want_ex = (ex["outputs"].get(name) or {}).get("digest")
        want_me = (me["inputs"].get(name) or {}).get("digest")
        if not (got is not None and got == want_ex == want_me):
            bad.append(f"프레임 {name} ({C.rel(d)}) 이 extract/measure 기록과 다르다")
    csv_want = me["outputs"]["csv"]["value_sha256"]
    if not C.CSV.exists() or prov.csv_digest(C.CSV) != csv_want:
        bad.append("results/timeseries.csv 가 measure 기록과 다르다")
    if an["inputs"]["csv"]["value_sha256"] != csv_want:
        bad.append("analyze 가 읽은 CSV 가 measure 결과와 다르다")
    for n, want in an["outputs"].get("fig", {}).items():
        p = C.FIG / n
        if not p.exists() or prov.sha256_file(p) != want:
            bad.append(f"results/fig/{n} 이 analyze 기록과 다르다")
    p = C.RESULTS / "summary.txt"
    if not p.exists() or prov.sha256_file(p) != an["outputs"]["summary_sha256"]:
        bad.append("results/summary.txt 가 analyze 기록과 다르다")
    if bad:
        raise SystemExit("기록과 다른 파일이 있다 — 손댔거나 단계를 건너뛰었다. run.bat 을 다시 돌려라:\n"
                         + "\n".join(f"  {b}" for b in bad))
    return ex, me, an


def collect(ex: dict, no_video: bool) -> tuple[list[Path], dict[str, bytes]]:
    files: list[Path] = [C.PROV, C.CSV, C.RESULTS / "summary.txt"]
    files += sorted(C.FIG.glob("*.png"))
    if C.OVERLAYS.is_dir():
        files += sorted(C.OVERLAYS.glob("*.jpg"))
    for name in C.CLIPS:
        files += sorted(C.frames_dir(name).rglob("*.jpg"))

    extra: dict[str, bytes] = {}
    if C.CLIPS_FILE.exists():
        files.append(C.CLIPS_FILE)
    else:
        doc = dict(team=C.TEAM, clips={
            n: dict(stem=c["stem"], T_C=c["T_C"], **{k: c[k] for k in ("start", "end") if c[k] is not None})
            for n, c in C.CLIPS.items()})
        extra[C.rel(C.CLIPS_FILE)] = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    if not no_video:
        bad = []
        for name, cfg in C.CLIPS.items():
            v = C.video_of(cfg["stem"])
            want = (ex["inputs"].get(name) or {}).get("sha256")
            if v is None:
                bad.append(f"영상 {name} ({cfg['stem']}) 이 data/raw 에 없다 (--no-video 면 뺄 수 있다)")
            elif prov.sha256_file(v) != want:
                bad.append(f"영상 {name} ({v.name}) 이 extract 기록과 다른 파일이다")
            else:
                files.append(v)
        if bad:
            raise SystemExit("\n".join(bad))
    files = list(dict.fromkeys(files))
    return files, extra


def safe_name(s: str) -> str:
    return re.sub(r"[^\w\-]+", "_", s, flags=re.UNICODE).strip("_") or "noteam"


def main() -> None:
    ap = argparse.ArgumentParser(description="제출용 서명 zip 을 만든다")
    ap.add_argument("--no-video", action="store_true", help="원본 영상은 넣지 않는다")
    args = ap.parse_args()

    ex, me, an = preflight()
    files, extra = collect(ex, args.no_video)

    hashes = {C.rel(p): prov.sha256_file(p) for p in files if p != C.PROV}
    hashes.update({rel: prov.sha256_bytes(b) for rel, b in extra.items()})
    total = sum(p.stat().st_size for p in files) + sum(len(b) for b in extra.values())

    e = prov.append(
        "pack",
        params=dict(no_video=args.no_video, **C.snapshot(["CLIPS"])),
        inputs=dict(analyze_tag=an["tag"], measure_tag=me["tag"], extract_tag=ex["tag"]),
        outputs=dict(
            files=len(hashes) + 1,
            bytes=total,
            files_digest=prov.sha256_bytes("\n".join(f"{k} {v}" for k, v in sorted(hashes.items())).encode()),
        ),
        code=[Path(__file__), Path(C.__file__), Path(prov.__file__)],
        notes="제출 zip. manifest.json 의 tag 가 파일 목록·해시를 서명한다",
    )
    hashes[C.rel(C.PROV)] = prov.sha256_file(C.PROV)

    arr = an["outputs"].get("arrhenius")
    manifest = dict(
        format=FORMAT,
        ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        host=socket.gethostname(),
        team=C.TEAM,
        clips_source=C.CLIPS_SOURCE,
        tools=prov.tool_versions(),
        prov_entries=e["seq"],
        prov_last_tag=e["tag"],
        analyze_tag=an["tag"],
        no_video=args.no_video,
        videos={n: dict(mp4=v["mp4"], sha256=v["sha256"]) for n, v in ex["inputs"].items()},
        results=dict(
            k={n: f["k"] for n, f in an["outputs"]["fits"].items()},
            Ea=None if arr is None else arr["Ea"],
            csv_value_sha256=an["inputs"]["csv"]["value_sha256"],
        ),
        files=dict(sorted(hashes.items())),
    )
    manifest["tag"] = prov._tag(manifest)

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    zip_path = C.ROOT / f"submit_{safe_name(C.TEAM)}_{stamp}_{manifest['tag'][:8]}.zip"
    with zipfile.ZipFile(zip_path, "w", allowZip64=True) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    compress_type=zipfile.ZIP_DEFLATED)
        for rel, b in extra.items():
            zf.writestr(rel, b, compress_type=zipfile.ZIP_DEFLATED)
        for p in files:
            ct = zipfile.ZIP_STORED if p.suffix.lower() in STORED_EXT else zipfile.ZIP_DEFLATED
            zf.write(p, C.rel(p), compress_type=ct)

    print(f"\n{zip_path.name}  {zip_path.stat().st_size / 2**20:.0f} MB  파일 {len(hashes) + 1}개"
          + ("  (영상 제외)" if args.no_video else ""))
    print(f"manifest tag={manifest['tag'][:16]}  provenance seq={e['seq']} tag={e['tag'][:16]}")
    print("이 zip 을 그대로 제출해라. 풀어서 다시 묶거나 안의 파일을 바꾸면 서명이 안 맞는다.")


if __name__ == "__main__":
    main()
