# Variant Review UI

A small React + TypeScript + Vite frontend over the platform's existing
agentic variant interpreter (`ai-report/agent/`, [ADR-0014](../docs/adr/0014-agentic-variant-interpretation.md)).
A clinician enters a variant (chrom/pos/ref/alt, gene, zygosity), the agent
drafts an ACMG classification with a full reasoning trace, and the UI records
clinician sign-off through the platform's existing insert-only
`/runs/{run_id}/review-decisions` endpoint ([ADR-0019](../docs/adr/0019-reviewer-decision-log.md)).
See [ADR-0027](../docs/adr/0027-rest-react-frontend-for-variant-interpreter.md)
for why this is a thin adapter over existing capability rather than a new agent.

**This is a portfolio project, not an accredited clinical test.** Every
assessment rendered here is AI-drafted and carries the mandatory
`AI-DRAFTED VARIANT INTERPRETATION — REQUIRES CLINICAL GENETICIST REVIEW`
banner — see the project-wide scope-honesty note in [`../CLAUDE.md`](../CLAUDE.md).

## Run it (no setup beyond stated deps)

```bash
cd web
npm install
npm run dev
```

Then open the URL Vite prints (typically <http://127.0.0.1:5173>).

By default, dev-server API calls are proxied to the platform's FastAPI
service at `http://127.0.0.1:8000` (see [`../api/README.md`](../api/README.md)
for how to run it):

```bash
# in a separate terminal, from the repo root
pip install -r api/requirements.txt
uvicorn api.main:app --reload
```

This UI calls `POST /agent/variant-review` (`api/routers/agent.py`) — a thin
adapter over the existing `ai-report/agent/` interpreter — and the platform's
existing `POST /runs/{run_id}/review-decisions` for sign-off. Both are
fixture-backed by default, no database required.

## Pointing at a different API host

Set `VITE_API_BASE_URL` before starting the dev server, e.g.:

```bash
VITE_API_BASE_URL=http://127.0.0.1:9000 npm run dev
```

The dev server proxies `/api/*` requests to that host (see
[`vite.config.ts`](vite.config.ts)), so the browser never needs CORS
configuration. In a production build, requests go directly to
`VITE_API_BASE_URL` (falling back to `http://127.0.0.1:8000` if unset).

## Build

```bash
npm run build
```

Runs a TypeScript type-check (`tsc`) followed by `vite build`, emitting
static assets to `web/dist/`.

## Project layout

| Path | What's here |
|---|---|
| `src/api/client.ts` | Typed `fetch` wrappers and TypeScript types for the variant-review API contract |
| `src/pages/VariantReview.tsx` | The form + result flow: submit a variant, show loading, render the result |
| `src/components/GuardrailBanner.tsx` | The mandatory, non-dismissible AI-drafted warning banner (text comes from the API response) |
| `src/components/AgentTrace.tsx` | Step-by-step render of the agent's reasoning trace — the audit trail, not a black box |
| `src/components/SignOffPanel.tsx` | Classification, ACMG evidence codes, summary, provenance, and the approve/reject sign-off control |
| `src/styles.css` | Plain CSS, no component library |

## Known limitations

No authentication, no persistence beyond what the backend API provides, and
no automated tests yet. This is a demo UI: see [`../CLAUDE.md`](../CLAUDE.md)
for the project's overall scope-honesty note.
