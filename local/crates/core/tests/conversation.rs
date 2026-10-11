//! 카드 L14 테스트 관점 — 대화·턴·첨부(SYNC-MS-021 ConversationService). 시험 DB · 임시 자리

mod support;

use sqlx::PgConnection;
use syncdoc_core::account::model::UserRow;
use syncdoc_core::conversation::ConversationService;
use syncdoc_core::errors::Problem;
use syncdoc_core::project::service::{ProjectService, ServerRepos};
use syncdoc_core::types::{LlmMessage, Progress, Storage};

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

struct Env {
    db: support::TestDb,
    _tmp: tempfile::TempDir,
    repos: ServerRepos,
    me: UserRow,
    other: UserRow,
}

async fn env() -> Env {
    let db = support::test_db().await;
    let tmp = tempfile::tempdir().expect("임시 자리");
    let repos = support::server_repos(tmp.path());
    let mut c = db.pool.acquire().await.expect("연결");
    let me = user(&mut c, "me").await;
    let other = user(&mut c, "other").await;
    for (code, owner) in [("LC", &me), ("LO", &other)] {
        ProjectService {
            db: &mut c,
            repos: &repos,
        }
        .init_project(&db.pool, code, "대화 시험", owner, false, Storage::Server)
        .await
        .expect("프로젝트");
    }
    drop(c);
    Env {
        db,
        _tmp: tmp,
        repos,
        me,
        other,
    }
}

/// 두 쪽 PDF — 쪽마다 글자 한 줄
fn pdf(pages: &[&str]) -> Vec<u8> {
    use lopdf::content::{Content, Operation};
    use lopdf::{Document, Object, Stream, dictionary};
    let mut doc = Document::with_version("1.5");
    let pages_id = doc.new_object_id();
    let font_id = doc.add_object(dictionary! {
        "Type" => "Font", "Subtype" => "Type1", "BaseFont" => "Helvetica",
    });
    let resources_id = doc.add_object(dictionary! {
        "Font" => dictionary! { "F1" => font_id },
    });
    let mut kids = Vec::new();
    for text in pages {
        let content = Content {
            operations: vec![
                Operation::new("BT", vec![]),
                Operation::new("Tf", vec!["F1".into(), 24.into()]),
                Operation::new("Td", vec![72.into(), 700.into()]),
                Operation::new("Tj", vec![Object::string_literal(*text)]),
                Operation::new("ET", vec![]),
            ],
        };
        let content_id =
            doc.add_object(Stream::new(dictionary! {}, content.encode().expect("내용")));
        let page_id = doc.add_object(dictionary! {
            "Type" => "Page", "Parent" => pages_id, "Contents" => content_id,
        });
        kids.push(page_id.into());
    }
    let count = kids.len() as i64;
    doc.objects.insert(
        pages_id,
        Object::Dictionary(dictionary! {
            "Type" => "Pages", "Kids" => kids, "Count" => count,
            "Resources" => resources_id, "MediaBox" => vec![0.into(), 0.into(), 595.into(), 842.into()],
        }),
    );
    let catalog_id = doc.add_object(dictionary! { "Type" => "Catalog", "Pages" => pages_id });
    doc.trailer.set("Root", catalog_id);
    let mut out = Vec::new();
    doc.save_to(&mut out).expect("PDF");
    out
}

#[tokio::test]
async fn conversations_are_mine_newest_first_with_titles() {
    let e = env().await;
    let mut c = e.db.pool.acquire().await.expect("연결");
    let mut svc = ConversationService {
        db: &mut c,
        repos: &e.repos,
    };
    let a = svc.create("LC", &e.me, None).await.expect("새 대화");
    assert_eq!(a.title, "새 대화");
    let long = "가".repeat(100);
    let b = svc
        .create("LC", &e.me, Some(&format!("  {long}  ")))
        .await
        .expect("긴 제목");
    assert_eq!(b.title.chars().count(), 80);
    assert!(matches!(
        svc.create("LO", &e.me, None).await,
        Err(Problem::NotFound { .. })
    ));
    let list = svc.list("LC", &e.me).await.expect("목록");
    assert_eq!(list.iter().map(|x| x.id).collect::<Vec<_>>(), [b.id, a.id]);
    // 턴 — seq·제목(첫 질문)·남의 대화
    let t1 = svc
        .add_turn(a.id, "  첫 질문이다  ", &[])
        .await
        .expect("턴");
    let t2 = svc.add_turn(a.id, "둘째", &[]).await.expect("턴");
    assert_eq!((t1.seq, t2.seq), (1, 2));
    let v = svc.get(a.id, &e.me).await.expect("대화");
    assert_eq!((v.title.as_str(), v.turn_count), ("첫 질문이다", 2));
    assert!(matches!(
        svc.get(a.id, &e.other).await,
        Err(Problem::NotFound { resource, .. }) if resource == "conversation"
    ));
    // 닫기 — 답·오류·둘 다 없음
    let p = vec![Progress {
        kind: "note".into(),
        text: "읽는다".into(),
    }];
    svc.finish_turn(t1.id, Some("답"), &p, &["LC-PRD-001#R1".into()], None)
        .await
        .expect("답");
    svc.finish_turn(t2.id, None, &[], &[], None)
        .await
        .expect("끊김");
    let v = svc.get(a.id, &e.me).await.expect("대화");
    assert_eq!(v.turns[0].answer.as_deref(), Some("답"));
    assert_eq!(v.turns[0].progress, p);
    assert_eq!(v.turns[0].context_item_ids, ["LC-PRD-001#R1"]);
    assert_eq!(
        (v.turns[1].answer.as_deref(), v.turns[1].error.as_deref()),
        (None, Some("답 없이 끊겼다"))
    );
    // 앞 대화 — 실패한 턴은 빠진다
    let h = svc.history(a.id, 10).await.expect("앞 대화");
    assert_eq!(h.len(), 2);
    assert!(
        matches!(&h[0], LlmMessage::Text { role: "user", text, .. } if text == "  첫 질문이다  ")
    );
    assert!(svc.history(a.id, 0).await.expect("0").is_empty());
    svc.delete(a.id, &e.me).await.expect("지우기");
    assert!(matches!(
        svc.get(a.id, &e.me).await,
        Err(Problem::NotFound { .. })
    ));
}

