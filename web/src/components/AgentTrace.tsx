import type { AgentTraceStep } from "../api/client";

interface AgentTraceProps {
  trace: AgentTraceStep[];
}

/**
 * Renders the agent's full Thought → Action → Observation trace so a
 * clinician can audit exactly what it looked up (ClinVar, gnomAD, gene
 * annotations) before trusting the classification. This is the deliberate
 * transparency point of the whole feature — never collapse it into a
 * black box or a "show details" toggle that hides it by default.
 */
export function AgentTrace({ trace }: AgentTraceProps) {
  if (trace.length === 0) {
    return (
      <section className="agent-trace" aria-label="Agent trace">
        <h2>Agent trace</h2>
        <p className="agent-trace__empty">No reasoning steps were recorded for this assessment.</p>
      </section>
    );
  }

  return (
    <section className="agent-trace" aria-label="Agent trace">
      <h2>Agent trace</h2>
      <p className="agent-trace__subtitle">
        Every step the agent took, in order — including any tool it called and what came back.
        Review this before trusting the classification below.
      </p>
      <ol className="agent-trace__list">
        {trace.map((step, index) => (
          <li key={index} className="agent-trace__step">
            <div className="agent-trace__step-header">
              <span className="agent-trace__step-number">Step {index + 1}</span>
              <span className="agent-trace__step-type">{step.type}</span>
              {step.tool_name && <span className="agent-trace__step-tool">{step.tool_name}</span>}
            </div>
            <p className="agent-trace__content">{step.content}</p>
            {(step.tool_input || step.tool_output) && (
              <div className="agent-trace__io">
                {step.tool_input && (
                  <div>
                    <h3>Tool input</h3>
                    <pre>{JSON.stringify(step.tool_input, null, 2)}</pre>
                  </div>
                )}
                {step.tool_output && (
                  <div>
                    <h3>Tool output</h3>
                    <pre>{JSON.stringify(step.tool_output, null, 2)}</pre>
                  </div>
                )}
              </div>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
