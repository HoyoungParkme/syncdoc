import os
#!/usr/bin/env python3
"""원본 USECASE MD를 파싱해 사람용 뷰가 쓸 JSON을 만든다.
싱크독의 UC-S5(사람용 뷰 갱신)가 하는 일을 그대로 한 것."""
import re, json, sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "specs") + "/UC/SYNC-UC-001.md"
raw = open(SRC, encoding="utf-8").read()

ACTOR_OF = {"A": "agent", "H": "human", "G": "github", "S": "system"}

def parse_table(block):
    """| 항목 | 내용 | 형식의 표를 dict로"""
    rows = {}
    for line in block.split("\n"):
        m = re.match(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|$", line)
        if not m:
            continue
        k, v = m.group(1).strip(), m.group(2).strip()
        if k in ("항목", "---") or set(k) <= set("-: "):
            continue
        rows[k] = v
    return rows

def parse_flow(block):
    """번호 매긴 기본 흐름"""
    return [re.sub(r"^\d+\.\s*", "", l).strip()
            for l in block.split("\n") if re.match(r"^\d+\.", l.strip())]

def parse_ext(block):
    """확장: - **2a. 제목** / 2a1. 내용"""
    items, cur = [], None
    for line in block.split("\n"):
        s = line.strip()
        head = re.match(r"^-\s*\*\*(.+?)\*\*\s*$", s)
        if head:
            cur = {"on": head.group(1).strip(), "steps": []}
            items.append(cur)
            continue
        step = re.match(r"^-\s*(\d+[a-z]\d+\.\s*.+)$", s)
        if step and cur:
            cur["steps"].append(re.sub(r"^\d+[a-z]\d+\.\s*", "", step.group(1)).strip())
    return items

# 유스케이스 블록 분리
chunks = re.split(r"\n#### ", raw)
ucs = []
for ch in chunks[1:]:
    head = ch.split("\n", 1)[0].strip()
    m = re.match(r"^(UC-([AHGS])\d+)\s+(.+)$", head)
    if not m:
        continue
    uc_id, letter, name = m.group(1), m.group(2), m.group(3)
    body = ch.split("\n", 1)[1]

    tbl_block = body.split("**기본 흐름**")[0]
    tbl = parse_table(tbl_block)

    flow_block = body.split("**기본 흐름**")[1].split("**확장**")[0] if "**기본 흐름**" in body else ""
    after_ext = body.split("**확장**")[1] if "**확장**" in body else ""
    ext_block = re.split(r"\n\*\*(?:사후조건 참고|연관)\*\*", after_ext)[0]

    note = ""
    nm = re.search(r"\*\*사후조건 참고\*\*:\s*(.+)", body)
    if nm:
        note = nm.group(1).strip()
    links = ""
    lm = re.search(r"\*\*연관\*\*:\s*(.+)", body)
    if lm:
        links = lm.group(1).strip()

    ucs.append({
        "id": uc_id,
        "short": uc_id.replace("UC-", ""),
        "name": name,
        "actor": ACTOR_OF[letter],
        "scope": tbl.get("범위", ""),
        "level": tbl.get("수준", ""),
        "primary": tbl.get("주 액터", ""),
        "stakeholders": tbl.get("이해관계자와 관심사", ""),
        "pre": tbl.get("사전조건", ""),
        "minGuarantee": tbl.get("최소 보장", ""),
        "successGuarantee": tbl.get("성공 보장", ""),
        "trigger": tbl.get("트리거", ""),
        "package": tbl.get("패키지", ""),
        "include": tbl.get("포함(include)", ""),
        "extPoint": tbl.get("확장점(extension point)", ""),
        "general": tbl.get("일반화", ""),
        "flow": parse_flow(flow_block),
        "ext": parse_ext(ext_block),
        "note": note,
        "links": links,
    })

# 대응표 추출
def grab_table(after_heading):
    seg = raw.split(after_heading)[1]
    lines, out = seg.strip().split("\n"), []
    for l in lines[2:]:
        if not l.startswith("|"):
            break
        cells = [c.strip() for c in l.strip("|").split("|")]
        out.append(cells)
    return out

data = {
    "ucs": ucs,
    "scenarioMap": grab_table("### 4.1 유스케이스 ↔ 시나리오"),
    "reqMap": grab_table("### 4.2 요구사항 ↔ 유스케이스"),
}

print(f"유스케이스 {len(ucs)}개 파싱", file=sys.stderr)
for u in ucs:
    empty = [k for k in ("scope","level","primary","stakeholders","pre",
                          "minGuarantee","successGuarantee","trigger",
                          "package","include","extPoint","general") if not u[k]]
    if empty or not u["flow"] or not u["ext"]:
        print(f"  ! {u['id']} 누락: {empty} flow={len(u['flow'])} ext={len(u['ext'])}", file=sys.stderr)

open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json"), "w", encoding="utf-8").write(
    json.dumps(data, ensure_ascii=False, indent=1))
print("data.json 생성", file=sys.stderr)
