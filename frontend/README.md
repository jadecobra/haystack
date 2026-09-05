# LongMuch frontend

Next.js App Router UI for LongMuch (`longmuch-web`).

## Dev

```bash
pnpm install
pnpm dev
```

Open http://localhost:3000.

## Backend origin

`app/api/analyze/[ticker]/route.ts` proxies to the FastAPI backend. Set one of:

- `BACKEND_ORIGIN`
- `HAYSTACK_BACKEND_ORIGIN`

Default is `http://127.0.0.1:8000`. On Vercel, set `BACKEND_ORIGIN` to the Render API URL.
