# Review & Fix Codex Comments

Read all Codex review comments on the current branch's PR, fix them, and push.

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

3. **For each comment with a code suggestion or actionable feedback:**
   - Read the referenced file and line range
   - Understand the suggestion (Codex often includes code diffs)
   - Apply the fix if valid
   - If the suggestion is wrong or not applicable, note why (do NOT blindly apply everything)

4. **After all fixes applied:**
   - Run `python -m ruff check .` to ensure no new lint issues
   - Run `python -m pytest tests/ -q --tb=short -x` to ensure tests pass
   - Stage changed files and commit: `fix: address Codex review feedback`
   - Push to the branch

5. **Report:**
   - List each comment addressed with file:line and what was done
   - List any comments skipped with reasoning
   - Note: Codex will automatically re-review after push
