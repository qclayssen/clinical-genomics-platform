import { useState } from "react";
import type { AgentBackend, VariantAssessment, VariantReviewRequest } from "../api/client";
import { submitFhirVariantReview, submitVariantReview } from "../api/client";
import { GuardrailBanner } from "../components/GuardrailBanner";
import { AgentTrace } from "../components/AgentTrace";
import { SignOffPanel } from "../components/SignOffPanel";

interface FormState {
  chrom: string;
  pos: string;
  ref: string;
  alt: string;
  gene: string;
  genotype: string;
  runId: string;
  backend: AgentBackend;
}

type IntakeMode = "manual" | "fhir";

const GENOTYPE_OPTIONS = ["heterozygous", "homozygous", "hemizygous"];

const BACKEND_OPTIONS: { value: AgentBackend; label: string }[] = [
  { value: "deterministic", label: "Deterministic (default — no LLM, no setup)" },
  { value: "ollama", label: "Ollama (local LLM)" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "azure_foundry", label: "Azure AI Foundry" },
  { value: "bedrock", label: "AWS Bedrock" },
];

// A known chr20 variant covered by the local ClinVar/gnomAD knowledge base
// (see tests/test_agent_smoke.py) — a sensible, always-classifiable default.
const INITIAL_FORM_STATE: FormState = {
  chrom: "chr20",
  pos: "4699605",
  ref: "G",
  alt: "A",
  gene: "PRNP",
  genotype: GENOTYPE_OPTIONS[0],
  runId: "run_2026_0301_a",
  backend: "deterministic",
};

const SAMPLE_FHIR_OBSERVATION = JSON.stringify(
  {
    resourceType: "Observation",
    component: [
      { code: { coding: [{ code: "48000-4" }] }, valueString: "chr20" },
      { code: { coding: [{ code: "81254-5" }] }, valueInteger: 4699605 },
      { code: { coding: [{ code: "69547-8" }] }, valueString: "G" },
      { code: { coding: [{ code: "69551-0" }] }, valueString: "A" },
      { code: { coding: [{ code: "48018-6" }] }, valueString: "PRNP" },
      {
        code: { coding: [{ code: "53034-5" }] },
        valueCodeableConcept: { coding: [{ display: "heterozygous" }] },
      },
    ],
  },
  null,
  2,
);

