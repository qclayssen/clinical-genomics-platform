#!/usr/bin/env bash
# One-time helper to create a PRIVATE GitHub repo and push this project.
#
# Auth is the one step that must be done by you (Claude can't authenticate on your
# behalf). This script checks you're logged in, then creates + pushes.
#
#   1. gh auth login          # once, interactive — pick GitHub.com > HTTPS > browser
#   2. ./scripts/push_to_github.sh
#
# Re-running after the first push just pushes new commits.
set -euo pipefail

REPO_NAME="${1:-clinical-genomics-platform}"
VISIBILITY="--private"          # change to --public when you're ready to show it off

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# 0. gh present?
if ! command -v gh >/dev/null; then
  echo "✗ GitHub CLI (gh) not found. Install it:  brew install gh"; exit 1
fi

# 1. Authenticated?
if ! gh auth status >/dev/null 2>&1; then
  cat <<'MSG'
✗ Not logged in to GitHub yet. Run this once, then re-run this script:

    gh auth login

  Choose:  GitHub.com  →  HTTPS  →  "Login with a web browser"
MSG
  exit 1
fi

# 2. Modern default branch name
git branch -M main

# 3. Create the repo if it doesn't exist, wire the remote, and push.
if git remote get-url origin >/dev/null 2>&1; then
  echo "▸ 'origin' already set to: $(git remote get-url origin)"
  echo "▸ pushing current branch…"
  git push -u origin main
else
  OWNER="$(gh api user --jq .login)"
  echo "▸ creating ${VISIBILITY#--} repo ${OWNER}/${REPO_NAME} and pushing…"
  gh repo create "${REPO_NAME}" ${VISIBILITY} --source=. --remote=origin --push
fi

echo "✓ Done. Repo: $(gh repo view --json url --jq .url 2>/dev/null || echo '(see github.com)')"
