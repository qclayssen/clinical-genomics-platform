import { useState } from "react";
import type { ReviewDecision, ReviewDecisionOutcome, VariantAssessment } from "../api/client";
import { recordReviewDecision } from "../api/client";

interface SignOffPanelProps {
  assessment: VariantAssessment;
}

/**
 * Shows the classification, rationale, and ACMG evidence codes for an
 * assessment, plus the clinician sign-off control. Sign-off is recorded via
 * the platform's existing insert-only `/runs/{run_id}/review-decisions`
 * endpoint (ADR-0019) — a re-review is always a *new* decision row, never an
 * edit to this one.
 */
export function SignOffPanel({ assessment }: SignOffPanelProps) {
  const [reviewer, setReviewer] = useState("");
  const [comment, setComment] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recorded, setRecorded] = useState<ReviewDecision | null>(null);

  async function handleDecision(decision: ReviewDecisionOutcome) {
    const trimmedName = reviewer.trim();
    if (!trimmedName) {
      setError("Enter your name before recording a decision.");
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await recordReviewDecision(assessment.run_id, {
        variant_key: assessment.variant_key,
        classification: assessment.classification,
        decision,
        reviewer: trimmedName,
        comment: comment.trim(),
      });
      setRecorded(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Recording the decision failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="signoff-panel" aria-label="Classification and sign-off">
      <h2>Classification</h2>
      <p
        className={`classification-badge classification-badge--${assessment.classification
          .toLowerCase()
          .replace(/\s+/g, "-")}`}
      >
        {assessment.classification}
        <span className="classification-badge__confidence"> ({assessment.confidence} confidence)</span>
      </p>

      {assessment.evidence_codes.length > 0 && (
        <div className="acmg-chips" aria-label="ACMG evidence codes">
          {assessment.evidence_codes.map((code) => (
            <span key={code} className="acmg-chip">
              {code}
            </span>
          ))}
        </div>
      )}

      <h3>Summary</h3>
      <p className="rationale-text">{assessment.summary}</p>

      {assessment.citations.length > 0 && (
        <>
          <h3>Citations</h3>
          <ul className="citations-list">
            {assessment.citations.map((citation) => (
              <li key={citation}>{citation}</li>
            ))}
          </ul>
        </>
      )}

      <h3>Provenance</h3>
      <dl className="provenance-list">
        {Object.entries(assessment.provenance).map(([key, value]) => (
          <div key={key} className="provenance-list__row">
            <dt>{key}</dt>
            <dd>{String(value)}</dd>
          </div>
        ))}
      </dl>

      <div className="signoff-control">
        {recorded ? (
          <p className="signoff-control__recorded">
            <strong>{recorded.decision === "approved" ? "Approved" : "Rejected"}</strong> by{" "}
            <strong>{recorded.reviewer}</strong> at <strong>{recorded.decided_at}</strong>
          </p>
        ) : (
          <>
            <h3>Reviewer decision</h3>
            <p className="signoff-control__hint">
              Confirms you, a qualified clinician, have reviewed the agent trace and summary above
              and take responsibility for this decision.
            </p>
            <div className="signoff-control__form">
              <label htmlFor="reviewer-name">Your name</label>
              <input
                id="reviewer-name"
                type="text"
                value={reviewer}
                onChange={(event) => setReviewer(event.target.value)}
                placeholder="Dr. Jane Smith"
                disabled={isSubmitting}
              />
              <label htmlFor="reviewer-comment">Comment (optional)</label>
              <input
                id="reviewer-comment"
                type="text"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                placeholder="Confirmed against ClinVar submission…"
                disabled={isSubmitting}
              />
              <div className="signoff-control__buttons">
                <button type="button" onClick={() => handleDecision("approved")} disabled={isSubmitting}>
                  {isSubmitting ? "Recording…" : "Approve"}
                </button>
                <button
                  type="button"
                  className="signoff-control__reject"
                  onClick={() => handleDecision("rejected")}
                  disabled={isSubmitting}
                >
                  Reject
                </button>
              </div>
            </div>
            {error && (
              <p className="signoff-control__error" role="alert">
                {error}
              </p>
            )}
          </>
        )}
      </div>
    </section>
  );
}
