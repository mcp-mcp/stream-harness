"""공개 저장소 유출 차단기. 커밋·푸시 직전에 비밀값과 개인정보가 섞였는지 검사한다.

막는 것
  1) 흔한 비밀 형식: API 키, 토큰, 개인키, 비밀번호 대입문
  2) 이메일, 휴대폰 번호, 주민번호, PC 사용자 폴더 경로
  3) --deny 로 준 금지어 목록 (저장소 밖 JSON, 형식은 아래)
  4) --vault 로 준 금고 폴더 안 JSON 값. 12자 이상 문자열 전부 + 이름이 비밀스러운 키
     (password·token·account·계좌 등)의 값은 6자 이상이면 전부. 여러 줄 값은 줄마다도
  5) 커밋 작성자·커미터 이름과 이메일 (번호+아이디@users.noreply.github.com 만 통과)
  6) 이진 파일 (사진 속 위치정보처럼 글자 검사로 못 보는 것). allow_binary 에 있어야 통과

금지어 JSON: {"terms": [...], "allow": [...], "allow_binary": [...], "vault_ignore": [...]}
  terms        대소문자 무시. 영문·숫자 금지어는 단어 경계로 비교(긴 단어 속 일부는 안 걸림).
               한글이 섞인 금지어는 띄어쓰기·전각·보이지 않는 문자를 지운 판으로 비교
  allow        걸려도 되는 문구. 검사 전에 지운다
  vault_ignore 금고에 있지만 비밀이 아닌 값(예: 요청 머리글 같은 흔한 문구). 정확히 같은 값만 뺀다

모드
  python tools/leak_check.py                 # 작업 폴더 전체(추적 + 새 파일). 손으로 돌릴 때
  python tools/leak_check.py --staged        # pre-commit 훅: 커밋 대기 내용 + 작성자·커미터
  python tools/leak_check.py --msg FILE      # commit-msg 훅: 커밋 메시지
  python tools/leak_check.py --push          # pre-push 훅: 올라갈 커밋 전부의 변경분·메시지·작성자·브랜치 이름

종료코드: 0 통과 / 1 걸림 / 2 검사 불가(금지어·금고·git 을 못 읽음 = 안전하게 차단)
걸린 값 자체는 화면에 찍지 않는다. 위치와 종류만 알려준다.
막는 대상은 '실수로 섞인 것'이다. 일부러 인코딩해 숨기는 것까지 막지는 못한다.
"""
import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_VAULT_LEN = 12
MIN_SECRET_KEY_LEN = 6
SECRET_KEY = re.compile(r"(?i)(?:^|[_\-\s.])(?:pass(?:word|wd)?|pwd|pin|secret|token|key|apikey|account|acct|acc_?no)s?(?:$|[_\-\s.])|계좌|비번|암호")
ZERO = "0" * 40
NOREPLY = r"\d+\+[A-Za-z0-9-]+@users\.noreply\.github\.com"
A = r"(?<![A-Za-z0-9_-])"  # 앞이 영문·숫자가 아님. 한글 옆에 붙어도 잡히게 \b 대신 쓴다
ZERO_WIDTH = re.compile("[%s-%s%s%s]" % (chr(0x200B), chr(0x200F), chr(0x2060), chr(0xFEFF)))  # 보이지 않는 문자

