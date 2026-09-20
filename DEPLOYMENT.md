# Deployment Guide

```
benconnect.de, www.benconnect.de
    -> Render (single Docker service: gunicorn/Flask)
        - serves the static frontend (flutter_app/docs)
        - serves the JSON API
        - talks to MongoDB Atlas (app data)
```

One Render web service builds the `Dockerfile` and serves everything: `app.py`
sets `static_folder` to `flutter_app/docs` and has routes (`/`, `/dashboard`,
`/settings`, `/chat`, `/setup`, `/admin`, `/einladung/...`) that hand back the
matching HTML file, so the same Flask/gunicorn process is both the site and
the API. There is no separate frontend host, no CORS, and no cross-subdomain
cookie dance — everything is same-origin.

The app itself is stateless (all data lives in MongoDB Atlas), so the service
runs with no persistent disk.

## Database: MongoDB Atlas

1. Create a free (M0) cluster at https://cloud.mongodb.com.
2. **Database Access** → add a user + password.
3. **Network Access** → allow `0.0.0.0/0` (Render egress IPs vary; use a strong
   password), or add Render's static outbound IPs if you pin them.
4. **Connect → Drivers → Python** → copy the URI (`mongodb+srv://…`).
  The application enforces TLS for non-local MongoDB connections; do not use
  an unencrypted `mongodb://` URI in Render.
5. One-time data import from the old SQLite DB:
   ```bash
   MONGODB_URI="mongodb+srv://…" MONGODB_DB=grouply \
       python migrate_sqlite_to_mongo.py users.db
   ```
   Remaps integer ids to ObjectIds and rewrites all foreign keys. Refuses to run
   over non-empty collections unless you pass `--force`.

Indexes are created automatically on app startup (`init_db()` → `ensure_indexes()`).

## App + site: Render

Render builds the existing `Dockerfile` (gunicorn on `$PORT`). Config is in
`render.yaml`; secrets are set in the Render dashboard (never in the repo).

Environment variables (Render → service → Environment):
- `MONGODB_URI` — the Atlas connection string  ⚠️ required
- `MONGODB_REQUIRED=1` — prevents the insecure in-memory fallback in production
- `MONGODB_DB` — `grouply` (already defaulted in render.yaml)
- `FLASK_SECRET_KEY` — Render can generate it (render.yaml `generateValue`)
- `SESSION_COOKIE_SECURE=1` — Secure cookies over HTTPS (already in render.yaml)
- `OPENAI_API_KEY`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`

`SESSION_COOKIE_DOMAIN` / `FLASK_ALLOWED_ORIGINS` are only needed if you ever
split the frontend onto a different origin again — leave them unset for the
normal same-origin setup.

Render auto-deploys on push (`autoDeploy: true`). The optional
`.github/workflows/backend-deploy.yml` also pokes the Render deploy API
(`RENDER_API_KEY` + `RENDER_SERVICE_ID` secrets).

### Custom domains

In the Render dashboard → service → Settings → Custom Domains, add:
- `benconnect.de`
- `www.benconnect.de`

For each domain Render shows the DNS record to create. At your DNS provider
for `benconnect.de`:
- Apex (`benconnect.de`): Render will give you either an A record (their
  anycast IP) or ask you to use an ALIAS/ANAME if your DNS host supports it.
- `www`: CNAME to the hostname Render gives you (typically
  `<service>.onrender.com`).

Wait for each domain to show "Verified" in Render (DNS propagation + automatic
TLS certificate issuance).

⚠️ Do not leave the apex domain's DNS pointed at GitHub Pages or Cloudflare
Pages — this repo no longer publishes a separate static site there.

## Local development

```bash
pip install -r requirements.txt
# needs a MongoDB — local mongod or an Atlas dev cluster
MONGODB_URI="mongodb://localhost:27017" MONGODB_DB=grouply python app.py
```
Do NOT set `SESSION_COOKIE_*` locally (they force Secure cookies, which browsers
drop over http://localhost).
