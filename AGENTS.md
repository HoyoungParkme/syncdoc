# AGENTS.md — 이 저장소에서 에이전트가 일하는 법

이 저장소는 **명세 우선**이다. 코드는 명세를 옮긴 것이고, 명세에 없는 코드는 만들지 않는다.

## 처음 열었을 때

1. `docs/specs/STD/SYNC-STD-004.md` — 개발 규약. 코드가 지켜야 할 규칙 17개(DEV-1~17)
2. `docs/specs/STD/SYNC-STD-001.md` — 명세 작성 규약. 명세를 고쳐야 할 때
3. `docs/specs/11-CODE/SYNC-CODE-001.md` — 구현 계획. **여기서 카드 하나를 받는다**

## 폴더 구조 (DOM-002 1장)

```
syncdoc/            저장소 = 프로젝트
├── backend/        파이썬. app/(임포트 패키지) · tests/ · alembic/ · pyproject.toml
├── frontend/       React 소스 (Vite+TS). 빌드 → backend/app/web/static
├── docs/specs/     명세 원본. 디렉터리는 {NN-TYPE} — 번호가 읽는 순서 (STD-001 1.1)
├── tools/          validate.py · check_code.py · check_ui.py · view_build.py · dev_preview.py
├── scripts/        tunnel.sh — Quick Tunnel 기동
└── Dockerfile · docker-compose.yml
```

## 작업 순서 (DEV-13)

```
1. CODE-001에서 완료가 "—"이고 선행이 끝난 첫 카드를 받는다
2. 카드의 참조를 전부 연다 — 시나리오·유스케이스(왜) → MINISPEC(어떻게) → API·화면(입구)
   참조 형식: [[SYNC-MS-002#SpecService.save]] → docs/specs/10-MS/SYNC-MS-002.md 의 #### SpecService.save 블록
3. MINISPEC 순서대로 구현. 함수 하나 = 커밋 하나. docstring 첫 줄 = MINISPEC 항목 ID (DEV-3)
4. MINISPEC "테스트 관점"을 테스트로. 통과할 때까지
5. 카드의 E2E (시나리오 흐름 그대로)
6. 완료 조건(DEV-14) 여섯 확인 → CODE-001 카드 완료란에 커밋·날짜 기록 → 다음 카드
   화면이 있는 카드는 일곱째 — 사람이 브라우저에서 data-el 대로 눌러 본다 (DEV-17)
```

## 막혔을 때

명세가 틀렸거나 모자란 것이다. **코드로 우회하지 않는다.**
- 함수가 필요한데 MINISPEC에 없다 → MINISPEC에 추가하고 클래스 명세(DOM-002)도 맞춘다
- 시그니처가 안 맞는다 → MINISPEC이 진실. 클래스 명세를 고친다
- 흐름이 다르다 → SEQUENCE를 고친다
- 고친 뒤 `python tools/validate.py` 로 위반 0 확인

## 도구

파이썬은 `backend/`에서 돈다 — `cd backend && uv run pytest` · `uv run ruff check .` · `uv run alembic upgrade head`.
검사기는 저장소 루트에서 돈다.

- `python tools/validate.py` — 명세 규약 검사 (STD-001 3·4장). 위반 0·경고 0이어야 한다
- `python tools/check_code.py` — MINISPEC↔코드 시그니처 대조 (DEV-14 첫째·둘째)
- `python tools/check_ui.py` — 와이어프레임 요소 번호↔React `data-el` 대조 (DEV-17)
- `python tools/check_dom.py` — DOM 세 문서(도메인·클래스·데이터)의 이름 일치 (STD-001 4장 `dom.name`)
- `python tools/open_items.py` — 명세의 열린 미결 모음. `--markdown`이 STD-003 5장 내용, `--check`가 그것과 대조
- `python tools/view_build.py --all` — 사람용 뷰 생성 → `docs/views/`. React 유저용 탭의 참조 구현
- `python tools/dev_preview.py` — 개발 DB에 시드를 넣고 앱을 띄운다. 화면 확인용
- 커밋 메시지: 코드 `code(슬라이스): 함수 — 요약` · 명세 `spec(문서ID): 요약` · 상태 `status(문서ID): a → b` · 끝난 슬라이스 수정 `fix(#이슈번호): 요약`(DEV-15). 둘째 줄부터 이유

## 문서 위치

```
docs/specs/{NN-TYPE}/{doc_id}.md   원본 (에이전트가 읽는 것). 01-RFQ … 11-CODE, 단계 밖은 STD
docs/specs/_templates/{TYPE}.md    새 문서 뼈대
docs/views/                        사람용 뷰 (생성물. 커밋 안 함)
tools/                             검사기·뷰 생성기
```

체인 전체 지도는 `docs/specs/STD/SYNC-STD-003.md`.