#[tokio::test]
async fn attachments_by_extension_with_limits_and_text() {
    let e = env().await;
    let mut c = e.db.pool.acquire().await.expect("연결");
    let mut svc = ConversationService {
        db: &mut c,
        repos: &e.repos,
    };
    let conv = svc.create("LC", &e.me, None).await.expect("대화");
    let md = svc
        .add_attachment(conv.id, &e.me, "메모.MD", "", "# 제목\n본문".as_bytes())
        .await
        .expect("md");
    assert_eq!((md.mime.as_str(), md.size), ("text/markdown", 15));
    assert_eq!(
        svc.attachment_text(conv.id, i64::from(md.id))
            .await
            .expect("글자")
            .as_deref(),
        Some("# 제목\n본문")
    );
    let png = svc
        .add_attachment(
            conv.id,
            &e.me,
            "a.png",
            "application/octet-stream",
            b"\x89PNG",
        )
        .await
        .expect("png");
    assert_eq!(png.mime, "image/png");
    assert_eq!(
        svc.attachment_text(conv.id, i64::from(png.id))
            .await
            .expect("이미지"),
        None
    );
    let two = svc
        .add_attachment(
            conv.id,
            &e.me,
            "두쪽.pdf",
            "application/pdf",
            &pdf(&["page one", "page two"]),
        )
        .await
        .expect("pdf");
    let text = svc
        .attachment_text(conv.id, i64::from(two.id))
        .await
        .expect("pdf 글자")
        .expect("있다");
    assert!(
        text.contains("page one") && text.contains("page two"),
        "{text}"
    );
    let broken = svc
        .add_attachment(conv.id, &e.me, "깨짐.pdf", "", b"%PDF-1.4 garbage")
        .await
        .expect("깨진 pdf");
    assert_eq!(
        svc.attachment_text(conv.id, i64::from(broken.id))
            .await
            .expect("깨진")
            .as_deref(),
        Some("")
    );
    // 종류 · 상한
    for (name, mime, want) in [
        ("x.exe", "", "exe"),
        ("x.md", "image/png", "image/png"),
        ("noext", "", "?"),
    ] {
        assert!(matches!(
            svc.add_attachment(conv.id, &e.me, name, mime, b"x").await,
            Err(Problem::AttachmentType { mime }) if mime == want
        ));
    }
    assert!(matches!(
        svc.add_attachment(conv.id, &e.me, "big.txt", "", &vec![b'a'; 1024 * 1024 + 1])
            .await,
        Err(Problem::AttachmentTooLarge {
            limit: 1_048_576,
            size: 1_048_577
        })
    ));
    for i in 0..4 {
        svc.add_attachment(
            conv.id,
            &e.me,
            &format!("{i}.txt"),
            "text/plain; charset=utf-8",
            b"x",
        )
        .await
        .expect("채우기");
    }
    assert!(matches!(
        svc.add_attachment(conv.id, &e.me, "9.txt", "", b"x").await,
        Err(Problem::AttachmentLimit { limit: 8 })
    ));
    // 보내면 턴의 일부 — 이 대화의 안 보낸 것만 붙는다
    let other_conv = svc.create("LC", &e.me, None).await.expect("다른 대화");
    let foreign = svc
        .add_attachment(other_conv.id, &e.me, "f.png", "", b"x")
        .await
        .expect("다른 대화 첨부");
    let turn = svc
        .add_turn(
            conv.id,
            "질문",
            &[
                i64::from(png.id),
                i64::from(md.id),
                i64::from(foreign.id),
                1 << 40,
            ],
        )
        .await
        .expect("턴");
    assert_eq!(
        svc.pending_images(turn.id).await.expect("이미지"),
        [("image/png".to_string(), b"\x89PNG".to_vec())]
    );
    assert!(matches!(
        svc.remove_attachment(png.id, &e.me).await,
        Err(Problem::AttachmentSent { .. })
    ));
    assert!(matches!(
        svc.remove_attachment(two.id, &e.other).await,
        Err(Problem::NotFound { resource, .. }) if resource == "attachment"
    ));
    svc.remove_attachment(two.id, &e.me).await.expect("빼기");
    assert_eq!(
        svc.attachment_text(other_conv.id, i64::from(md.id))
            .await
            .expect("다른 대화"),
        None
    );
    let (name, mime, bytes) = svc.attachment_bytes(md.id, &e.me).await.expect("바이트");
    assert_eq!((name.as_str(), mime.as_str()), ("메모.MD", "text/markdown"));
    assert_eq!(bytes, "# 제목\n본문".as_bytes());
    let v = svc.get(conv.id, &e.me).await.expect("대화");
    assert_eq!(v.turns[0].attachments.len(), 2);
    assert_eq!(v.pending.len(), 5); // broken + 4 txt
}
