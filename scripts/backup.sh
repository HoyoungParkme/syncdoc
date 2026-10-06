#!/usr/bin/env bash
# 정기 백업 — SYNC-INFRA-001 6.1 (카드 BR). 노트북이 유일한 사본이라(서버 저장) 하루 한 번 밖에 둔다.
#
#   1) DB 덤프(pg_dump -Fc)와 볼륨 origins(서버 저장소)를 컨테이너에서 받아 한 묶음으로
#   2) gpg 대칭 암호화(AES256) — 암호 파일은 사람이 만든다. 없으면 이유를 남기고 끝
#   3) BACKUP_DIR(기본 구글 드라이브 내 드라이브/syncdoc-backup)에 두고, 최근 BACKUP_KEEP개만 남긴다
#   오늘 것이 이미 있으면 건너뛴다 — crontab이 매시 불러도 하루 한 번이다
#
# 사용: scripts/backup.sh                 백업(오늘 것이 있으면 건너뜀)
#       scripts/backup.sh --verify 파일   풀어서 덤프·서버 저장소 목록을 보인다
# 설정: ~/.config/syncdoc/backup.env (비밀 아님) — BACKUP_DIR · BACKUP_KEEP · BACKUP_PASS_FILE
set -euo pipefail
cd "$(dirname "$0")/.."

CONF="${SYNCDOC_BACKUP_CONF:-$HOME/.config/syncdoc/backup.env}"
[ -f "$CONF" ] && . "$CONF"
BACKUP_DIR="${BACKUP_DIR:-/mnt/g/내 드라이브/syncdoc-backup}"
BACKUP_KEEP="${BACKUP_KEEP:-14}"
BACKUP_PASS_FILE="${BACKUP_PASS_FILE:-$HOME/.config/syncdoc/backup.pass}"

say() { echo "$(date '+%F %T') $*"; }

if [ ! -s "$BACKUP_PASS_FILE" ]; then
  say "건너뜀: 암호 파일이 없다 — $BACKUP_PASS_FILE (권한 600으로 만들고 노트북 밖에도 보관한다)"
  exit 3
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

decrypt() { gpg --batch --quiet --pinentry-mode loopback --passphrase-file "$BACKUP_PASS_FILE" -d "$1"; }

if [ "${1:-}" = "--verify" ]; then
  decrypt "$2" | tar -x -C "$tmp"
  say "덤프 항목 $(docker compose exec -T db pg_restore --list < "$tmp/db.dump" | grep -c 'TABLE DATA') 표"
  say "서버 저장소: $(tar -tf "$tmp/origins.tar" | grep -oE '^origins/[^/]+\.git/$' | sed 's#origins/##; s#\.git/##' | tr '\n' ' ')"
  exit 0
fi

if [ ! -d "$(dirname "$BACKUP_DIR")" ]; then
  say "건너뜀: 백업 자리의 상위 폴더가 없다 — $(dirname "$BACKUP_DIR") (드라이브가 연결됐나)"
  exit 4
fi
mkdir -p "$BACKUP_DIR"
today="$(date +%Y%m%d)"
if compgen -G "$BACKUP_DIR/syncdoc-$today-*.tar.gpg" > /dev/null; then
  say "건너뜀: 오늘 것이 있다"
  exit 0
fi

# compose 밖에서 컨테이너로 — 덤프는 DB 컨테이너의 pg_dump, 원본은 앱 컨테이너의 tar
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$tmp/db.dump"
docker compose exec -T app tar -C /var/syncdoc -cf - origins > "$tmp/origins.tar"
name="syncdoc-$today-$(date +%H%M%S).tar.gpg"
tar -C "$tmp" -cf - db.dump origins.tar \
  | gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-file "$BACKUP_PASS_FILE" \
      --symmetric --cipher-algo AES256 -o "$tmp/$name"
cp "$tmp/$name" "$BACKUP_DIR/$name.part" && mv "$BACKUP_DIR/$name.part" "$BACKUP_DIR/$name"

# 최근 BACKUP_KEEP개만 — 이름에 날짜·시각이 있어 정렬이 곧 시간순이다
ls -1 "$BACKUP_DIR"/syncdoc-*.tar.gpg | sort | head -n "-$BACKUP_KEEP" | while read -r old; do rm -f "$old"; done
say "백업 $name ($(du -h "$BACKUP_DIR/$name" | cut -f1)) → $BACKUP_DIR"
