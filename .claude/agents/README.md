# Project agents

Specialized subagents for working on this repo, invocable from Claude Code. They encode this
project's conventions so a session gets consistent help without re-explaining the rules each
time. Definitions live in this folder as `<name>.md` (frontmatter + system prompt).

| Agent | Use it to… | Modifies files? |
|---|---|---|
| **pipeline-engineer** | Extend the Nextflow pipeline, DB schema, or CDK infra while respecting provenance/validation conventions | Yes — code |
| **test-engineer** | Write/maintain pytest + jest + stub coverage; a bug fix starts with a failing test | Yes — tests/fixtures only |
| **documentation-writer** | Keep README/docs/ADRs/CLAUDE.md accurate, honest, and beginner-friendly | Yes — docs only |
| **compliance-auditor** | Audit traceability & validation *process* against the ISO 15189 / NATA patterns the project claims | No — read-only |
| **security-reviewer** | Review AWS IAM, S3 exposure, secrets, container supply-chain, deps, CI safety | No — read-only |
| **validation-reviewer** | Review the analytical-validation *science* — hap.py methodology, metric correctness, honesty of claims | No — read-only |

## When to reach for which

- **Building a feature** → `pipeline-engineer` (+ `test-engineer` for coverage).
- **Docs drifted from the code** → `documentation-writer`.
- **Before a release or showing the repo to someone** → `compliance-auditor` + `validation-reviewer`.
- **Before `cdk deploy` or `gh repo edit --visibility public`** → `security-reviewer`.

## Two families: builders and reviewers

- **Builders** (`pipeline-engineer`, `test-engineer`, `documentation-writer`) change files, each
  in its own lane — code, tests, docs — so responsibilities don't blur.
- **Reviewers** (`compliance-auditor`, `security-reviewer`, `validation-reviewer`) are
  deliberately **read-only**: they surface findings with evidence and severity and leave the fix
  to a builder. A reviewer that quietly "fixes" what it reviews can't be trusted to report
  honestly. Note the clean split among them: compliance = *process/traceability*, security =
  *threat surface*, validation = *the science of the accuracy claims*.

## Adding another agent

Copy an existing file, keep the frontmatter shape (`name`, `description`, optional `tools`),
and write a system prompt that (1) points the agent at `CLAUDE.md` + the `clinical-genomics`
skill first, and (2) states plainly whether it may modify files and in which lane. Ideas not
yet built: a `data-privacy-reviewer` (for when real patient data replaces GIAB), a
`release-validator` (gate that re-runs `hap.py` validation on version bumps).
