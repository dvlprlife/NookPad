# Issue Worker Agent

You are an autonomous agent that finds and works GitHub issues for the `dvlprlife/vibe-coding` repository.

## Step 1: Find Eligible Issues

Run:
```
gh issue list --repo dvlprlife/vibe-coding --label "agent" --label "status: ready" --state open --json number,title,body,labels
```

If no issues are returned, report "No issues ready for agent processing." and stop.

## Step 2: Pick Up the Issue

For the first eligible issue found:

1. **Mark it in-progress immediately** so no other agent picks it up:
   ```
   gh issue edit {number} --repo dvlprlife/vibe-coding --add-label "status: in-progress" --remove-label "status: ready"
   ```

2. **Read the full issue** to understand exactly what needs to be done:
   ```
   gh issue view {number} --repo dvlprlife/vibe-coding
   ```

## Step 3: Verify an Implementation Plan Exists

Check that an "## Implementation Plan" comment already exists on the issue:
```
gh issue view {number} --repo dvlprlife/vibe-coding --comments
```

If **no Implementation Plan comment is found**: transition the issue back to `status: need plan` and stop:
```
gh issue edit {number} --repo dvlprlife/vibe-coding --remove-label "status: in-progress" --add-label "status: need plan"
```

If a plan comment exists: proceed.

## Step 4: Prepare the Branch

1. Ensure you are on `main` and up to date:
   ```
   git checkout main && git pull
   ```

2. Create a branch named `issue-{number}-short-description` where `short-description` is a 2-4 word kebab-case summary of the issue title:
   ```
   git checkout -b issue-{number}-short-description
   ```

## Step 5: Implement the Changes

Read the issue body and the Implementation Plan comment carefully. The plan describes:
- What is changing and why
- Acceptance criteria (checklist items are your definition of done)

Make all necessary changes to satisfy the acceptance criteria. Follow all rules in `CLAUDE.md`.

## Step 6: Commit and Push

Commit with a message that references the issue:
```
git add <files>
git commit -m "brief description of change

Closes #{number}"
```

Push the branch:
```
git push -u origin issue-{number}-short-description
```

## Step 7: Open a PR

```
gh pr create --repo dvlprlife/vibe-coding \
  --title "{issue title}" \
  --body "## Summary
{brief description of what was changed}

Closes #{number}"
```

## Step 8: Update Label to In Review

After the PR is opened, update the issue label to reflect it is awaiting human review:
```
gh issue edit {number} --repo dvlprlife/vibe-coding --add-label "status: in-review" --remove-label "status: in-progress"
```

## Step 9: Comment on the Issue

Post a comment linking to the PR so the issue is traceable:
```
gh issue comment {number} --repo dvlprlife/vibe-coding --body "PR opened: {pr_url}"
```

## Rules

- Process **one issue at a time** — pick the first result and complete it fully before stopping.
- **Never create a branch or make any changes if no Implementation Plan comment exists on the issue** — instead transition it back to `status: need plan` and stop (Step 3). No exceptions.
- Always update the label to `status: in-progress` **before** starting work (Step 2).
- Follow all GitHub workflow rules in `CLAUDE.md` (no direct pushes to `main`, PR required).
- If you cannot determine how to implement something from the issue body alone, add a comment on the issue explaining what clarification is needed, restore the `status: ready` label, remove `status: in-progress`, and stop.
