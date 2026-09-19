#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

ARCHIVE=${1:-/home/nasser/dji-thermal-sdk-upload/dji_thermal_sdk_v1.8_20250829.zip}
EXPECTED_SHA256=E3DA978A5AC2F670CD97BE9F0E73D41DB066B8AD13E794DB36E6E560D188D793
SDK_DIR=/opt/dji-thermal-sdk
DEPLOY_DIR=/var/www/skygreenline-lab/thermal
PROJECT=thermal_inspector
SDK_BIN=utility/bin/linux/release_x64

if [[ $EUID -ne 0 ]]; then
    echo 'Run this installer through sudo.' >&2
    exit 1
fi
[[ $(uname -m) == x86_64 ]] || { echo 'The supplied DJI SDK requires an x86_64 VPS.' >&2; exit 1; }
[[ -f $ARCHIVE ]] || { echo "SDK archive is missing: $ARCHIVE" >&2; exit 1; }
[[ -d $DEPLOY_DIR/.git ]] || { echo "Thermal deployment is missing: $DEPLOY_DIR" >&2; exit 1; }

echo '[1/6] Verifying the private DJI SDK archive and application baseline'
actual_sha=$(sha256sum "$ARCHIVE" | awk '{print toupper($1)}')
[[ $actual_sha == $EXPECTED_SHA256 ]] || {
    echo "SDK checksum mismatch: $actual_sha" >&2
    exit 1
}
curl --fail --silent --output /dev/null https://skygreenline-lab.io/
curl --fail --silent --output /dev/null https://skygreenline-lab.io/api/health
curl --fail --silent --output /dev/null http://127.0.0.1:8003/api/health

echo '[2/6] Extracting to a protected staging directory'
stage=$(mktemp -d /opt/.dji-thermal-sdk.XXXXXX)
backup=''
installed=0
cleanup() {
    code=$?
    rm -rf -- "$stage"
    if [[ $code -ne 0 && $installed -eq 1 && -d $SDK_DIR ]]; then
        failed="${SDK_DIR}.failed-$(date -u +%Y%m%dT%H%M%SZ)"
        mv -- "$SDK_DIR" "$failed"
        [[ -z $backup || ! -d $backup ]] || mv -- "$backup" "$SDK_DIR"
        echo "Installation failed; candidate SDK retained at $failed" >&2
    fi
    exit "$code"
}
trap cleanup EXIT
python3 - "$ARCHIVE" "$stage" <<'PY'
from pathlib import Path, PurePosixPath
from zipfile import ZipFile
import sys

archive, target = Path(sys.argv[1]), Path(sys.argv[2])
with ZipFile(archive) as bundle:
    for member in bundle.infolist():
        path = PurePosixPath(member.filename)
        if path.is_absolute() or '..' in path.parts:
            raise SystemExit(f'Unsafe archive path: {member.filename}')
        # Reject symbolic links. The official package contains regular files only.
        if (member.external_attr >> 16) & 0o170000 == 0o120000:
            raise SystemExit(f'Unexpected symbolic link: {member.filename}')
    bundle.extractall(target)
PY

chmod 0755 "$stage/$SDK_BIN/dji_irp" "$stage/$SDK_BIN/dji_irp_omp" "$stage/$SDK_BIN/dji_ircm"
find "$stage" -type d -exec chmod 0755 {} +
find "$stage" -type f ! -path "*/$SDK_BIN/dji_irp" ! -path "*/$SDK_BIN/dji_irp_omp" ! -path "*/$SDK_BIN/dji_ircm" -exec chmod 0644 {} +
chown -R root:root "$stage"

echo '[3/6] Validating the Linux decoder against DJI M4T radiometric data'
lib_dir="$stage/$SDK_BIN"
decoder="$lib_dir/dji_irp"
sample="$stage/dataset/M4T/DJI_0001_R.JPG"
[[ -x $decoder && -f $sample ]] || { echo 'Required decoder or M4T sample is absent.' >&2; exit 1; }
file "$decoder" | grep -q 'ELF 64-bit.*x86-64' || { echo 'Unexpected decoder architecture.' >&2; exit 1; }
if LD_LIBRARY_PATH="$lib_dir" ldd "$decoder" | grep -q 'not found'; then
    echo 'The DJI decoder has unresolved shared-library dependencies.' >&2
    LD_LIBRARY_PATH="$lib_dir" ldd "$decoder" >&2
    exit 1
