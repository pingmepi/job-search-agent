# Check Codex Review Comments (Read-Only)

Show all Codex review comments on the current branch's PR without making changes.

## Steps

1. **Find the PR:**
   ```
   BRANCH=$(git branch --show-current)
   gh pr list --head "$BRANCH" --json number,url --jq '.[0]'
   ```
   If no PR exists, stop and tell the user.

2. **Fetch all review comments:**
   ```
   gh api repos/pingmepi/job-search-agent/pulls/{number}/comments --paginate
   gh api repos/pingmepi/job-search-agent/pulls/{number}/reviews --paginate
   ```

3. **Display comments grouped by file:**
   For each comment show:
   - File path and line number
   - The comment body (suggestion/feedback)
   - Whether it looks actionable or informational

4. **Summary:**
   - Total comments: X
   - Actionable: Y (code changes needed)
   - Informational: Z (no changes needed)
   - Suggest running `/review-fix` to auto-address actionable comments

**DO NOT modify any files. This is a read-only command.**
