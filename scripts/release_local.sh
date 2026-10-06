#!/usr/bin/env bash
# 싱크독_로컬(폐쇄망판) 반입물 — SYNC-INFRA-001 8.1 (카드 BC · BU). 인터넷 쪽에서 만든다.
#
#   scripts/release_local.sh {판}        예: scripts/release_local.sh 2026.10.07
#
# 결과: dist/syncdoc-local-{판}.tar.gz — 풀면 syncdoc-local-{판}/ 아래
#   images.tar.gz(docker save — 앱 syncdoc-app:{판}과 postgres:16-alpine) · docker-compose.yml ·
#   .env.example(SYNCDOC_VERSION이 이 판) · INSTALL.md · SHA256SUMS
set -euo pipefail

ver="${1:?판을 준다 — 예: scripts/release_local.sh 2026.10.07}"
if [[ ! "$ver" =~ ^[0-9A-Za-z][0-9A-Za-z._-]*$ ]]; then
  echo "판에는 영문·숫자·. _ - 만 쓴다: $ver" >&2
  exit 2
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
name="syncdoc-local-${ver}"
dist="${root}/dist"
out="${dist}/${name}"
rm -rf "$out" "${out}.tar.gz"
mkdir -p "$out"

# 싱크독_깃허브와 같은 Dockerfile — 판은 설정(EDITION=closed)이 가른다
docker build -t "syncdoc-app:${ver}" "$root"
# DB 이미지는 이 PC에 있는 것을 그대로 담는다 — 없을 때만 받는다. 매번 받으면 로컬 태그가 새 다이제스트로
# 옮겨가 같은 PC의 운영 db가 다음 compose up에 다시 만들어진다 (#262, INFRA 8.1)
docker image inspect postgres:16-alpine >/dev/null 2>&1 || docker pull postgres:16-alpine
docker save "syncdoc-app:${ver}" postgres:16-alpine | gzip > "${out}/images.tar.gz"

cp "${root}/release/local/docker-compose.yml" "${root}/release/local/INSTALL.md" "$out/"
sed "s/^SYNCDOC_VERSION=.*/SYNCDOC_VERSION=${ver}/" "${root}/release/local/.env.example" > "${out}/.env.example"
(cd "$out" && sha256sum images.tar.gz docker-compose.yml .env.example INSTALL.md > SHA256SUMS)

tar -C "$dist" -czf "${out}.tar.gz" "$name"
echo "${out}.tar.gz"
