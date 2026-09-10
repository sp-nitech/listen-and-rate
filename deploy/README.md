# Deploy on DigitalOcean (`rate.ramsalab.ae`)

Single Droplet, Docker Compose, Caddy for HTTPS. The app is one Uvicorn
process; ratings are JSON files under `data/ratings/`. Do not use App Platform.

## Droplet

| Setting | Value |
|---------|--------|
| Image | Ubuntu 24.04 LTS |
| Plan | **Basic, 2 GiB RAM / 1 vCPU / 50 GiB SSD** (~$12/mo) |
| Region | **Frankfurt (`fra1`)** — closest to the UAE. `ams3` is the fallback. |
| Auth | SSH keys only |
| Hostname | `rate` |
| Backups | Enable (~$2.40/mo) |

Skip the $6 / 1 GiB size: image builds and Caddy plus Python can OOM. You do
not need 2 vCPUs for 10 raters.

Create a **Cloud Firewall** on the Droplet. Inbound TCP only:

- `22` (SSH)
- `80` (ACME + redirect)
- `443` (HTTPS)

Do not open `8000`. That port stays on the Docker network.

## DNS

In DigitalOcean Networking → Domains → `ramsalab.ae`:

| Type | Hostname | Value | TTL |
|------|----------|--------|-----|
| A | `rate` | Droplet public IPv4 | 300 |

Add AAAA only if the Droplet has IPv6. Wait until `rate.ramsalab.ae` resolves
before the first `compose up` so Let's Encrypt HTTP-01 can succeed:

```sh
dig +short rate.ramsalab.ae
```

## First boot

SSH in and install Docker Engine plus the Compose plugin from
[Docker's Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).

Copy this repo onto the Droplet (clone or `rsync`). Experiment data is **not**
in the image:

- `data/json/config.yaml`
- `data/json/assignments.json` — 10 real rater IDs, not `alice`/`bob`/`carol`
- `data/audio/source/` and `data/audio/generated/` — matching filenames
- `data/ratings/` — empty, writable

The container user is `app` (uid 1000):

```sh
sudo chown -R 1000:1000 data/ratings
```

Create `.env` at the repo root:

```sh
cp deploy/env.example .env
```

Set `ACME_EMAIL` to an address you read. Generate the admin password hash:

```sh
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'your-password'
```

Paste the bcrypt string into `ADMIN_PASSWORD_HASH`, doubling every `$`
(`$2a$14$…` becomes `$$2a$$14$$…`) so Compose does not eat the hash.

Start:

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Checks:

- `https://rate.ramsalab.ae/api/status` — `{"status":"ok",…}`
- `https://rate.ramsalab.ae/?rater=<id>` — rating UI (Chrome, Edge, or Firefox; Safari is unsupported)
- `https://rate.ramsalab.ae/progress` and `/report` — HTTP basic auth (`admin` + the password you hashed)

Give each rater a unique, unguessable link. There is no login; knowing an ID
is enough to open that session:

```text
https://rate.ramsalab.ae/?rater=<their-id>
```

## Updates

Experiment files only (config, assignments, audio) — no image rebuild:

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart rate-app
```

Backend or UI code — rebuild:

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Backups

Droplet backups snapshot the whole VM weekly. Also copy ratings off the box;
losing the Droplet without that loses the study:

```sh
rsync -avz user@rate.ramsalab.ae:/path/to/rate-app/data/ratings/ ./ratings-backup/
```

If the audio corpus grows past ~20 GiB, attach a Volume and bind-mount it at
`/app/data/audio` instead of keeping clips on the boot disk.
