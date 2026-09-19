#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

DEPLOY_DIR=/var/www/skygreenline-lab/thermal
PARENT_DIR=/var/www/skygreenline-lab
REPOSITORY=https://github.com/Tabook22/thermal_img.git
PROJECT=thermal_inspector
SITE_FILE=/etc/nginx/sites-available/insulator-inspector
SNIPPET_FILE=/etc/nginx/snippets/thermal-inspector.conf
AUTH_FILE=/etc/nginx/.thermal_htpasswd

if [[ $EUID -ne 0 ]]; then
    echo "Run this script through sudo." >&2
    exit 1
fi

existing_root=$(curl --fail --silent --output /dev/null --write-out '%{http_code}' https://skygreenline-lab.io/)
existing_api=$(curl --fail --silent --output /dev/null --write-out '%{http_code}' https://skygreenline-lab.io/api/health)
[[ "$existing_root" == 200 && "$existing_api" == 200 ]] || {
    echo "Existing application baseline is unhealthy; no changes made." >&2
    exit 1
}
[[ -f "$SITE_FILE" ]] || { echo "Expected Nginx site file is missing: $SITE_FILE" >&2; exit 1; }
ss -ltn | grep -qE '127\.0\.0\.1:8003[[:space:]]' && { echo 'Port 8003 is already used.' >&2; exit 1; }
ss -ltn | grep -qE '127\.0\.0\.1:5174[[:space:]]' && { echo 'Port 5174 is already used.' >&2; exit 1; }

echo '[1/8] Installing Docker Compose and Basic Authentication utilities'
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2 apache2-utils git curl
systemctl enable --now docker
usermod -aG docker nasser

echo '[2/8] Preparing the isolated deployment directory'
install -d -o nasser -g nasser -m 0750 "$PARENT_DIR"
if [[ -e "$DEPLOY_DIR" ]]; then
    [[ -d "$DEPLOY_DIR/.git" ]] || { echo "$DEPLOY_DIR exists but is not a Git checkout; stopping." >&2; exit 1; }
    [[ -z "$(sudo -u nasser git -C "$DEPLOY_DIR" status --porcelain)" ]] || { echo 'Deployment checkout has local changes; stopping.' >&2; exit 1; }
    sudo -u nasser git -C "$DEPLOY_DIR" fetch origin main
    sudo -u nasser git -C "$DEPLOY_DIR" checkout main
    sudo -u nasser git -C "$DEPLOY_DIR" merge --ff-only origin/main
else
    sudo -u nasser git clone --branch main --single-branch "$REPOSITORY" "$DEPLOY_DIR"
fi
cd "$DEPLOY_DIR"

echo '[3/8] Creating protected production secrets'
if [[ ! -f .env ]]; then
    sudo -u nasser python3 deploy/create-production-env.py
fi
chown nasser:nasser .env
chmod 600 .env

echo '[4/8] Creating temporary web access protection'
if [[ -f "$AUTH_FILE" ]]; then
    echo 'Preserving the existing protected website login file.'
else
    read -r -p 'Temporary /thermal/ username [nasser]: ' auth_user
    auth_user=${auth_user:-nasser}
    [[ "$auth_user" =~ ^[A-Za-z0-9._-]{1,64}$ ]] || { echo 'Invalid username.' >&2; exit 1; }
    echo 'Enter the temporary website password twice. It will not be displayed.'
    htpasswd -c "$AUTH_FILE" "$auth_user"
fi
chown root:www-data "$AUTH_FILE"
chmod 640 "$AUTH_FILE"

echo '[5/8] Building the application and applying database migrations'
compose=(docker compose -p "$PROJECT" -f docker-compose.prod.yml)
if [[ -x /opt/dji-thermal-sdk/utility/bin/linux/release_x64/dji_irp ]]; then
    if grep -qx 'DJI_SDK_VERSION=unavailable' .env; then
        echo 'A DJI executable exists but its version is unverified; decoder remains disabled.'
    else
        compose+=(-f docker-compose.sdk.yml)
    fi
fi
"${compose[@]}" build api web
"${compose[@]}" up -d db
"${compose[@]}" run --rm --no-deps api alembic upgrade head
"${compose[@]}" up -d api web

for attempt in $(seq 1 45); do
    if curl --fail --silent --output /dev/null http://127.0.0.1:8003/api/health \
       && curl --fail --silent --output /dev/null http://127.0.0.1:5174/thermal/; then
        break
    fi
    sleep 2
done
curl --fail --silent http://127.0.0.1:8003/api/health > /tmp/thermal-health.json
curl --fail --silent --output /dev/null http://127.0.0.1:5174/thermal/

echo '[6/8] Backing up and extending the existing Nginx site'
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="${SITE_FILE}.backup-${stamp}"
cp -a "$SITE_FILE" "$backup"
install -o root -g root -m 0644 deploy/nginx-thermal.conf "$SNIPPET_FILE"
python3 - "$SITE_FILE" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
include = "    include /etc/nginx/snippets/thermal-inspector.conf;\n"
if include not in text:
    match = re.search(r"(?m)^(\s*server_name\s+[^;]*skygreenline-lab\.io[^;]*;\s*\n)", text)
    if not match:
        raise SystemExit("Could not locate the existing HTTPS server_name directive")
    text = text[:match.end()] + "\n" + include + text[match.end():]
    path.write_text(text, encoding="utf-8", newline="\n")
PY
if ! nginx -t; then
    cp -a "$backup" "$SITE_FILE"
    nginx -t
    echo 'Nginx validation failed; original configuration restored.' >&2
    exit 1
fi
systemctl reload nginx

echo '[7/8] Verifying existing and thermal applications'
[[ "$(curl --fail --silent --output /dev/null --write-out '%{http_code}' https://skygreenline-lab.io/)" == 200 ]]
[[ "$(curl --fail --silent --output /dev/null --write-out '%{http_code}' https://skygreenline-lab.io/api/health)" == 200 ]]
[[ "$(curl --silent --output /dev/null --write-out '%{http_code}' https://skygreenline-lab.io/thermal/)" == 401 ]]
[[ "$(curl --silent --output /dev/null --write-out '%{http_code}' https://skygreenline-lab.io/thermal/api/health)" == 401 ]]
"${compose[@]}" ps

echo '[8/8] Deployment complete'
echo "Commit: $(git rev-parse HEAD)"
echo "Nginx backup: $backup"
echo "Internal health: $(cat /tmp/thermal-health.json)"
echo 'Sign out and reconnect once before running Docker as nasser; group membership was added.'
