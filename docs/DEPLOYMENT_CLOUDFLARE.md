# Cloudflare Deployment

The current backend is FastAPI/Python, so it should run on a Python-capable host.
Cloudflare can still be used as the public edge:

1. Deploy the FastAPI backend to a Python host.
2. Put the Cloudflare Worker gateway in front of that backend.
3. Deploy the static demo to Cloudflare Pages.
4. Point the demo/API URL at the Worker gateway.

## Worker Gateway

The Worker in `cloudflare/api-gateway` proxies `/api/v1/*` requests to a public
FastAPI origin and forwards `CF-Connecting-IP` as `X-Forwarded-For` for risk
scoring.

```bash
cd cloudflare/api-gateway
npx wrangler secret put POUW_API_ORIGIN
npx wrangler deploy
```

Set `POUW_API_ORIGIN` to the backend origin, for example:

```text
https://api.example.com
```

## Pages Demo

The static demo currently calls same-origin `/api/v1`. Deploy it after either:

- placing the Worker on the same hostname/path, or
- updating the demo API origin to the Worker URL.

```bash
npx wrangler pages deploy demo/frontend --project-name pouw-captcha-demo
```

## Required Production Environment

Backend:

```text
DEBUG=false
SECRET_KEY=<strong random value>
ADMIN_API_KEY=<strong random value>
DATABASE_URL=<production database>
REDIS_URL=<production redis>
ALLOWED_ORIGINS=<registered demo/site origins>
ALLOW_DEBUG_SITE_AUTOCREATE=false
DEFAULT_MODEL=mnist-tiny
```

Register a site:

```bash
curl -X POST https://<api-host>/api/v1/sites/register \
  -H "Content-Type: application/json" \
  -H "X-POUW-Admin-Key: <ADMIN_API_KEY>" \
  -d '{
    "domain": "example.com",
    "allowedOrigins": ["https://example.com"],
    "verificationRate": 0.2,
    "difficultyMultiplier": 1.0
  }'
```

Use the returned `siteKey` in browser code and keep `secretKey` only on the
application backend for token validation.

## Validation Contract

```bash
curl https://<api-host>/api/v1/captcha/validate/<token> \
  -H "X-POUW-Secret-Key: <site secret key>"
```

Tokens are one-time-use. A successful validation burns the token id in Redis
until token expiry.
