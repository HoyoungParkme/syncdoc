#!/usr/bin/env bash
# 켤 때마다 하는 일 — SYNC-INFRA-001 5장 Quick Tunnel (도메인 없음, 주소 가변).
#
#   1) docker compose up -d --build   앱·DB 기동 (마이그레이션은 컨테이너가 돌린다)
#   2) cloudflared tunnel --url http://localhost:8000  → https://xxx.trycloudflare.com
#   3) 주소를 .env 의 PUBLIC_BASE_URL 에 넣고 app 재시작
#   4) OAuth 앱 callback URL 을 사람이 브라우저에서 고친다 (아래 순서를 출력한다)
#
# 사용: scripts/tunnel.sh          기동 + 터널
#       scripts/tunnel.sh --stop   터널 종료
set -euo pipefail
cd "$(dirname "$0")/.."

LOG=/tmp/syncdoc-cloudflared.log
PIDF=/tmp/syncdoc-cloudflared.pid

stop() {
  [ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null && echo "터널 종료" || echo "돌고 있는 터널 없음"
  rm -f "$PIDF"
}
[ "${1:-}" = "--stop" ] && { stop; exit 0; }

export PATH="$HOME/.local/bin:$PATH"   # sudo 없이 넣은 cloudflared
command -v cloudflared >/dev/null || {
  echo "cloudflared 가 없습니다. 설치(권한 불필요):" >&2
  echo "  mkdir -p ~/.local/bin" >&2
  echo "  curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o ~/.local/bin/cloudflared" >&2
  echo "  chmod 755 ~/.local/bin/cloudflared" >&2
  exit 1
}

echo "[1/4] docker compose up"
docker compose up -d --build
for _ in $(seq 1 60); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health || true)" = "200" ] && break
  sleep 2
done
curl -sf http://localhost:8000/health >/dev/null || { echo "앱이 뜨지 않았습니다: docker compose logs app" >&2; exit 1; }

echo "[2/4] cloudflared quick tunnel"
stop >/dev/null 2>&1 || true
: > "$LOG"
nohup cloudflared tunnel --url http://localhost:8000 --no-autoupdate >"$LOG" 2>&1 &
echo $! > "$PIDF"
URL=""
for _ in $(seq 1 60); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
[ -n "$URL" ] || { echo "터널 주소를 못 얻었습니다. 로그: $LOG" >&2; stop; exit 1; }

echo "[3/4] .env PUBLIC_BASE_URL=$URL"
if grep -q '^PUBLIC_BASE_URL=' .env; then
  sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=$URL|" .env
else
  printf '\nPUBLIC_BASE_URL=%s\n' "$URL" >> .env
fi
docker compose up -d app >/dev/null   # env_file 을 다시 읽는다

echo "[4/4] 사람이 할 일 — OAuth 앱 callback 고치기 (3분)"
cat <<EOF

  공개 주소: $URL

  1. https://github.com/settings/developers → OAuth Apps → 공개용 앱 (없으면 New OAuth App)
  2. Homepage URL:            $URL
     Authorization callback:  $URL/auth/github/callback
     (Expire user access tokens 는 끈 채로 — MS-006 미결)
  3. Update application
  4. 앱을 새로 만들었으면 Client ID·Secret 을 .env 의 GITHUB_CLIENT_ID·GITHUB_CLIENT_SECRET 에 넣고
     docker compose up -d app 로 다시 읽힌다
  5. 브라우저에서 $URL 접속 → GitHub 로그인

  webhook 은 걸지 않는다 (주소가 매번 바뀐다). 외부 push 는 5분 폴링이 가져온다.
  터널 종료: scripts/tunnel.sh --stop

EOF
