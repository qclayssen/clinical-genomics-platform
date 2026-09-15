# ADR-0030 — Azure deployment for the REST API + React frontend

**Status:** Accepted · **Date:** 2026-09-15

## Context

ADR-0027 added a REST API (`api/`) and React frontend (`web/`) as thin adapters over the existing
variant interpreter. Both apps only had a local run path (`uvicorn api.main:app --reload`,
`npm run dev`) — no deployment target existed for either. Separately, this platform's only cloud
hosting is AWS: `infra/lib/demo-hosting-stack.ts` runs the Streamlit demo + Metabase on an EC2
instance. ADR-0028 added an `AzureFoundryBackend` LLM backend, but that consumes Azure's AI API —
it does not deploy anything to Azure, so it doesn't demonstrate an actual Azure hosting path.

## Decision

Add `azure/` — Bicep templates deploying `api/` as an **Azure Container App** and `web/`'s built
`dist/` as an **Azure Static Web App** — following the same honesty pattern already used for AWS
in this repo: infra-as-code plus CI validation, with a real deploy left to the operator's own
account, never run automatically.

- **Bicep, not Terraform.** Azure's native ARM DSL needs only the `az`/`bicep` CLI, no extra
  language runtime — parallel to how `infra/` uses CDK's native TypeScript rather than raw
  CloudFormation or a third IaC tool.
- **Container Apps, not App Service**, for the API: consumption-based scale-to-zero (`minReplicas:
  0`) keeps idle cost at zero, matching this platform's existing free-tier bias (ADR-0011,
  `infra-ci.yml`'s banned-resource check for `AWS::RDS`/NAT gateways/etc.).
- **`CGP_DB_URL` stays optional**, passed as a secure Bicep param defaulting to empty — the
  Container App runs fixture-backed by default, identical to `api/main.py`'s existing local
  behaviour. No new database is introduced.
- **A Log Analytics workspace is provisioned alongside the Container Apps environment** and wired
  via `appLogsConfiguration` — a managed environment with an empty `properties` object is rejected
  by ARM at deploy time (`bicep build`/`bicep lint` only check template syntax, not
  resource-provider validation, so this needed to be explicit rather than assumed).
- **CI runs `bicep build` + `bicep lint` only** (`.github/workflows/azure-ci.yml`), mirroring
  `infra-ci.yml`'s `cdk synth`-not-`cdk deploy` stance: it catches template syntax/type errors on
  every PR touching `azure/**` without requiring `AZURE_CREDENTIALS` in CI secrets.
- **`docker/Dockerfile.api`** containerizes `api/` following `Dockerfile.demo`'s existing pattern
  (pinned pip/setuptools/wheel for the same CVEs already patched there, `HEALTHCHECK` against the
  API's existing `/healthz` route) — copies only `api/`, `ai-report/agent/`, and
  `ai-report/guardrails.py` (the modules `api/routers/agent.py` actually imports), not the full
  `ai-report/requirements.txt` ML stack (torch/transformers/etc.), which the API's default
  deterministic path never touches — those are imported lazily per-backend in `agent/llm.py` only
  when a non-default `AGENT_LLM_BACKEND` is selected.

## Consequences

**Good**
- "Deploying on Azure" is now backed by real, CI-checked IaC rather than an aspirational mention —
  same evidentiary bar this repo already holds AWS deployment to.
- Entirely additive: no AWS stack, pipeline module, or DB schema changed. `infra/` and `azure/`
  are independent; a reviewer can read either without needing the other.
- The Container App's optional `CGP_DB_URL` and Static Web App's `/api/*` proxy
  (`web/staticwebapp.config.json`) reuse exactly the config surface `api/main.py` and
  `vite.config.ts` already expose — no parallel configuration scheme invented.

**Bad / accepted limitations**
- CI never runs a real `az deployment group create` — there is no automated signal that the
  templates actually provision successfully end-to-end, only that they compile and lint cleanly.
  Same accepted limitation already documented for `BedrockBackend` in ADR-0028.
- `minReplicas: 0` means the first request after idle cold-starts; acceptable for a portfolio
  demo, would need tuning for a real SLA.
- The Static Web App ↔ Container App backend link (`az staticwebapp backends link`) is a manual,
  one-time `az` command in `azure/README.md`, not itself expressed in Bicep — Microsoft's
  `Microsoft.Web/staticSites/linkedBackends` resource type exists but linking at deploy time
  requires the Container App to already exist, which would need a two-pass deployment; documented
  as a manual step rather than adding that complexity for a portfolio-scale target.

## Alternatives considered

- **Terraform instead of Bicep** — rejected: Bicep is Azure-native (no state file to manage, no
  extra binary beyond `az`), and this repo already accepts a cloud-native IaC tool per platform
  (CDK for AWS) rather than standardizing on one cross-cloud tool.
- **Azure App Service instead of Container Apps** — rejected: App Service's cheapest non-free tier
  bills continuously; Container Apps' consumption plan scales to zero, matching the free-tier bias
  already enforced by `infra-ci.yml`'s banned-resource-type check.
- **Baking `CGP_DB_URL` as a required param** — rejected: would break the "runs with no setup"
  promise `api/main.py`'s own docstring makes; kept optional exactly as it is locally.