fi
test_dir=$(mktemp -d /tmp/dji-sdk-test.XXXXXX)
LD_LIBRARY_PATH="$lib_dir" "$decoder" -s "$sample" -a measure -o "$test_dir/measure.raw" --measurefmt float32 >"$test_dir/output.log" 2>&1
[[ -s $test_dir/measure.raw ]] || { cat "$test_dir/output.log" >&2; echo 'DJI sample decode produced no measurements.' >&2; exit 1; }
python3 - "$test_dir/measure.raw" "$test_dir/output.log" <<'PY'
from pathlib import Path
import re, struct, sys

raw, log = Path(sys.argv[1]), Path(sys.argv[2]).read_text(errors='replace')
match = re.search(r'image\s+width\s*:\s*(\d+).*?image height\s*:\s*(\d+)', log, re.S)
if not match:
    raise SystemExit('DJI decoder did not report dimensions')
width, height = map(int, match.groups())
if raw.stat().st_size != width * height * 4:
    raise SystemExit('DJI float32 output size does not match its dimensions')
values = struct.unpack(f'<{width * height}f', raw.read_bytes())
finite = [value for value in values if value == value and abs(value) != float('inf')]
if not finite:
    raise SystemExit('DJI sample contains no finite temperature values')
print(f'Validated DJI M4T sample: {width}x{height}, {min(finite):.2f}C to {max(finite):.2f}C')
PY
rm -rf -- "$test_dir"

echo '[4/6] Installing the SDK outside the Git checkout'
if [[ -e $SDK_DIR ]]; then
    backup="${SDK_DIR}.backup-$(date -u +%Y%m%dT%H%M%SZ)"
    mv -- "$SDK_DIR" "$backup"
fi
mv -- "$stage" "$SDK_DIR"
installed=1

python3 - "$DEPLOY_DIR/.env" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = path.read_text(encoding='utf-8').splitlines()
key = 'DJI_SDK_VERSION='
replacement = 'DJI_SDK_VERSION=1.8'
lines = [replacement if line.startswith(key) else line for line in lines]
if not any(line.startswith(key) for line in lines):
    lines.append(replacement)
path.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
PY
chown nasser:nasser "$DEPLOY_DIR/.env"
chmod 0600 "$DEPLOY_DIR/.env"

echo '[5/6] Enabling the read-only SDK mount for the thermal API'
cd "$DEPLOY_DIR"
compose=(docker compose -p "$PROJECT" -f docker-compose.prod.yml -f docker-compose.sdk.yml)
"${compose[@]}" up -d --no-deps api
for attempt in $(seq 1 40); do
    health=$(curl --fail --silent http://127.0.0.1:8003/api/health 2>/dev/null || true)
    if python3 -c 'import json,sys; data=json.load(sys.stdin); raise SystemExit(not (data.get("status")=="ok" and data.get("decoder_available") is True and data.get("sdk_version")=="1.8"))' <<<"$health" 2>/dev/null; then
        break
    fi
    sleep 2
done
health=$(curl --fail --silent http://127.0.0.1:8003/api/health)
python3 -c 'import json,sys; data=json.load(sys.stdin); assert data["decoder_available"] is True and data["sdk_version"] == "1.8"' <<<"$health"

echo '[6/6] Verifying isolation and both applications'
docker inspect thermal_inspector-api-1 --format '{{range .Mounts}}{{if eq .Destination "/opt/dji-thermal-sdk"}}{{.Source}}|{{.RW}}{{end}}{{end}}' | grep -qx '/opt/dji-thermal-sdk|false'
curl --fail --silent --output /dev/null http://127.0.0.1:5174/thermal/
curl --fail --silent --output /dev/null https://skygreenline-lab.io/
curl --fail --silent --output /dev/null https://skygreenline-lab.io/api/health
[[ $(curl --silent --output /dev/null --write-out '%{http_code}' https://skygreenline-lab.io/thermal/) == 401 ]]
rm -f -- "$ARCHIVE"
trap - EXIT

echo "DJI Thermal SDK 1.8 is active: $health"
[[ -z $backup ]] || echo "Previous SDK backup: $backup"
