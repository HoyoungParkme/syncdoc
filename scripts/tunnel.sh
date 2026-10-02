#!/usr/bin/env bash
# 켤 때마다 하는 일 — SYNC-INFRA-001 5장 공개 경로.
#
#   1) docker compose up -d --build   앱·DB 기동 (마이그레이션은 컨테이너가 돌린다)
#   2) 터널 — .env 의 TUNNEL_TOKEN 이 있으면 Named Tunnel (고정 주소 PUBLIC_BASE_URL).
#              터널은 compose 서비스 — docker-compose.override.yml(git에 안 올림)을 만들어 두면
#              그 뒤로는 Docker가 뜰 때 app·db와 같이 뜬다. 재부팅해도 할 일이 없다 (#284)
#              없으면 Quick Tunnel (호스트 cloudflared tunnel --url … → https://xxx.trycloudflare.com)
#   3) Quick 이면 새 주소를 .env 의 PUBLIC_BASE_URL 에 넣고 app 재시작. Named 는 안 건드린다
#   4) Quick 이면 OAuth 앱 callback URL 을 사람이 브라우저에서 고친다 (아래 순서를 출력한다)
#
# 사용: scripts/tunnel.sh          기동 + 터널
#       scripts/tunnel.sh --stop   터널 종료
set -euo pipefail
cd "$(dirname "$0")/.."

LOG=/tmp/syncdoc-cloudflared.log
PIDF=/tmp/syncdoc-cloudflared.pid

OVR=docker-compose.override.yml

stop() {
  # 예전(호스트 nohup) 터널과 compose 터널 서비스 둘 다
  [ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null && echo "호스트 터널 종료" || echo "돌고 있는 호스트 터널 없음"
  rm -f "$PIDF"
  [ -f "$OVR" ] && docker compose stop tunnel >/dev/null 2>&1 && echo "터널 컨테이너 멈춤" || true
}
[ "${1:-}" = "--stop" ] && { stop; exit 0; }

# .env 에서 두 값만 읽는다 — source 하면 다른 값이 셸에 퍼진다
TUNNEL_TOKEN=$(sed -n 's/^TUNNEL_TOKEN=//p' .env | tail -1)
PUBLIC_BASE_URL=$(sed -n 's/^PUBLIC_BASE_URL=//p' .env | tail -1)

# 호스트 cloudflared는 Quick Tunnel만 쓴다 — Named는 컨테이너 이미지가 있다
if [ -z "$TUNNEL_TOKEN" ]; then
  export PATH="$HOME/.local/bin:$PATH"   # sudo 없이 넣은 cloudflared
  command -v cloudflared >/dev/null || {
    echo "cloudflared 가 없습니다. 설치(권한 불필요):" >&2
    echo "  mkdir -p ~/.local/bin" >&2
    echo "  curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o ~/.local/bin/cloudflared" >&2
    echo "  chmod 755 ~/.local/bin/cloudflared" >&2
    exit 1
  }
fi

# 예전 호스트 터널은 끈다 — 터널은 이제 compose 서비스다 (#284)
[ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null || true
rm -f "$PIDF"
if [ -n "$TUNNEL_TOKEN" ]; then
  [ -n "$PUBLIC_BASE_URL" ] || { echo "TUNNEL_TOKEN 이 있으면 PUBLIC_BASE_URL(고정 호스트)도 .env 에 있어야 합니다" >&2; exit 1; }
  # 토큰은 파일에 안 적는다 — compose가 .env 에서 ${TUNNEL_TOKEN} 을 채운다.
  # app과 네트워크를 같이 쓴다 — 대시보드의 대상 http://localhost:8000 이 곧 app 이다
  cat > "$OVR" <<'YML'
# scripts/tunnel.sh가 만든다 — .env 에 TUNNEL_TOKEN 이 있을 때만 (INFRA-001 5장, #284). git에 안 올린다
services:
  tunnel:
    image: cloudflare/cloudflared:2026.8.3
    command: tunnel --no-autoupdate run
    environment:
      TUNNEL_TOKEN: ${TUNNEL_TOKEN}
    network_mode: "service:app"
    depends_on: [app]
    restart: unless-stopped
YML
else
  rm -f "$OVR"   # 토큰이 없으면 터널 서비스도 없다 — Quick Tunnel은 아래에서 호스트로
fi

echo "[1/4] docker compose up"  # 빌드 컨텍스트는 저장소 루트 (backend·frontend·docs)
docker compose up -d --build
for _ in $(seq 1 60); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health || true)" = "200" ] && break
  sleep 2
done
curl -sf http://localhost:8000/health >/dev/null || { echo "앱이 뜨지 않았습니다: docker compose logs app" >&2; exit 1; }

: > "$LOG"
if [ -n "$TUNNEL_TOKEN" ]; then
  # Named Tunnel — 주소는 Cloudflare 대시보드에서 호스트를 이 터널에 이어 둔 것. 재부팅해도 같다
  echo "[2/4] cloudflared named tunnel(컨테이너) → $PUBLIC_BASE_URL"
  for _ in $(seq 1 60); do
    docker compose logs tunnel 2>/dev/null | grep -q "Registered tunnel connection" && break
    sleep 1
  done
  docker compose logs tunnel 2>/dev/null | grep -q "Registered tunnel connection" \
    || { echo "터널이 안 붙었습니다: docker compose logs tunnel" >&2; exit 1; }
  echo "[3/4] .env 그대로 (고정 주소)"
  echo "[4/4] 할 일 없음 — OAuth 콜백·MCP 등록은 처음 한 번만. 재부팅해도 터널이 저절로 뜬다"
  echo
  echo "  공개 주소: $PUBLIC_BASE_URL   (health: $(curl -s -m 10 "$PUBLIC_BASE_URL/health" || echo '아직 응답 없음 — 몇 초 뒤 다시'))"
  echo "  터널 종료: scripts/tunnel.sh --stop"
  exit 0
fi

echo "[2/4] cloudflared quick tunnel (TUNNEL_TOKEN 없음 — 주소가 매번 바뀐다. 고정하려면 INFRA-001 5장)"
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
