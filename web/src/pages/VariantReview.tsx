import { useState } from "react";
import type { VariantAssessment, VariantReviewRequest } from "../api/client";
import { submitVariantReview } from "../api/client";
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
}

const GENOTYPE_OPTIONS = ["heterozygous", "homozygous", "hemizygous"];

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
};

export function VariantReview() {
  const [form, setForm] = useState<FormState>(INITIAL_FORM_STATE);
  const [assessment, setAssessment] = useState<VariantAssessment | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
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

      <section className="review-form" aria-label="Submit a variant for review">
        <form onSubmit={handleSubmit}>
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

        {error && (
          <p className="review-form__error" role="alert">
            {error}
          </p>
        )}
      </section>

      {isSubmitting && (
        <p className="loading-indicator" role="status">
          Running the agentic interpreter — querying the knowledge base and applying ACMG rules…
        </p>
      )}

      {assessment && (
        <div className="review-result">
          <GuardrailBanner text={assessment.banner} />
          <AgentTrace trace={assessment.agent_trace} />
          <SignOffPanel assessment={assessment} />
        </div>
      )}
    </main>
  );
}
