# Project agents

Specialized subagents for working on this repo, invocable from Claude Code. They encode this
project's conventions so a session gets consistent help without re-explaining the rules each
time. Definitions live in this folder as `<name>.md` (frontmatter + system prompt).

| Agent | Use it to… | Modifies code? |
|---|---|---|
| **pipeline-engineer** | Extend the Nextflow pipeline, DB schema, or CDK infra while respecting provenance/validation conventions | Yes (Read/Edit/Write/Bash) |
| **compliance-auditor** | Audit traceability & validation against the ISO 15189 / NATA *patterns* the project claims — provenance, insert-only invariants, validation honesty, ADR/change control | No — read-only reviewer |
| **security-reviewer** | Review AWS IAM, S3 exposure, secrets, container supply-chain, dependencies, CI safety — before a deploy or before going public | No — read-only reviewer |

## When to reach for which

- **Building a feature** → `pipeline-engineer`.
- **Before a release or showing the repo to someone** → `compliance-auditor`.
- **Before `cdk deploy` or `gh repo edit --visibility public`** → `security-reviewer`.

The two reviewers are deliberately **read-only**: they surface findings with evidence and
severity, and leave the fix to you (or to `pipeline-engineer`). Auditors that quietly "fix"
what they review can't be trusted to report honestly.

## Adding another agent

Copy an existing file, keep the frontmatter shape (`name`, `description`, optional `tools`),
and write a system prompt that (1) points the agent at `CLAUDE.md` + the `clinical-genomics`
skill first, and (2) states plainly whether it may modify code. Ideas not yet built:
a `data-privacy-reviewer` (for when real patient data replaces GIAB), a `release-validator`
(gate that re-runs `hap.py` validation on version bumps).
