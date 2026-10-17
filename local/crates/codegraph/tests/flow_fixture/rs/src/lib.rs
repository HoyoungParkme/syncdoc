use axum::{routing::get, Router};
use reqwest::Client;
use sqlx::PgPool;

pub fn app() -> Router {
    Router::new().route("/api/x", get(list).post(make))
}

async fn list(pool: &PgPool) {
    sqlx::query("select 1").fetch_one(pool).await;
}

async fn make() {
    let c = Client::new();
    c.get("u").send().await;
    let f = |y| helper(y);
    helper(1);
}

fn helper(x: i32) -> i32 {
    return x;
}

#[get("/hi/")]
async fn hi() {}
