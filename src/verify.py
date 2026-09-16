from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfoam import config as C
from mfoam import prov

OK, BAD = "  ok ", "  !! "


def check(label: str, cond: bool, detail: str = "") -> bool:
    print((OK if cond else BAD) + label + (f"  {detail}" if detail and not cond else ""))
    return cond


def check_entry(e: dict, prev_tag: str | None, seq: int, current: bool) -> bool:
    ok = True
    tail = "" if current else "  (이전 기록 — 서명/체인만 검사)"
    print(f"\nseq={e['seq']} {e['stage']} @{e['ts']}{tail}")
    if e["tag"] == prov.UNSIGNED:
        ok &= check("서명", False, "미서명 — 키 없이 돌린 기록. 키를 넣고 run.bat 으로 다시 돌려라")
    elif not prov.signed():
        ok &= check("서명", False, "키 없음 — 서명 검증은 키가 있어야 된다")
    else:
        ok &= check("서명", prov._tag(e) == e["tag"])
    ok &= check("체인", e["seq"] == seq and e.get("prev") == prev_tag,
                f"prev={str(e.get('prev'))[:16]} 기대={str(prev_tag)[:16]}")
    if not current:
        return bool(ok)

    for rel, want in e["code"]["files"].items():
        p = C.ROOT / rel
        got = prov.sha256_file(p) if p.exists() else None
        ok &= check(f"코드 {rel}", got == want,
                    "파일 없음" if got is None else f"{got[:16]} != {want[:16]}")

    out = e["outputs"]
    if "csv" in out:
        p = C.ROOT / out["csv"]["path"]
        got = prov.csv_digest(p) if p.exists() else None
        ok &= check("결과 timeseries.csv 값 해시", got == out["csv"]["value_sha256"],
                    "파일 없음" if got is None else f"{got[:16]} != {out['csv']['value_sha256'][:16]}")
    for name, want in out.get("fig", {}).items():
        p = C.FIG / name
        got = prov.sha256_file(p) if p.exists() else None
        ok &= check(f"결과 fig/{name}", got == want, "파일 없음" if got is None else "내용 다름")
    if "summary_sha256" in out:
        p = C.RESULTS / "summary.txt"
        got = prov.sha256_file(p) if p.exists() else None
        ok &= check("결과 summary.txt", got == out["summary_sha256"],
                    "파일 없음" if got is None else "내용 다름")
    return bool(ok)


def check_reference() -> bool:
    ref = json.loads(C.REFERENCE.read_text(encoding="utf-8"))
    print(f"\n기준 결과와 비교  (원본 host={ref['host']}  태그 {ref['tag'][:16]}  허용 ±{C.REF_TOL:.0%})")
    ok = True

    ex = prov.latest("extract")
    for name, want in ref["videos"].items():
        got = ((ex or {}).get("inputs", {}).get(name) or {}).get("sha256")
        ok &= check(f"영상 {name} sha256", got == want, "extract 기록 없음" if got is None else "다른 영상")

    an = prov.latest("analyze")
    if an is None:
        return check("analyze 기록", False, "없음")
    fits = an["outputs"]["fits"]
    for name, want in ref["k"].items():
        got = fits.get(name, {}).get("k")
        if got is None:
            ok &= check(f"k {name}", False, "기록 없음")
            continue
        d = abs(got - want) / want
        ok &= check(f"k {name}  {got:.4e} vs {want:.4e}  ({d:+.1%})", d <= C.REF_TOL)
    arr = an["outputs"].get("arrhenius")
    if ref.get("Ea") is not None:
        got = (arr or {}).get("Ea")
        if got is None:
            ok &= check("Ea", False, "기록 없음")
        else:
            d = abs(got - ref["Ea"]) / ref["Ea"]
            ok &= check(f"Ea  {got / 1000:.2f} vs {ref['Ea'] / 1000:.2f} kJ/mol  ({d:+.1%})", d <= C.REF_TOL)
    return bool(ok)


def main() -> None:
    log = prov.read_log()
    if not log:
        raise SystemExit("provenance.jsonl 이 비었다. src/extract.py 부터 돌려라.")

    newest = {e["stage"]: e["seq"] for e in log}

    all_ok, prev_tag = True, None
    for i, e in enumerate(log, start=1):
        all_ok &= check_entry(e, prev_tag, i, current=newest[e["stage"]] == e["seq"])
        prev_tag = e["tag"]

    if C.REFERENCE.exists():
        all_ok &= check_reference()

    print(f"\n{len(log)} 항목 — " + ("전부 통과" if all_ok else "불일치 있음"))
    print(f"최신 태그 {log[-1]['tag']}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
