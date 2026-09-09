#!/usr/bin/env python3
"""SYNC-STD-001 명세 작성 규약 3장(위반)·4장(미완성)을 그대로 옮긴 검증기.
SpecService.validate의 원형. 문서 경로들을 받아 위반·경고를 출력한다."""
import re, sys, os

TYPES = {
  # type: (항목 패턴들, 필수 절 이름들)
  "RFQ":  ([r"Q\d+"], ["배경", "요구", "사용자와 환경", "미정"]),
  "PRD":  ([r"G\d+", r"R\d+", r"N\d+"], ["목표", "비목표", "요구사항", "성공지표", "미결사항"]),
  "SCN":  ([r"P\d+", r"S\d+"], ["페르소나", "시나리오", "대응표"]),
  "UC":   ([r"UC-[AHGS]\d+"], ["액터", "사용자 목표 수준 유스케이스", "하위기능 수준 유스케이스", "대응표"]),
  "INFRA":([r"C\d+"], ["제약", "구성도", "기술 스택", "데이터가 사는 곳", "인증과 접근", "미결사항"]),
  "DOM":  ([r"[A-Z][A-Za-z]+", r"[a-z][a-z0-9_]+"], None),  # 문서별로 아래에서 세분
  "UI":   ([r"UI-\d+"], None),
  "API":  ([r"(GET|POST|PUT|PATCH|DELETE)/\S+", r"[a-z][a-z_]+"], None),
  "SEQ":  ([r"SEQ-\d+", r"SEQ-C\d+"], ["생명선", "대응표", "되먹일 것"]),
  "MS":   ([r"[A-Za-z_]+\.[a-z_]+"], ["함수 목록", "미결사항"]),
  "CODE": ([r"[A-C]\d*"], ["슬라이스", "통합 테스트", "커밋", "미결사항"]),
  "STD":  ([r"[A-Z]+-\d+", r"V-[A-Z]+"], ["미결사항"]),
}
# 같은 타입 안에서 문서 성격이 다른 것: 제목으로 구분
SUBTYPES = {
  ("DOM", "도메인"): ([r"[A-Z][A-Za-z]+"], ["개념 식별", "개념 모델", "개념별 정리", "경계", "미결사항"]),
  ("DOM", "클래스"): ([r"[A-Z][A-Za-z]+"], ["폴더 구조", "엔티티", "의존 관계", "설계 클래스", "미결사항"]),
  ("DOM", "ERD"):   ([r"[a-z][a-z0-9_]+"], ["ERD", "DD", "인덱스", "미결사항"]),
  ("UI", "화면 설계"): ([r"UI-\d+"], ["유스케이스 대응", "화면 목록", "공통 틀", "화면 흐름", "미결사항"]),
  ("UI", "와이어프레임"): ([r"UI-\d+"], ["형식"]),
  ("API", "REST"): ([r"(GET|POST|PUT|PATCH|DELETE)/\S+"], ["규칙", "에러", "엔드포인트", "미결사항"]),
  ("API", "MCP"):  ([r"[a-z][a-z_]+"], ["규칙", "도구", "에이전트 순서", "미결사항"]),
}
DOC_ID = re.compile(r"^[A-Z]{1,4}-[A-Z]+-\d{3}$")
REF = re.compile(r"\[\[([^\]]+)\]\]")

def strip_code(text):
    """코드블록을 빈 줄로 치환 (줄 번호 유지)"""
    out, inblk = [], False
    for l in text.split("\n"):
        if l.startswith("```"):
            inblk = not inblk; out.append(""); continue
        out.append("" if inblk else re.sub(r"`[^`]*`", lambda m: " " * len(m.group(0)), l))
    return "\n".join(out)

def _type_of_dir(name):
    """디렉터리 이름 → 타입. `06-DOM` → `DOM` (SYNC-STD-001 1.1). STD는 번호가 없다."""
    return name.split("-", 1)[1] if name[:2].isdigit() and "-" in name else name


