//! 카드 L14 테스트 관점 — 묻기(SYNC-MS-018 ask_item·ask_tool·ask_code·conversation_view)와 모델 어댑터
//! (SYNC-MS-020 Llm.step_stream). 시험 DB · 임시 자리 · 진짜 git · 작은 가짜 모델 서버(대본대로 답하고 받은 본문을 남긴다)

mod support;

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};

use axum::Router;
use axum::body::Bytes;
use axum::extract::State;
use axum::http::{StatusCode, header};
use axum::response::{IntoResponse, Response};
use serde_json::{Map, Value, json};
use sqlx::PgConnection;
use syncdoc_core::account::model::UserRow;
use syncdoc_core::conversation::ConversationService;
use syncdoc_core::errors::Problem;
use syncdoc_core::infra::llm::Llm;
use syncdoc_core::pipeline::{self, SaveInput};
use syncdoc_core::project::service::{ProjectService, ServerRepos};
use syncdoc_core::queries;
use syncdoc_core::types::{AskEvent, AskStream, Author, AuthorKind, Entry, Storage};

const CODE: &str = "LQ";
const PRD: &str = "# 묻기 시험\n\n## 1. 목표\n\n## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 첫 기능\n설명.\n\n#### R13 열셋째\n설명.\n\n## 4. 성공지표\n\n## 5. 미결사항\n";

