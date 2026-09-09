# ADR-0028 — Azure AI Foundry / AWS Bedrock backends, and a minimal FHIR intake

**Status:** Accepted · **Date:** 2026-09-09

## Context

ADR-0027 exposed the existing agentic variant interpreter (ADR-0014) over REST and React, but
`agent/llm.py`'s multi-provider abstraction only covered Ollama, OpenAI, and Anthropic — none of
this platform's stated target AI platforms (Azure AI Foundry, AWS Bedrock) were represented, and
the REST route only ever ran the deterministic path. Separately, every intake path into the agent
(CLI, Streamlit, the new REST form) required discrete chrom/pos/ref/alt fields; there was no way
to demonstrate ingesting from a clinical-data-standard shape, which is a common integration point
for this kind of tooling in a hospital setting.

## Decision

**LLM backends.** Add `AzureFoundryBackend` and `BedrockBackend` to `agent/llm.py`, following the
exact shape of the existing backends (`LLMBackend` ABC: `name`, `model_id`, `is_available()`,
`generate()`):

- `AzureFoundryBackend` uses the `openai` package's `AzureOpenAI` client — Azure AI Foundry's
  OpenAI-family and OpenAI-compatible deployments speak the same Chat Completions wire format as
  OpenAI itself, so message/response conversion is factored into shared
  `_messages_to_openai_format()` / `_parse_openai_style_response()` helpers used by both
  `OpenAIBackend` and `AzureFoundryBackend`, rather than duplicated.
- `BedrockBackend` uses Bedrock's model-agnostic **Converse API** (not a per-model-family
  integration), authenticating via boto3's standard credential chain rather than a bespoke API-key
  env var — consistent with how this platform's other AWS code
  (`db/sync_dynamodb_to_postgres.py`, `infra/`) authenticates.
- `POST /agent/variant-review` (and its FHIR sibling below) gained an opt-in `backend` field. Any
  non-deterministic backend runs the real `ReActAgent`, and — reusing
  `ai-report/agent/interpret.py`'s existing CLI fallback policy verbatim rather than reinventing
  it — falls back to `DeterministicInterpreter` if the agent can't complete cleanly (backend
  unavailable, loop detected, etc.), keeping the partial trace.

**FHIR intake.** Add `agent/fhir_intake.py`: `variant_from_fhir_observation()` maps a **subset** of
the HL7 FHIR Genomics Reporting IG's `Observation` component codes (48000-4 chromosome, 81254-5
allele start, 69547-8/69551-0 ref/alt allele, 48018-6 gene, 53034-5 allelic state) to a `Variant`.
This is explicitly not a conformant FHIR profile validator — it's scoped to exactly the fields the
agent consumes, and says so in its own docstring. Wired in as `POST /agent/variant-review/fhir`,
sharing the same interpretation/guardrail/response path as the manual-fields endpoint via an
extracted `_run_interpretation()` / `_to_assessment()` pair in `api/routers/agent.py`.

**Bug found and fixed in passing.** Building tests for the `backend` param surfaced a real
threading bug: the router previously held one module-level `DeterministicInterpreter()` singleton,
but its cached SQLite connection (`agent/data/knowledge_base.py`) is bound to the thread that
created it. FastAPI's request handling (and the test client) can dispatch across threads, which
intermittently raised `sqlite3.ProgrammingError`. Fixed by constructing a fresh interpreter per
request — cheap (a local SQLite file open) — rather than sharing one across threads.

## Consequences

**Good**
- Both of the JD-relevant cloud AI platforms are now real, tested code paths (mocked in tests, not
  live-network — no cloud account needed to run the suite), not just aspirational mentions.
- The FHIR intake path demonstrates an EMR-shaped integration point without requiring a real Epic/
  HL7 feed or overclaiming IG conformance.
- Sharing `_messages_to_openai_format`/`_parse_openai_style_response` between OpenAI and Azure
  Foundry avoids the append-a-third-near-duplicate-class outcome ADR-0027 was written to avoid.
- The threading bug fix is a real correctness improvement, not scope creep — it was a latent bug
  in the code ADR-0027 shipped, caught by writing more tests against it.

**Bad / accepted limitations**
- `BedrockBackend` is exercised in tests via a mocked `bedrock-runtime` client, not a real AWS
  account — there is no CI signal that a real Converse API call would succeed end-to-end.
- The FHIR mapping is intentionally narrow (five components); a real Genomics Reporting IG payload
  with nested `derivedFrom` references, `Sequence` resources, or a coordinate system other than the
  simplified single-position one used here won't parse. This is stated in the module docstring, not
  hidden.
- `ReActAgent`'s LLM path still isn't exercised against a real model in CI (by design — no
  network/cloud dependency in the test suite), so its ClinVar/gnomAD tool-use loop is only verified
  through the deterministic path and the mocked backend unit tests.

## Alternatives considered

- **A bespoke Azure/Bedrock HTTP client instead of `openai`/`boto3`** — rejected: both providers
  ship (or are wire-compatible with) maintained SDKs; hand-rolling auth and retries would be pure
  risk for no benefit.
- **A full FHIR Genomics Reporting IG validator (e.g. via `fhir.resources`)** — rejected as
  out of scope: this platform doesn't otherwise touch FHIR, and a "conformant validator" claim
  would be dishonest for five hand-read component codes; a documented subset is the honest version.
- **Wiring `backend` selection through query params instead of the request body** — rejected for
  consistency: every other field on this endpoint is already in the JSON body.
