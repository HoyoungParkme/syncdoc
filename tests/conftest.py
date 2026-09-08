"""테스트 공통. 테스트 DB는 SYNCDOC_TEST_DATABASE_URL (없으면 로컬 5434 컨테이너)."""

import os

os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "SYNCDOC_TEST_DATABASE_URL",
        "postgresql+psycopg://syncdoc:syncdoc@localhost:5434/syncdoc_test",
    ),
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")