export function VariantReview() {
  const [mode, setMode] = useState<IntakeMode>("manual");
  const [form, setForm] = useState<FormState>(INITIAL_FORM_STATE);
  const [fhirJson, setFhirJson] = useState(SAMPLE_FHIR_OBSERVATION);
  const [fhirRunId, setFhirRunId] = useState(INITIAL_FORM_STATE.runId);
  const [fhirBackend, setFhirBackend] = useState<AgentBackend>("deterministic");
  const [assessment, setAssessment] = useState<VariantAssessment | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleManualSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const pos = Number(form.pos);
    if (!form.chrom.trim() || !Number.isFinite(pos) || !form.ref.trim() || !form.alt.trim() || !form.runId.trim()) {
      setError("Chromosome, position, ref, alt, and run ID are required.");
      return;
    }

    const request: VariantReviewRequest = {
      chrom: form.chrom.trim(),
      pos,
      ref: form.ref.trim().toUpperCase(),
      alt: form.alt.trim().toUpperCase(),
      gene: form.gene.trim(),
      genotype: form.genotype,
      run_id: form.runId.trim(),
      backend: form.backend,
    };

    setIsSubmitting(true);
    setAssessment(null);
    try {
      const result = await submitVariantReview(request);
      setAssessment(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Variant review request failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleFhirSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!fhirRunId.trim()) {
      setError("Run ID is required.");
      return;
    }

    let resource: Record<string, unknown>;
    try {
      resource = JSON.parse(fhirJson);
    } catch {
      setError("That isn't valid JSON.");
      return;
    }

    setIsSubmitting(true);
    setAssessment(null);
    try {
      const result = await submitFhirVariantReview({ resource, run_id: fhirRunId.trim(), backend: fhirBackend });
      setAssessment(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "FHIR variant review request failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="page">
      <header className="page__header">
        <h1>Variant Review</h1>
        <p>
          Submit a variant to the platform's existing agentic interpreter for a draft ACMG
          classification. <strong>This is a portfolio project, not an accredited clinical test.</strong>{" "}
          Every result is AI-drafted and requires clinician sign-off before it means anything —
          see the guardrail banner below.
        </p>
      </header>

      <div className="intake-tabs" role="tablist" aria-label="Variant intake mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "manual"}
          className={mode === "manual" ? "intake-tabs__tab intake-tabs__tab--active" : "intake-tabs__tab"}
          onClick={() => setMode("manual")}
        >
          Manual fields
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "fhir"}
          className={mode === "fhir" ? "intake-tabs__tab intake-tabs__tab--active" : "intake-tabs__tab"}
          onClick={() => setMode("fhir")}
        >
          FHIR Observation
        </button>
      </div>

      {mode === "manual" ? (
        <section className="review-form" aria-label="Submit a variant for review">
          <form onSubmit={handleManualSubmit}>
            <div className="form-row">
              <label htmlFor="chrom">Chromosome</label>
              <input
                id="chrom"
                type="text"
                value={form.chrom}
                onChange={(event) => updateField("chrom", event.target.value)}
                placeholder="chr20"
                disabled={isSubmitting}
                required
              />
            </div>

            <div className="form-row">
              <label htmlFor="pos">Position</label>
              <input
                id="pos"
                type="number"
                value={form.pos}
                onChange={(event) => updateField("pos", event.target.value)}
                placeholder="4699605"
                disabled={isSubmitting}
                required
              />
            </div>

            <div className="form-row">
              <label htmlFor="ref">Ref allele</label>
              <input
                id="ref"
                type="text"
                value={form.ref}
                onChange={(event) => updateField("ref", event.target.value)}
                placeholder="G"
                disabled={isSubmitting}
                required
              />
            </div>

            <div className="form-row">
              <label htmlFor="alt">Alt allele</label>
              <input
                id="alt"
                type="text"
                value={form.alt}
                onChange={(event) => updateField("alt", event.target.value)}
                placeholder="A"
                disabled={isSubmitting}
                required
              />
            </div>

            <div className="form-row">
              <label htmlFor="gene">Gene (optional)</label>
              <input
                id="gene"
                type="text"
                value={form.gene}
                onChange={(event) => updateField("gene", event.target.value)}
                placeholder="PRNP"
                disabled={isSubmitting}
              />
            </div>

            <div className="form-row">
              <label htmlFor="genotype">Zygosity</label>
              <select
                id="genotype"
                value={form.genotype}
                onChange={(event) => updateField("genotype", event.target.value)}
                disabled={isSubmitting}
                required
              >
                {GENOTYPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-row">
              <label htmlFor="backend">AI backend</label>
              <select
                id="backend"
                value={form.backend}
                onChange={(event) => updateField("backend", event.target.value as AgentBackend)}
                disabled={isSubmitting}
              >
                {BACKEND_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <p className="form-row__hint">
                Non-deterministic backends need their own credentials configured server-side and
                fall back to deterministic automatically if unavailable.
              </p>
            </div>

            <div className="form-row">
              <label htmlFor="run-id">Run ID</label>
              <input
                id="run-id"
                type="text"
                value={form.runId}
                onChange={(event) => updateField("runId", event.target.value)}
                placeholder="run_2026_0301_a"
                disabled={isSubmitting}
                required
              />
              <p className="form-row__hint">
                Must be an existing pipeline run (see <code>GET /runs</code>) — sign-off is recorded
                against it.
              </p>
            </div>

            <button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Submitting…" : "Submit for review"}
            </button>
          </form>
        </section>
      ) : (
        <section className="review-form" aria-label="Submit a FHIR Observation for review">
          <p className="form-row__hint">
            Paste a FHIR genomics <code>Observation</code> resource. Only a subset of the HL7
            Genomics Reporting IG's component codes is read (chromosome, position, ref/alt
            allele, gene, zygosity) — see <code>ai-report/agent/fhir_intake.py</code>.
          </p>
          <form onSubmit={handleFhirSubmit}>
            <div className="form-row">
              <label htmlFor="fhir-json">FHIR Observation (JSON)</label>
              <textarea
                id="fhir-json"
                value={fhirJson}
                onChange={(event) => setFhirJson(event.target.value)}
                rows={14}
                disabled={isSubmitting}
                spellCheck={false}
              />
            </div>

            <div className="form-row">
              <label htmlFor="fhir-backend">AI backend</label>
              <select
                id="fhir-backend"
                value={fhirBackend}
                onChange={(event) => setFhirBackend(event.target.value as AgentBackend)}
                disabled={isSubmitting}
              >
                {BACKEND_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-row">
              <label htmlFor="fhir-run-id">Run ID</label>
              <input
                id="fhir-run-id"
                type="text"
                value={fhirRunId}
                onChange={(event) => setFhirRunId(event.target.value)}
                placeholder="run_2026_0301_a"
                disabled={isSubmitting}
                required
              />
            </div>

            <button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Submitting…" : "Submit FHIR Observation"}
            </button>
          </form>
        </section>
      )}

      {error && (
        <p className="review-form__error" role="alert">
          {error}
        </p>
      )}

      {isSubmitting && (
        <p className="loading-indicator" role="status">
          Running the agentic interpreter — querying the knowledge base and applying ACMG rules…
        </p>
      )}

      {assessment && (
        <div className="review-result">
          <GuardrailBanner
            text={assessment.banner}
            violations={assessment.guardrail_violations}
          />
          <AgentTrace trace={assessment.agent_trace} />
          <SignOffPanel assessment={assessment} />
        </div>
      )}
    </main>
  );
}