PATTERNS = [
    ("Anthropic 키", A + r"sk-ant-[A-Za-z0-9_-]{20,}"),
    ("OpenAI 키", A + r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    ("GitHub 토큰", A + r"(?:(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    ("AWS 키", A + r"AKIA[0-9A-Z]{16}(?![0-9A-Z])"),
    ("Google 키", A + r"AIza[0-9A-Za-z_-]{35}"),
    ("Slack 토큰", A + r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ("텔레그램 봇 토큰", r"(?<!\d)\d{8,10}:[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])"),
    ("개인키", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("JWT", A + r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ("비밀번호 대입", r"(?i)(?<![A-Za-z])(?:password|passwd|pwd|secret|api_?key|token)(?![A-Za-z])\s*[:=]\s*['\"][^'\"\s]{6,}['\"]"),
    ("이메일", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("휴대폰 번호", r"(?<!\d)01[016789][-. ]?\d{3,4}[-. ]?\d{4}(?!\d)"),
    ("주민번호", r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)"),
    ("PC 사용자 폴더", r"(?i)(?<![A-Za-z])[A-Z]:[\\/]+Users[\\/]+[^\\/\s]+"),
]
ALLOW_DEFAULT = ["@example.com", "@users.noreply.github.com", "noreply@"]


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"git {args[0]} 실패: " + r.stderr.decode("utf-8", "replace").strip())
    return r.stdout


def norm(s):
    """전각→반각, 보이지 않는 문자 제거."""
    return ZERO_WIDTH.sub("", unicodedata.normalize("NFKC", s))


def compile_terms(terms):
    """금지어 → ('re', 정규식) 또는 ('sq', 띄어쓰기 지운 소문자).
    영문·숫자 금지어: 단어 경계 + 단어 사이 띄어쓰기 무시 (긴 단어 속 일부는 안 걸림).
    한글이 섞인 금지어: 띄어쓰기를 전부 지우고 비교 (띄어 써서 피해 가지 못하게)."""
    out = []
    for t in (x.strip() for x in terms):
        if re.fullmatch(r"[\x20-\x7e]+", t):
            body = r"\s*".join(re.escape(w) for w in t.split())
            out.append(("re", re.compile(r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])", re.I)))
        else:
            out.append(("sq", re.sub(r"\s+", "", norm(t)).lower()))
    return out


def load_deny(path):
    d = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    terms = [t for t in d.get("terms", []) if isinstance(t, str) and t.strip()]
    if not terms:
        raise ValueError("금지어가 비어 있음")
    return (terms, list(d.get("allow", [])), set(d.get("allow_binary", [])),
            set(d.get("vault_ignore", [])))


def load_vault(folder, skip=None, ignore=()):
    """금고 폴더 JSON 의 값 {값: '파일 > 키'}. 하나라도 못 읽으면 예외(=차단).
    skip = 금지어 목록 파일(금고 안에 있어도 비밀값이 아니므로 뺀다)"""
    found, broken = {}, []

    def add(v, label, key):
        v = str(v).strip()
        need = MIN_SECRET_KEY_LEN if SECRET_KEY.search(key) else MIN_VAULT_LEN
        if len(v) >= need and v not in ignore:
            found.setdefault(v, label)

    def walk(node, label, key=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{label} > {k}", str(k))
        elif isinstance(node, list):
            for v in node:
                walk(v, label, key)
        elif isinstance(node, str):
            add(node, label, key)
            if "\n" in node:  # 여러 줄 값(개인키 등)은 한 줄만 새도 잡히게
                for part in node.splitlines():
                    add(part, label, key)
        elif isinstance(node, int) and not isinstance(node, bool) and SECRET_KEY.search(key):
            add(node, label, key)  # 숫자로 저장된 계좌·아이디

    for f in Path(folder).rglob("*"):
        if f.is_file() and ".json" in f.name and f.resolve() != skip:
            try:
                walk(json.loads(f.read_text(encoding="utf-8-sig")), f.name)
            except (ValueError, UnicodeDecodeError, OSError):
                broken.append(f.name)
    if broken:
        raise ValueError(f"금고 JSON {len(broken)}개를 못 읽음: {', '.join(broken[:5])}")
    if not found:
        raise ValueError("금고에서 값을 하나도 못 읽음")
    return found


def decode(data):
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp949", "replace")


def staged_items():
    names = git("diff", "--cached", "--name-only", "--diff-filter=ACMRT", "-z").split(b"\0")
    return [(n.decode(), git("show", f":{n.decode()}")) for n in names if n]


def worktree_items():
    names = git("ls-files", "-co", "--exclude-standard", "-z").split(b"\0")
    return [(n.decode(), (ROOT / n.decode()).read_bytes()) for n in names if n]


def split_ident(s):
    m = re.match(r"(.*) <([^>]*)>", s.strip())
    return (m.group(1), m.group(2)) if m else (s.strip(), "")


def push_items(stdin_text):
    """pre-push 가 넘겨준 범위의 커밋 전부: 변경 파일, 메시지, 작성자·커미터, 브랜치 이름."""
    items, idents = [], []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO:
            continue  # 원격 브랜치 삭제
        _, local_sha, remote_ref, remote_sha = parts
        items.append((f"(브랜치 이름 {remote_ref})", remote_ref.encode()))
        if remote_sha == ZERO:
            shas = git("rev-list", local_sha, "--not", "--remotes").split()
        else:
            shas = git("rev-list", f"{remote_sha}..{local_sha}").split()
        for sha in (s.decode() for s in shas):
            meta = git("show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", sha).decode("utf-8", "replace")
            an, ae, cn, ce, body = (meta.split("\0") + [""] * 5)[:5]
            idents += [(f"(커밋 {sha[:7]} 작성자)", an, ae), (f"(커밋 {sha[:7]} 커미터)", cn, ce)]
            items.append((f"(커밋 {sha[:7]} 메시지)", body.encode()))
            names = git("diff-tree", "-r", "--root", "--no-commit-id", "--name-only", "-z",
                        "--diff-filter=ACMRT", sha).split(b"\0")
            for n in (x.decode() for x in names if x):
                items.append((f"{n} (커밋 {sha[:7]})", git("show", f"{sha}:{n}")))
    return items, idents


def has_term(text, terms):
    n = norm(text)
    sq = re.sub(r"\s+", "", n).lower()
    return any(v.search(n) if k == "re" else v in sq for k, v in terms)


def scan_text(path, text, terms, allow, vault, hits):
    for no, line in enumerate(text.splitlines(), 1):
        clean = line
        for a in allow:
            clean = re.sub(re.escape(a), " ", clean, flags=re.I)
        for name, pat in PATTERNS:
            if re.search(pat, clean):
                hits.append((path, no, name))
        if has_term(clean, terms):
            hits.append((path, no, "금지어"))
    for value, label in vault.items():  # 전문 대조: 여러 줄 값·이스케이프된 값까지
        for form in (value, json.dumps(value, ensure_ascii=False)[1:-1]):
            if form.isdigit():
                m = re.search(r"(?<!\d)" + form + r"(?!\d)", text)
                i = m.start() if m else -1
            else:
                i = text.find(form)
            if i >= 0:
                hits.append((path, text.count("\n", 0, i) + 1, f"금고 값 ({label})"))
                break


def check_ident(label, name, email, terms, hits):
    if not re.fullmatch(NOREPLY, email):
        hits.append((label, 0, "이메일이 깃허브 공개용 주소(번호+아이디@users.noreply.github.com)가 아님"))
    if has_term(f"{name} {email}", terms):
        hits.append((label, 0, "이름·이메일에 금지어"))


def main():
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="공개 저장소 유출 차단기")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--staged", action="store_true", help="pre-commit: 커밋 대기 내용 + 작성자·커미터")
    mode.add_argument("--msg", help="commit-msg: 커밋 메시지 파일")
    mode.add_argument("--push", action="store_true", help="pre-push: 표준입력으로 받은 범위의 커밋 전부")
    ap.add_argument("--deny", help="금지어 목록 JSON (저장소 밖에 둘 것)")
    ap.add_argument("--vault", help="비밀값이 든 JSON 폴더 (저장소 밖)")
    a = ap.parse_args()

    terms, allow, allow_bin, ignore, vault, idents = [], list(ALLOW_DEFAULT), set(), set(), {}, []
    try:
        if a.deny:
            raw, extra, allow_bin, ignore = load_deny(a.deny)
            terms, allow = compile_terms(raw), allow + extra
        if a.vault:
            vault = load_vault(a.vault, Path(a.deny).resolve() if a.deny else None, ignore)
        if a.msg:
            files = [("(커밋 메시지)", Path(a.msg).read_bytes())]
        elif a.push:
            files, idents = push_items(sys.stdin.read())
        elif a.staged:
            files = staged_items()
            for kind, label in (("GIT_AUTHOR_IDENT", "(커밋 작성자)"), ("GIT_COMMITTER_IDENT", "(커미터)")):
                idents.append((label, *split_ident(git("var", kind).decode("utf-8", "replace"))))
        else:
            files = worktree_items()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
        print(f"검사를 못 했습니다. 안전하게 막습니다: {e}")
        return 2

    hits = []
    for path, data in files:
        if has_term(path, terms):
            hits.append((path, 0, "파일 이름에 금지어"))
        is_utf16 = data[:2] in (b"\xff\xfe", b"\xfe\xff")
        if b"\0" in data and not is_utf16:
            if path.split(" (커밋")[0] not in allow_bin:
                hits.append((path, 0, "이진 파일 (눈으로 확인 후 allow_binary 에 등록)"))
            continue
        scan_text(path, decode(data), terms, allow, vault, hits)
    for label, name, email in idents:
        check_ident(label, name, email, terms, hits)

    if not hits:
        print(f"통과: 항목 {len(files)}개, 금지어 {len(terms)}개, 금고 값 {len(vault)}개 대조")
        return 0
    print(f"막았습니다: {len(hits)}건 걸림")
    for path, no, kind in hits[:50]:
        print(f"  {path}{':' + str(no) if no else ''}  {kind}")
    if len(hits) > 50:
        print(f"  외 {len(hits) - 50}건")
    return 1


if __name__ == "__main__":
    sys.exit(main())
