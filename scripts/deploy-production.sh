#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

DEPLOY_DIR=/var/www/skygreenline-lab/thermal
PROJECT=thermal_inspector
cd "$DEPLOY_DIR"
[[ "$(pwd -P)" == "$DEPLOY_DIR" ]] || { echo 'Unexpected deployment directory' >&2; exit 1; }
[[ -f .env && -f docker-compose.prod.yml ]] || { echo 'Production files are missing' >&2; exit 1; }
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo 'Tracked working tree is not clean' >&2; exit 1; }
[[ "$(git branch --show-current)" == main ]] || { echo 'Expected main branch' >&2; exit 1; }
curl --fail --silent --output /dev/null https://skygreenline-lab.io/
curl --fail --silent --output /dev/null https://skygreenline-lab.io/api/health

old_commit=$(git rev-parse HEAD)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="$DEPLOY_DIR/backups/$stamp"
mkdir -p "$backup_dir"
chmod 700 "$DEPLOY_DIR/backups" "$backup_dir"
printf '%s\n' "$old_commit" > "$backup_dir/previous-commit.txt"
cp -p .env "$backup_dir/.env"
cp -p docker-compose.prod.yml "$backup_dir/docker-compose.prod.yml"

compose=(-f docker-compose.prod.yml)
if [[ -x /opt/dji-thermal-sdk/utility/bin/linux/release_x64/dji_irp ]]; then
    if grep -qx 'DJI_SDK_VERSION=unavailable' .env; then
        echo 'Set DJI_SDK_VERSION to the verified installed SDK version before enabling it' >&2
        exit 1
    fi
    compose+=(-f docker-compose.sdk.yml)
fi
dc() { docker compose -p "$PROJECT" "${compose[@]}" "$@"; }

# Start an existing database volume so every update has a fresh logical backup.
if docker volume inspect "${PROJECT}_mysql_data" >/dev/null 2>&1; then
    dc up -d db
    dc exec -T db sh -c 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mysqldump -u root --single-transaction --routines --triggers --databases "$MYSQL_DATABASE"' | gzip -9 > "$backup_dir/database.sql.gz"
    test -s "$backup_dir/database.sql.gz"
fi

updated=0
rollback() {
    code=$?
    if [[ $code -ne 0 && $updated -eq 1 ]]; then
        echo "Deployment failed; restoring application commit $old_commit" >&2
        git reset --hard "$old_commit"
        dc build api web
        dc up -d --no-deps api web || true
        echo "Database backup: $backup_dir/database.sql.gz (if present). Review migration compatibility before restoring data." >&2
    fi
    exit "$code"
}
trap rollback EXIT

git fetch origin main
git merge --ff-only origin/main
updated=1
dc build api web
dc up -d db
dc run --rm --no-deps api alembic upgrade head
dc up -d api web
for attempt in $(seq 1 30); do
    if curl --fail --silent --output /dev/null http://127.0.0.1:8003/api/health \
       && curl --fail --silent --output /dev/null http://127.0.0.1:5174/thermal/; then
        break
    fi
    sleep 2
done
curl --fail --silent --output /dev/null http://127.0.0.1:8003/api/health
curl --fail --silent --output /dev/null http://127.0.0.1:5174/thermal/
curl --fail --silent --output /dev/null https://skygreenline-lab.io/
curl --fail --silent --output /dev/null https://skygreenline-lab.io/api/health
echo "Deployed $(git rev-parse HEAD); backup in $backup_dir"
trap - EXIT