type Script = Arc<Mutex<VecDeque<(u16, &'static str, String)>>>;

#[derive(Clone)]
struct Fake {
    bodies: Arc<Mutex<Vec<Value>>>,
    script: Script,
}

async fn answer(State(f): State<Fake>, body: Bytes) -> Response {
    let v: Value = serde_json::from_slice(&body).unwrap_or(Value::Null);
    f.bodies.lock().expect("본문").push(v);
    let next = f.script.lock().expect("대본").pop_front();
    let (status, ctype, text) = next.unwrap_or((500, "text/plain", "대본 없음".into()));
    (
        StatusCode::from_u16(status).expect("상태"),
        [(header::CONTENT_TYPE, ctype)],
        text,
    )
        .into_response()
}

/// 가짜 모델을 띄운다 — 주소와 본문 기록
async fn fake(script: Vec<(u16, &'static str, String)>) -> (Llm, Fake) {
    let f = Fake {
        bodies: Arc::default(),
        script: Arc::new(Mutex::new(script.into())),
    };
    let app = Router::new()
        .route("/v1/chat/completions", axum::routing::post(answer))
        .with_state(f.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("자리");
    let port = listener.local_addr().expect("포트").port();
    tokio::spawn(async move {
        axum::serve(listener, app).await.expect("가짜 모델");
    });
    (
        Llm {
            url: format!("http://127.0.0.1:{port}/v1/chat/completions"),
            key: "k".into(),
            model: "fake".into(),
        },
        f,
    )
}

fn sse(chunks: &[Value]) -> (u16, &'static str, String) {
    let mut s: String = chunks
        .iter()
        .map(|c| format!("data: {c}\r\n\r\n"))
        .collect();
    s.push_str("data: [DONE]\n\n");
    (200, "text/event-stream", s)
}

fn call(id: &str, name: &str, args: &str) -> Value {
    json!({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": id, "function": {"name": name, "arguments": args}}]}}]})
}

fn text(t: &str) -> Value {
    json!({"choices": [{"delta": {"content": t}}]})
}

struct Env {
    db: support::TestDb,
    _tmp: tempfile::TempDir,
    repos: ServerRepos,
    user: UserRow,
}

async fn user(c: &mut PgConnection, login: &str) -> UserRow {
    sqlx::query_as::<_, UserRow>(
        "INSERT INTO users (github_login, display_name, kind) VALUES ($1, $1 || ' 님', 'local') \
         RETURNING id, github_login, github_user_id, display_name, github_token_encrypted, created_at, kind",
    )
    .bind(login)
    .fetch_one(c)
    .await
    .expect("사용자")
}

async fn env() -> Env {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시 자리");
    let repos = support::server_repos(tmp.path());
    let mut c = db.pool.acquire().await.expect("연결");
    let u = user(&mut c, "asker").await;
    ProjectService {
        db: &mut c,
        repos: &repos,
    }
    .init_project(&db.pool, CODE, "묻기 시험", &u, false, Storage::Server)
    .await
    .expect("프로젝트");
    drop(c);
    pipeline::save_pipeline(
        &db.pool,
        &repos,
        SaveInput {
            entry: Entry::Mcp,
            doc_id: None,
            doc_type: Some("PRD".into()),
            body: PRD.into(),
            expected_version: None,
            project_code: Some(CODE.into()),
            author: Author {
                kind: AuthorKind::Agent,
                user: u.clone(),
                instructed_by: Some(u.clone()),
                via: Entry::Mcp,
            },
            message: "PRD".into(),
            confirm_item_deletion: false,
            reason: None,
            restore: false,
            read_first: true,
            commit_hash: None,
        },
    )
    .await
    .expect("PRD");
    Env {
        db,
        _tmp: tmp,
        repos,
        user: u,
    }
}

impl Env {
    async fn conversation(&self) -> i32 {
        let mut c = self.db.pool.acquire().await.expect("연결");
        ConversationService {
            db: &mut c,
            repos: &self.repos,
        }
        .create(CODE, &self.user, None)
        .await
        .expect("대화")
        .id
    }
}

async fn tool(
    c: &mut PgConnection,
    e: &Env,
    conv: i32,
    name: &str,
    a: Value,
) -> syncdoc_core::types::ToolResult {
    let a: Map<String, Value> = a.as_object().cloned().unwrap_or_default();
    queries::ask_tool(c, &e.repos, name, &a, CODE, &e.user, conv)
        .await
        .expect("도구")
}

async fn drain(mut rx: AskStream) -> Vec<Result<AskEvent, Problem>> {
    let mut out = Vec::new();
    while let Some(x) = rx.recv().await {
        out.push(x);
    }
    out
}

#[tokio::test]
async fn one_tool_call_then_answer_streams_events_and_closes_the_turn() {
    let e = env().await;
    let conv = e.conversation().await;
    let (llm, f) = fake(vec![
        sse(&[
            text("먼저 "),
            text("읽는다"),
            call("c1", "get_item", "{\"doc_id\": \"LQ-PRD-001\","),
            json!({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": " \"item_id\": \"R1\", \"reason\": \"R1을 본다\"}"}}]}}]}),
            json!({"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 3}}),
        ]),
        sse(&[text("답은 LQ-PRD-001#R1"), text("이다")]),
    ])
    .await;
    let rx = queries::ask_item(
        &e.db.pool,
        &e.repos,
        &llm,
        "LQ-PRD-001",
        Some("R13"),
        i64::from(conv),
        "R1이 뭐야",
        &[],
        &e.user,
    )
    .await
    .expect("시작");
    let events: Vec<AskEvent> = drain(rx)
        .await
        .into_iter()
        .map(|x| x.expect("이벤트"))
        .collect();
    assert_eq!(
        events,
        [
            AskEvent::Start {
                doc_id: Some("LQ-PRD-001".into()),
                item_id: Some("R13".into()),
                key: None
            },
            AskEvent::Delta("먼저 ".into()),
            AskEvent::Delta("읽는다".into()),
            AskEvent::Note("먼저 읽는다".into()),
            AskEvent::Note("R1을 본다".into()),
            AskEvent::Read {
                tool: "get_item".into(),
                target: Some("LQ-PRD-001#R1".into())
            },
            AskEvent::Delta("답은 LQ-PRD-001#R1".into()),
            AskEvent::Delta("이다".into()),
            AskEvent::Answer {
                answer: "답은 [[LQ-PRD-001#R1]]이다".into(),
                context_item_ids: vec!["LQ-PRD-001#R1".into()],
                missing_refs: vec![]
            },
        ]
    );
    // 모델에 보낸 본문 — 시작 맥락·도구 아홉·스트림, 둘째는 도구 호출과 결과
    let bodies = f.bodies.lock().expect("본문").clone();
    assert_eq!(bodies.len(), 2);
    let first = &bodies[0];
    assert_eq!(
        first
            .as_object()
            .map(|o| o.keys().cloned().collect::<Vec<_>>()),
        Some(vec![
            "model".into(),
            "messages".into(),
            "tools".into(),
            "tool_choice".into(),
            "stream".into(),
            "stream_options".into()
        ])
    );
    assert_eq!(first["tools"].as_array().map(Vec::len), Some(9));
    let system = first["messages"][0]["content"].as_str().expect("지시문");
    assert!(system.contains("[문서] LQ-PRD-001"), "{system}");
    assert!(system.contains("[지금 보는 항목] R13 열셋째"), "{system}");
    assert!(system.contains("R1 첫 기능\nR13 열셋째"), "{system}");
    let second = &bodies[1]["messages"];
    assert_eq!(second[2]["role"], "assistant");
    assert_eq!(second[2]["content"], "먼저 읽는다");
    assert_eq!(
        second[2]["tool_calls"][0]["function"]["arguments"],
        "{\"doc_id\": \"LQ-PRD-001\", \"item_id\": \"R1\", \"reason\": \"R1\\uc744 \\ubcf8\\ub2e4\"}"
    );
    assert_eq!(second[3]["role"], "tool");
    let tool: Value =
        serde_json::from_str(second[3]["content"].as_str().expect("결과")).expect("JSON");
    assert_eq!(tool["display_name"], "첫 기능");
    // 턴 — 원문 답·진행 줄·본 것, 제목은 질문
    let mut c = e.db.pool.acquire().await.expect("연결");
    let v = queries::conversation_view(&mut c, &e.repos, conv, &e.user)
        .await
        .expect("대화");
    assert_eq!(v.title, "R1이 뭐야");
    let t = &v.turns[0];
    assert_eq!(t.answer.as_deref(), Some("답은 [[LQ-PRD-001#R1]]이다"));
    assert_eq!(
        t.progress
            .iter()
            .map(|p| (p.kind.as_str(), p.text.as_str()))
            .collect::<Vec<_>>(),
        [
            ("note", "먼저 읽는다"),
            ("note", "R1을 본다"),
            ("read", "get_item LQ-PRD-001#R1")
        ]
    );
    let raw: Option<String> = sqlx::query_scalar("SELECT answer FROM turns")
        .fetch_one(&mut *c)
        .await
        .expect("원문");
    assert_eq!(raw.as_deref(), Some("답은 LQ-PRD-001#R1이다"));
}

#[tokio::test]
async fn failures_before_and_after_start() {
    let e = env().await;
    let conv = e.conversation().await;
    // 키 없음 — 네트워크 전, 턴 없음
    let off = Llm::default();
    assert!(matches!(
        queries::ask_item(
            &e.db.pool,
            &e.repos,
            &off,
            "LQ-PRD-001",
            None,
            i64::from(conv),
            "q",
            &[],
            &e.user
        )
        .await,
        Err(Problem::LlmNotConfigured)
    ));
    // 없는 항목 — 스트림 전, 턴은 남지 않는다(트랜잭션째)
    let (llm, f) = fake(vec![
        (500, "text/plain", "죽음".into()),
        (
            200,
            "application/json",
            json!({"choices": [{"message": {"content": "단발 답"}}]}).to_string(),
        ),
    ])
    .await;
    assert!(matches!(
        queries::ask_item(&e.db.pool, &e.repos, &llm, "LQ-PRD-001", Some("R9"), i64::from(conv), "q", &[], &e.user).await,
        Err(Problem::NotFound { resource, .. }) if resource == "item"
    ));
    assert!(matches!(
        queries::ask_item(
            &e.db.pool,
            &e.repos,
            &llm,
            "LQ-PRD-001",
            None,
            1 << 40,
            "q",
            &[],
            &e.user
        )
        .await,
        Err(Problem::Internal { .. })
    ));
    let mut c = e.db.pool.acquire().await.expect("연결");
    let n: i64 = sqlx::query_scalar("SELECT count(*) FROM turns")
        .fetch_one(&mut *c)
        .await
        .expect("수");
    assert_eq!(n, 0);
    // 모델 500 — 시작 뒤 error, 턴은 그 이유로 닫힌다
    let rx = queries::ask_item(
        &e.db.pool,
        &e.repos,
        &llm,
        "LQ-PRD-001",
        None,
        i64::from(conv),
        "q",
        &[],
        &e.user,
    )
    .await
    .expect("시작");
    let out = drain(rx).await;
    assert!(matches!(out[0], Ok(AskEvent::Start { .. })));
    assert!(matches!(&out[1], Err(Problem::LlmUnavailable { reason }) if reason == "HTTP 500"));
    // 단발 JSON — 조각 없이 답
    let rx = queries::ask_item(
        &e.db.pool,
        &e.repos,
        &llm,
        "LQ-PRD-001",
        None,
        i64::from(conv),
        "q2",
        &[],
        &e.user,
    )
    .await
    .expect("시작");
    let out: Vec<AskEvent> = drain(rx)
        .await
        .into_iter()
        .map(|x| x.expect("이벤트"))
        .collect();
    assert_eq!(out.len(), 2);
    assert!(matches!(&out[1], AskEvent::Answer { answer, .. } if answer == "단발 답"));
    assert_eq!(f.bodies.lock().expect("본문").len(), 2);
    let v = ConversationService {
        db: &mut c,
        repos: &e.repos,
    }
    .get(conv, &e.user)
    .await
    .expect("대화");
    assert_eq!(
        v.turns
            .iter()
            .map(|t| t.error.as_deref())
            .collect::<Vec<_>>(),
        [Some("HTTP 500"), None]
    );
}

#[tokio::test]
async fn eight_calls_then_wrap_up_without_tools() {
    let e = env().await;
    let conv = e.conversation().await;
    let mut script: Vec<_> = (0..8)
        .map(|i| {
            sse(&[call(
                &format!("c{i}"),
                "list_documents",
                "{\"reason\": \"목록\"}",
            )])
        })
        .collect();
    script.push(sse(&[text("마무리 답")]));
    let (llm, f) = fake(script).await;
    let rx = queries::ask_item(
        &e.db.pool,
        &e.repos,
        &llm,
        "LQ-PRD-001",
        None,
        i64::from(conv),
        "q",
        &[],
        &e.user,
    )
    .await
    .expect("시작");
    let out: Vec<AskEvent> = drain(rx)
        .await
        .into_iter()
        .map(|x| x.expect("이벤트"))
        .collect();
    assert!(matches!(out.last(), Some(AskEvent::Answer { answer, .. }) if answer == "마무리 답"));
    let bodies = f.bodies.lock().expect("본문").clone();
    assert_eq!(bodies.len(), 9);
    let last = &bodies[8];
    assert_eq!(last["tool_choice"], "none");
    let msgs = last["messages"].as_array().expect("메시지");
    assert!(
        msgs.last()
            .and_then(|m| m["content"].as_str())
            .is_some_and(|c| c.starts_with("도구 호출 상한"))
    );
}

#[tokio::test]
async fn ask_tool_answers_text_for_the_model() {
    let e = env().await;
    let conv = e.conversation().await;
    let mut c = e.db.pool.acquire().await.expect("연결");
    let r = tool(&mut c, &e, conv, "nope", json!({})).await;
    assert_eq!(r.text, "{\"error\": \"모르는 도구 nope\"}");
    let r = tool(
        &mut c,
        &e,
        conv,
        "get_item",
        json!({"doc_id": "LQ-PRD-001"}),
    )
    .await;
    assert_eq!(r.text, "{\"error\": \"인자 item_id·reason가 없다\"}");
    let r = tool(
        &mut c,
        &e,
        conv,
        "get_item",
        json!({"doc_id": "XX-PRD-001", "item_id": "R1", "reason": "r"}),
    )
    .await;
    assert_eq!(r.text, "{\"error\": \"없음\", \"doc_id\": \"XX-PRD-001\"}");
    let r = tool(
        &mut c,
        &e,
        conv,
        "get_item",
        json!({"doc_id": "LQ-PRD-001", "item_id": "R9", "reason": "r"}),
    )
    .await;
    assert!(
        r.text
            .starts_with("{\"error\": \"없음\", \"hint\": \"이 문서에 그 항목이 없다.")
    );
    assert!(
        r.text
            .ends_with("\"resource\": \"item\", \"id\": \"LQ-PRD-001#R9\"}"),
        "{}",
        r.text
    );
    let r = tool(&mut c, &e, conv, "list_documents", json!({"reason": "r"})).await;
    assert_eq!(r.target, None);
    let docs: Value = serde_json::from_str(&r.text).expect("JSON");
    assert_eq!(docs[0]["title"], "묻기 시험");
    let r = tool(
        &mut c,
        &e,
        conv,
        "get_document",
        json!({"doc_id": "LQ-PRD-001", "reason": "r"}),
    )
    .await;
    assert_eq!(r.target.as_deref(), Some("LQ-PRD-001"));
    let r = tool(
        &mut c,
        &e,
        conv,
        "item_chain",
        json!({"doc_id": "LQ-PRD-001", "item_id": "R1", "reason": "r"}),
    )
    .await;
    let chain: Value = serde_json::from_str(&r.text).expect("JSON");
    assert_eq!(chain["rows"].as_array().map(Vec::len), Some(11));
    for name in ["code_graph", "read_code", "find_code"] {
        let a = match name {
            "code_graph" => json!({"doc_id": "LQ-PRD-001", "item_id": "R1", "reason": "r"}),
            "read_code" => json!({"target": "a.py", "reason": "r"}),
            _ => json!({"query": "a", "reason": "r"}),
        };
        let r = tool(&mut c, &e, conv, name, a).await;
        assert_eq!(
            r.text,
            "{\"error\": \"코드 그래프 없음\", \"hint\": \"코드를 push하면 서버가 만든다\"}"
        );
    }
    let r = tool(
        &mut c,
        &e,
        conv,
        "read_attachment",
        json!({"attachment_id": "7", "reason": "r"}),
    )
    .await;
    assert_eq!(
        r.text,
        "{\"error\": \"없음\", \"attachment_id\": 7, \"hint\": \"이미지는 붙인 질문에 이미 보였다\"}"
    );
}
