# Production deployment

Deploy this application to `/var/www/skygreenline-lab/thermal` with Docker Compose project `thermal_inspector`. The root website and its `/api/` remain with the existing Nginx locations. Thermal UI and API use `/thermal/` and `/thermal/api/`.

Use `docker-compose.prod.yml`; `docker-compose.yml` remains a local development example. Run `python3 deploy/create-production-env.py` once on the VPS to create a mode 600 `.env` with unique MySQL passwords, a URL-encoded matching `DATABASE_URL`, and `CORS_ORIGINS=https://skygreenline-lab.io`. The command refuses to overwrite an existing `.env` and never prints the secrets. Never commit `.env`. All published Compose ports bind to loopback. Install `deploy/nginx-thermal.conf` as a snippet in the existing HTTPS server block after backing up that server file. The snippet protects both thermal routes with Basic Authentication; `/api/` and `location /` stay with the existing site.

The official Linux x64 DJI SDK must be provided separately under `/opt/dji-thermal-sdk`. Once `utility/bin/linux/release_x64/dji_irp` is executable, set `DJI_SDK_VERSION` in `.env` to its verified version and add `-f docker-compose.sdk.yml` to Compose commands to mount it read-only. Without that file, `/thermal/api/health` truthfully reports `decoder_available: false`; temperature measurement is unavailable. Ordinary image previews are not radiometric measurements.

After initial setup, run `bash scripts/deploy-production.sh` from the deployment directory for updates. It records the previous commit, backs up `.env` and the database, fetches and fast-forwards `main`, builds the app, applies Alembic, restarts, and checks internal health. It preserves Docker volumes. If health fails, it restores the previous application commit and containers; review database migrations before any database restore.

Useful commands (add `-f docker-compose.sdk.yml` if SDK installed):

```bash
docker compose -p thermal_inspector -f docker-compose.prod.yml ps
docker compose -p thermal_inspector -f docker-compose.prod.yml logs --tail=100 api
docker compose -p thermal_inspector -f docker-compose.prod.yml restart api web
docker compose -p thermal_inspector -f docker-compose.prod.yml exec api alembic current
```
