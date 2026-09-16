from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import config as C

CSV_PRECISION = {
    "t_s": 1,
    "foam_mL": 3,
    "liq_mL": 3,
    "h_mL": 3,
    "band_fill": 4,
}


_EMBEDDED_KEY: str | None = None

UNSIGNED = "unsigned"


def _key() -> bytes | None:
    k = os.environ.get("MFOAM_PROV_KEY") or C._FILE_ENV.get("MFOAM_PROV_KEY", "") or _EMBEDDED_KEY
    return k.encode() if k else None


def signed() -> bool:
    return _key() is not None


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm_field(col: str, val: str) -> str:
    if col not in CSV_PRECISION:
        return val.strip()
    s = val.strip()
    try:
        x = float(s)
    except ValueError:
        return s
    if x != x:
        return "nan"
    return f"{x:.{CSV_PRECISION[col]}f}"


def canon_csv(path: Path) -> bytes:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    cols = [c.strip() for c in lines[0].split(",")]
    out = [",".join(cols)]
    for line in lines[1:]:
        if not line.strip():
            continue
        fields = line.split(",")
        out.append(",".join(_norm_field(c, v) for c, v in zip(cols, fields)))
    return ("\n".join(out) + "\n").encode("utf-8")


def csv_digest(path: Path) -> str:
    return sha256_bytes(canon_csv(path))


def tree_digest(root: Path, pattern: str = "*.jpg") -> dict:
    files = sorted(root.rglob(pattern))
    lines = [f"{p.relative_to(root).as_posix()} {sha256_file(p)}" for p in files]
    return dict(
        n=len(files),
        digest=sha256_bytes("\n".join(lines).encode()),
        bytes=sum(p.stat().st_size for p in files),
    )


def code_digest(paths: list[Path]) -> dict:
    items = {}
    for p in sorted(paths):
        if p.exists():
            items[p.relative_to(C.ROOT).as_posix()] = sha256_file(p)
    return dict(
        files=items,
        digest=sha256_bytes(
            "\n".join(f"{k} {v}" for k, v in sorted(items.items())).encode()
        ),
    )


def _ffmpeg_version() -> str:
    try:
        out = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, check=True
        ).stdout
        return out.splitlines()[0].strip()
    except Exception:
        return "unavailable"


def tool_versions(include_ffmpeg: bool = False) -> dict:
    v = dict(python=platform.python_version(), platform=platform.platform())
    try:
        import numpy

        v["numpy"] = numpy.__version__
    except Exception:
        pass
    try:
        import cv2

        v["opencv"] = cv2.__version__
    except Exception:
        pass
    if include_ffmpeg:
        v["ffmpeg"] = _ffmpeg_version()
    return v


def _canon_json(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _tag(entry: dict) -> str:
    key = _key()
    if key is None:
        return UNSIGNED
    body = {k: v for k, v in entry.items() if k != "tag"}
    return hmac.new(key, _canon_json(body), hashlib.sha256).hexdigest()


def read_log(path: Path | None = None) -> list[dict]:
    path = path or C.PROV
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def append(
    stage: str,
    *,
    params: dict,
    inputs: dict,
    outputs: dict,
    code: list[Path],
    notes: str = "",
    include_ffmpeg: bool = False,
) -> dict:
    log = read_log()
    entry = {
        "seq": len(log) + 1,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": stage,
        "host": socket.gethostname(),
        "code": code_digest(code),
        "tools": tool_versions(include_ffmpeg),
        "params": params,
        "inputs": inputs,
        "outputs": outputs,
        "notes": notes,
        "prev": log[-1]["tag"] if log else None,
    }
    entry["tag"] = _tag(entry)
    C.PROV.parent.mkdir(parents=True, exist_ok=True)
    with C.PROV.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return entry


def latest(stage: str) -> dict | None:
    for e in reversed(read_log()):
        if e["stage"] == stage:
            return e
    return None


def require_csv_unchanged(path: Path) -> str:
    e = latest("measure")
    if e is None:
        raise SystemExit("measure 로그 없음. src/measure.py 를 먼저 돌려라.")
    want = e["outputs"]["csv"]["value_sha256"]
    got = csv_digest(path)
    if want != got:
        raise SystemExit(
            f"CSV 값 해시 불일치 — 손댄 흔적.\n  기록: {want}\n  현재: {got}\n"
            f"  (의도한 재측정이면 src/measure.py 를 다시 돌려 새 항목을 남겨라)"
        )
    return got
