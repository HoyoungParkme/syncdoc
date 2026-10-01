# docs/specs — 명세 원본

싱크독 명세 체인 11단계 + STD. 쓰는 법은 아래 셋이다.

- [명세 작성 규약 SYNC-STD-001](https://github.com/HoyoungParkme/syncdoc/blob/main/docs/specs/STD/SYNC-STD-001.md) — 필수 절과 항목 ID 형식은 그 2장
- [개발 규약 SYNC-STD-004](https://github.com/HoyoungParkme/syncdoc/blob/main/docs/specs/STD/SYNC-STD-004.md)
- [타입별 뼈대 `_templates/`](https://github.com/HoyoungParkme/syncdoc/blob/main/docs/specs/_templates)

**이 저장소에는 규약·템플릿 사본을 두지 않는다.** 규약이 바뀌면 위 링크 끝이 바뀐다.
에이전트는 싱크독 MCP의 `get_template`으로 타입별 뼈대와 규약을 받는다.

**위에서 아래로 읽는다.** 디렉터리 번호가 그 순서다.

| # | 디렉터리 | 무엇 |
|---|---|---|
| 1 | `01-RFQ` | 요청 — 무엇을 원하나 |
| 2 | `02-PRD` | 제품 요구사항 |
| 3 | `03-SCN` | 사용자 시나리오 |
| 4 | `04-UC` | 유스케이스 |
| 5 | `05-INFRA` | 인프라·제약 |
| 6 | `06-DOM` | 도메인 모델 · **클래스 명세** · ERD·DD (문서 셋 — **한 번에 쓰지 않는다.** 아래) |
| 7 | `07-UI` | 화면 설계 · 와이어프레임 |
| 8 | `08-API` | REST · MCP 도구 |
| 9 | `09-SEQ` | 시퀀스 |
| 10 | `10-MS` | MINISPEC — 함수 단위 |
| 11 | `11-CODE` | 구현 슬라이스 카드 |
| — | `STD` | 작성 규약·뷰 규약·개발 규약 (단계 밖 — 싱크독 저장소에 있다) |

- 경로 `docs/specs/{NN-TYPE}/{doc_id}.md` · 문서 ID `{프로젝트코드}-{TYPE}-{NNN}`
- 상태(`status`)는 frontmatter가 진실. 변경은 싱크독 웹에서만
- 첨부는 `assets/` — 문서에서는 문서 폴더 기준 상대 경로(`../assets/x.png`)
- 화면(UI) 배치는 디자인 도구 산출물(스타일까지 든 자기 완결 html)을 그대로 넣는다(규약 2.7)
- 커밋·PR에 에이전트 표시(Co-Authored-By 등)를 남기지 않는다. 작성자는 사람의 계정이다
- **문서 하나를 만들거나 고치면 멈춘다.** 사람이 웹에서 읽고 「다음」이라고 한 뒤에 다음 문서.
  단계가 아니라 문서가 단위다(규약 1.8)
- DOM 셋은 순서가 있다. 도메인 모델은 6에서, 클래스 명세는 8 API 뒤에 돌아와서,
  ERD는 클래스 명세 뒤에(규약 2.6)