def validate(path, deleted_ids=()):
    raw = open(path, encoding="utf-8").read()
    V, W = [], []
    fname = os.path.basename(path)

    # ── frontmatter ──
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
    if not m:
        V.append((1, "frontmatter.missing", "frontmatter 블록 없음")); return V, W, {}
    fm = {}
    for line in m.group(1).split("\n"):
        k, _, v = line.partition(":"); fm[k.strip()] = v.strip()
    for f in ("doc_id", "type", "title", "status"):
        if f not in fm: V.append((2, "frontmatter.field", f"필수 필드 {f} 없음"))
    typ = fm.get("type", "")
    if typ not in TYPES: V.append((2, "frontmatter.type", f"type {typ!r}"))
    if fm.get("status") not in ("draft", "review", "approved"): V.append((2, "frontmatter.status", fm.get("status")))
    did = fm.get("doc_id", "")
    if not DOC_ID.match(did): V.append((2, "frontmatter.doc_id", f"형식 {did!r}"))
    elif did.split("-")[1] != typ: V.append((2, "frontmatter.doc_id", f"{did}의 타입 ≠ {typ}"))
    elif fname != f"{did}.md": V.append((2, "frontmatter.doc_id", f"파일명 {fname} ≠ {did}.md"))
    elif _type_of_dir(os.path.basename(os.path.dirname(os.path.abspath(path)))) != typ: V.append((2, "frontmatter.doc_id", f"디렉터리 ≠ {typ}"))
    up = fm.get("upstream", "")
    for u in re.findall(r"[\w-]+", up.strip("[]")):
        if not DOC_ID.match(u): V.append((2, "frontmatter.ref", f"upstream {u!r}"))

    # 타입·서브타입 패턴
    pats, secs = TYPES.get(typ, ([], []))
    title = fm.get("title", "")
    for (t, key), (p, s) in SUBTYPES.items():
        if t == typ and key in title: pats, secs = p, s
    if secs is None: secs = []
    item_re = re.compile(r"^(?:" + "|".join(pats) + r")$") if pats else None

    # ── 헤딩 순회 ──
    body = strip_code(raw[m.end():])
    offset = raw[:m.end()].count("\n")
    seen, items, sections = {}, [], []
    for i, l in enumerate(body.split("\n"), start=offset + 1):
        h = re.match(r"^(#{1,6}) (.+)$", l)
        if not h: continue
        tok = h.group(2).split(" ")[0]
        text = h.group(2)
        if item_re and item_re.match(tok):
            if tok in seen: V.append((i, "item.duplicate", tok))
            seen[tok] = i; items.append(tok)
            if tok in deleted_ids: V.append((i, "item.reused", tok))
            if re.search(r"(?<![0-9])0\d", tok): V.append((i, "item.padding", tok))
        else:
            if re.match(r"[.:]$", tok) and item_re and item_re.match(tok[:-1]):
                V.append((i, "item.punct", tok))
            elif re.match(r"^[A-Z]+-?\d+$", tok) and item_re:
                V.append((i, "item.pattern", f"{tok} — ID처럼 보이지만 {typ} 패턴 아님"))
            sections.append(re.sub(r"^[\d.]+\s*", "", text))

    # ── 참조 형식 ──
    for i, l in enumerate(body.split("\n"), start=offset + 1):
        for r in REF.findall(l):
            d, _, it = r.partition("#")
            if d == "": d = did   # [[#항목]] = 같은 문서
            if not DOC_ID.match(d) or (it and " " in it):
                V.append((i, "ref.format", r))

    # ── 미완성 ──
    for s in secs:
        if not any(sec.startswith(s) for sec in sections):
            W.append(("section.missing", s))
    if not items and typ not in ("CODE", "STD"):
        W.append(("item.none", ""))

    return V, W, {"doc_id": did, "type": typ, "items": items, "sections": sections}

if __name__ == "__main__":
    import glob
    paths = sys.argv[1:] or sorted(p for p in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "specs", "*", "*.md")) if "/_templates/" not in p)
    total_v = total_w = 0
    for p in paths:
        V, W, info = validate(p)
        total_v += len(V); total_w += len(W)
        tag = "위반" if V else ("미완성" if W else "통과")
        print(f"{os.path.basename(p):32s} {info.get('doc_id','?'):14s} {tag:4s} 항목{len(info.get('items',[])):3d}  ", end="")
        print(("위반 " + "; ".join(f"L{l} {r} {m}" for l, r, m in V[:4])) if V else "", end="")
        print(("  경고 " + "; ".join(f"{r}:{m}" for r, m in W)) if W else "")
    print(f"\n합계: 위반 {total_v}, 경고 {total_w}")
