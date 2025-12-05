#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This script demonstrates how to configure branch protection for `main`
# using the GitHub CLI. It is NOT executed automatically by CI.
# Review and adjust the JSON payload before running.
#
# Usage:
#   GH_TOKEN=ghp_xxx ./tools/apply_branch_protection.sh
#
# Requirements:
#   - GitHub CLI (`gh`) authenticated with repo admin permissions.
#   - The `jq` utility available in PATH.
#
# NOTE: Remove the `--dry-run` flag once you are ready to apply the policy.

set -euo pipefail

REPO_SLUG="${REPO_SLUG:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
BRANCH="${BRANCH:-main}"

PATCH_PAYLOAD=$(
  jq -n \
    --arg branch "$BRANCH" \
    '{
      required_pull_request_reviews: {
        dismiss_stale_reviews: true,
        required_approving_review_count: 1,
        require_code_owner_reviews: false
      },
      required_status_checks: {
        strict: true,
        checks: [
          { "context": "CI" },
          { "context": "Secret Scan" }
        ]
      },
      enforce_admins: true,
      required_conversation_resolution: true,
      restrictions: null,
      allow_force_pushes: false,
      allow_deletions: false,
      block_creations: false,
      required_linear_history: false,
      lock_branch: false,
      allow_fork_syncing: true,
      required_signatures: false
    }'
)

echo "Applying branch protection to $REPO_SLUG:$BRANCH"
echo "$PATCH_PAYLOAD" | jq .

# Dry-run preview (remove --dry-run to apply)
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/$REPO_SLUG/branches/$BRANCH/protection" \
  --input - \
  --dry-run <<<"$PATCH_PAYLOAD"

echo "[NOTE] Remove --dry-run above once you confirm the payload."
