# Issue Tracker

## Location

GitHub: `browser-use`

## Workflow

Issues are created and managed via the `gh` CLI. External PRs are also pulled into the triage queue and processed through the same labels and states as issues.

## Commands

```bash
# List open issues
gh issue list

# Create an issue
gh issue create --title "..." --body "..."

# View an issue
gh issue view <number>

# List open PRs
gh pr list

# View a PR
gh pr view <number>
```

## External PRs as request surface

Enabled. External PRs are treated as incoming requests and triaged alongside issues.
