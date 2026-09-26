"""스트림 배정 점검기. 폴더 안 모든 코드가 스트림(담당 갈래) 하나에 배정됐는지 센다.

규칙: 코드 파일 하나 = 스트림 하나. 미배정 0, 중복 0이어야 정상이다.
어느 스트림에도 안 속한 코드는 누구의 리뷰도 받지 않는다. 이 점검기가 그 빈틈을 센다.

배정표(streams.json) 예시는 templates/streams.json.
  extensions : 셀 파일 확장자
  exclude    : 셀 대상에서 뺄 경로 앞부분
  streams    : { 키: {label, map, roots[], globs[]} }
판정: globs 일치가 roots 일치보다 우선하고, roots 끼리는 더 긴 경로가 이긴다. 대소문자 구분.
      같은 우선순위로 두 스트림이 잡으면 '중복'이다.
      map 에 적은 맵 문서가 없으면 그것도 문제로 센다.

사용: python tools/stream_check.py <streams.json> [--root 폴더]
종료코드: 0 정상 / 1 미배정·중복·맵 없음 중 하나라도 있음
"""
import argparse
from fnmatch import fnmatchcase
import json
import sys
from pathlib import Path


def claim(rel, streams):
    """rel 경로를 잡는 스트림 목록. (우선순위, 키) 중 최고 순위만 남긴다."""
    best, owners = -1, []
    for key, s in streams.items():
        score = -1
        if any(fnmatchcase(rel, g) for g in s.get("globs", [])):
            score = 10_000
        else:
            for r in s.get("roots", []):
                r = r.rstrip("/") + "/"
                if rel.startswith(r):
                    score = max(score, len(r))
        if score > best:
            best, owners = score, [key]
        elif score == best and score >= 0:
            owners.append(key)
    return owners if best >= 0 else []


SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__"}


def validate(reg):
    """배정표 형식 오류 목록. 틀린 배정표로 '문제 없음'이 나오는 걸 막는다."""
    errs = []
    exts = reg.get("extensions", [".py"])
    if not (isinstance(exts, list) and exts and all(isinstance(e, str) and e.startswith(".") for e in exts)):
        errs.append('extensions 는 [".py"] 처럼 점으로 시작하는 목록이어야 합니다')
    if not isinstance(reg.get("exclude", []), list):
        errs.append("exclude 는 목록이어야 합니다")
    streams = reg.get("streams")
    if not isinstance(streams, dict) or not streams:
        return errs + ["streams 가 비어 있습니다"]
    for k, st in streams.items():
        if not isinstance(st, dict):
            errs.append(f"{k}: 스트림 정보는 객체여야 합니다")
            continue
        if not st.get("map"):
            errs.append(f"{k}: map(맵 문서 경로)이 없습니다")
        for f in ("roots", "globs"):
            v = st.get(f, [])
            if not (isinstance(v, list) and all(isinstance(x, str) and x for x in v)):
                errs.append(f"{k}: {f} 는 문자열 목록이어야 합니다")
        if not st.get("roots") and not st.get("globs"):
            errs.append(f"{k}: roots·globs 가 둘 다 비어 코드를 하나도 못 가집니다")
    return errs


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="스트림 배정 점검기")
    ap.add_argument("registry", help="streams.json 경로")
    ap.add_argument("--root", default=".", help="셀 폴더 (기본: 현재 폴더)")
    a = ap.parse_args()

    try:
        reg = json.loads(Path(a.registry).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        print(f"배정표를 못 읽었습니다: {e}")
        return 1
    errs = validate(reg) if isinstance(reg, dict) else ["배정표 맨 바깥은 객체여야 합니다"]
    if errs:
        print("배정표 형식이 틀렸습니다:")
        for e in errs:
            print(f"  {e}")
        return 1
    root = Path(a.root).resolve()
    exts = tuple(reg.get("extensions", [".py"]))
    exclude = [e.rstrip("/") + "/" for e in reg.get("exclude", [])]
    streams = reg["streams"]

    counts = {k: 0 for k in streams}
    unassigned, doubled = [], []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.suffix not in exts:
            continue
        rel = f.relative_to(root).as_posix()
        if SKIP_DIRS & set(rel.split("/")[:-1]) or any(rel.startswith(e) for e in exclude):
            continue
        owners = claim(rel, streams)
        if not owners:
            unassigned.append(rel)
        elif len(owners) > 1:
            doubled.append((rel, owners))
        else:
            counts[owners[0]] += 1

    missing_maps = [k for k, s in streams.items() if not (root / s["map"]).is_file()]

    total = sum(counts.values()) + len(unassigned) + len(doubled)
    if total == 0:
        print(f"셀 코드가 0개입니다. --root({root})와 extensions 를 확인하세요.")
        return 1
    print(f"코드 {total}개 · 스트림 {len(streams)}개")
    for k in sorted(counts, key=lambda k: -counts[k]):
        print(f"  {counts[k]:>5}  {k:<12} {streams[k].get('label', '')}")

    ok = True
    if unassigned:
        ok = False
        print(f"\n미배정 {len(unassigned)}개. 어느 스트림에 넣을지 정해 주세요:")
        for r in unassigned[:30]:
            print(f"  {r}")
        if len(unassigned) > 30:
            print(f"  외 {len(unassigned) - 30}개")
    if doubled:
        ok = False
        print(f"\n중복 {len(doubled)}개. 한 스트림만 남기세요:")
        for r, o in doubled[:30]:
            print(f"  {r}  ({', '.join(o)})")
    if missing_maps:
        ok = False
        print(f"\n맵 문서가 없는 스트림 {len(missing_maps)}개: {', '.join(missing_maps)}")
    if ok:
        print("\n미배정 0 · 중복 0. 모든 코드에 담당 스트림이 있습니다.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
