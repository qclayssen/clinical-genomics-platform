/**
 * Typed client for the Clinical Genomics Insight Platform's variant-review
 * API. `/agent/variant-review` is a thin adapter over the platform's
 * existing agentic variant interpreter (ai-report/agent/, ADR-0014) — no new
 * agent lives behind this endpoint. Sign-off reuses the existing insert-only
 * `/runs/{run_id}/review-decisions` endpoint (ADR-0019), not a bespoke one.
 *
 * Portfolio project — this API is not an accredited clinical test. Every
 * assessment returned here is AI-drafted and requires clinician sign-off
 * before it means anything (see GuardrailBanner and SignOffPanel).
 *
 * Base URL resolution:
 *  - In dev, requests go to `/api/...` which Vite proxies to
 *    VITE_API_BASE_URL (default http://127.0.0.1:8000) — see vite.config.ts.
 *  - In a production build (no dev proxy available), requests go straight
 *    to VITE_API_BASE_URL if set, otherwise http://127.0.0.1:8000.
 */

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

function resolveApiBase(): string {
  const configured = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (import.meta.env.DEV) {
    // Use the Vite dev proxy so the browser never needs CORS.
    return "/api";
  }
  return configured || DEFAULT_API_BASE_URL;
}

export type AgentBackend = "deterministic" | "ollama" | "openai" | "anthropic" | "azure_foundry" | "bedrock";

export interface VariantReviewRequest {
  chrom: string;
  pos: number;
  ref: string;
  alt: string;
  gene?: string;
  genotype?: string;
  run_id: string;
  backend?: AgentBackend;
}

export interface FhirVariantReviewRequest {
  /** A FHIR Observation resource — see ai-report/agent/fhir_intake.py for the recognized LOINC components. */
  resource: Record<string, unknown>;
  run_id: string;
  backend?: AgentBackend;
}

export interface AgentTraceStep {
  type: string;
  content: string;
  timestamp?: number;
  tool_name?: string | null;
  tool_input?: Record<string, unknown> | null;
  tool_output?: Record<string, unknown> | null;
  duration_ms?: number | null;
}

export interface VariantAssessment {
  run_id: string;
  variant_key: string;
  chrom: string;
  pos: number;
  ref: string;
  alt: string;
  gene: string;
  genotype: string;
  classification: string;
  evidence_codes: string[];
  confidence: string;
  summary: string;
  citations: string[];
  banner: string;
  backend_used: string;
  agent_trace: AgentTraceStep[];
  provenance: Record<string, unknown>;
  guardrail_violations: string[];
}

export type ReviewDecisionOutcome = "approved" | "rejected";

export interface ReviewDecisionRequest {
  variant_key: string;
  classification: string;
  decision: ReviewDecisionOutcome;
  reviewer: string;
  comment?: string;
}

export interface ReviewDecision extends ReviewDecisionRequest {
  id: number;
  run_id: string;
  decided_at: string;
}

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function parseErrorBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    try {
      return await response.text();
    } catch {
      return null;
    }
  }
}

async function postJson<TResponse>(path: string, body: unknown): Promise<TResponse> {
  const base = resolveApiBase();
  const response = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const errorBody = await parseErrorBody(response);
    const detail =
      typeof errorBody === "object" && errorBody !== null && "detail" in errorBody
        ? String((errorBody as { detail: unknown }).detail)
        : response.statusText;
    throw new ApiError(
      `Request to ${path} failed (${response.status}): ${detail}`,
      response.status,
      errorBody,
    );
  }

  return (await response.json()) as TResponse;
}

/** POST /agent/variant-review — runs the existing agentic interpreter on one variant. */
export function submitVariantReview(input: VariantReviewRequest): Promise<VariantAssessment> {
  return postJson<VariantAssessment>("/agent/variant-review", input);
}

/** POST /agent/variant-review/fhir — same review, variant supplied as a FHIR Observation. */
export function submitFhirVariantReview(input: FhirVariantReviewRequest): Promise<VariantAssessment> {
  return postJson<VariantAssessment>("/agent/variant-review/fhir", input);
}

/**
 * Record clinician sign-off. Reuses the platform-wide, insert-only
 * `POST /runs/{run_id}/review-decisions` endpoint (ADR-0019) — a decision
 * here is a new row, never an edit to a previous one.
 */
export function recordReviewDecision(
  runId: string,
  decision: ReviewDecisionRequest,
): Promise<ReviewDecision> {
  return postJson<ReviewDecision>(`/runs/${encodeURIComponent(runId)}/review-decisions`, decision);
}
