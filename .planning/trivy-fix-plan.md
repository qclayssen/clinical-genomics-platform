I'll help you fix the Trivy vulnerability scan failures. Let me start by getting the failure logs to identify the specific vulnerabilities.

<details>
<summary>🔍 Expanding: Fetching Trivy failure logs from PR #48</summary>

```bash
gh run view <run-id> --log-failed | grep -A 50 CRITICAL
```
</details>

Let me first find the latest run on PR #48:

```bash
gh run list --limit 10 --head refs/pull/48/merge --json databaseId,headSha --jq '.[0].databaseId'
```

I'll execute that to get the run ID.