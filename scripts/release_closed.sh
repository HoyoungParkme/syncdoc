#!/usr/bin/env bash
# 폐쇄망판 반입물 — SYNC-INFRA-001 8.1 (카드 BC). 인터넷 쪽에서 만든다.
#
#   scripts/release_closed.sh {판}        예: scripts/release_closed.sh 2026.09.30
#
# 결과: dist/syncdoc-closed-{판}.tar.gz — 풀면 syncdoc-closed-{판}/ 아래
#   images.tar.gz(docker save — 앱 syncdoc-app:{판}과 postgres:16-alpine) · docker-compose.yml ·
#   .env.example(SYNCDOC_VERSION이 이 판) · INSTALL.md · SHA256SUMS
set -euo pipefail

ver="${1:?판을 준다 — 예: scripts/release_closed.sh 2026.09.30}"
if [[ ! "$ver" =~ ^[0-9A-Za-z][0-9A-Za-z._-]*$ ]]; then
  echo "판에는 영문·숫자·. _ - 만 쓴다: $ver" >&2
  exit 2
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
name="syncdoc-closed-${ver}"
dist="${root}/dist"
out="${dist}/${name}"
rm -rf "$out" "${out}.tar.gz"
mkdir -p "$out"

# 인터넷판과 같은 Dockerfile — 판은 설정(EDITION=closed)이 가른다
docker build -t "syncdoc-app:${ver}" "$root"
docker pull postgres:16-alpine
docker save "syncdoc-app:${ver}" postgres:16-alpine | gzip > "${out}/images.tar.gz"

cp "${root}/release/closed/docker-compose.yml" "${root}/release/closed/INSTALL.md" "$out/"
sed "s/^SYNCDOC_VERSION=.*/SYNCDOC_VERSION=${ver}/" "${root}/release/closed/.env.example" > "${out}/.env.example"
(cd "$out" && sha256sum images.tar.gz docker-compose.yml .env.example INSTALL.md > SHA256SUMS)

tar -C "$dist" -czf "${out}.tar.gz" "$name"
echo "${out}.tar.gz"
