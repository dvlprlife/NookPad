# Agent Workflow

This document describes the full lifecycle of an issue through the agent system for the `dvlprlife/vibe-coding` repository.

## Agents

| Agent | File | Purpose |
|-------|------|---------|
| Repo Check | `repo-check.md` | Ensures all required labels exist in the repo |
| Issue Planner | `issue-planner.md` | Reviews issues and writes implementation plans |
| Issue Worker | `issue-worker.md` | Implements changes, commits, and opens a PR |

---

## Issue Lifecycle

### 1. Setup (Repo Check Agent)
Run once before using the other agents to ensure all required labels exist.

```
agent: repo-check
```

---

### 2. Issue Created by Human
A human creates an issue and applies the following labels to queue it for agent processing:

| Label | Purpose |
|-------|---------|
| `agent` | Marks the issue for agent pickup |
| `status: need plan` | Signals the issue planner to review it |

---

### 3. Planning (Issue Planner Agent)
The planner finds issues labeled `agent` + `status: need plan`.

**Happy path — enough information:**
1. Posts an `## Implementation Plan` comment (file-by-file changes + acceptance criteria)
2. Removes `status: need plan`, adds `status: ready`

**Failure path — not enough information:**
1. Adds `status: follow up` and `human` labels, removes `agent`
2. Posts a `## Needs Clarification` comment explaining what is missing
3. Stops — human intervention required

---

### 4. Implementation (Issue Worker Agent)
The worker finds issues labeled `agent` + `status: ready`.

1. Swaps `status: ready` → `status: in-progress`
2. Verifies an `## Implementation Plan` comment exists — if not, transitions back to `status: need plan` and stops
3. Creates a branch, implements the changes, commits, and pushes
4. Opens a PR referencing the issue
5. Swaps `status: in-progress` → `status: in-review`
6. Posts a comment on the issue linking to the PR

---

### 5. Review (Human)
A human reviews the PR. On merge the issue is closed.

---

## Label State Machine

```
[human creates issue]
        │
        ▼
  agent + status: need plan
        │
        ▼ (issue planner)
        ├─── not enough info ──▶ status: follow up + human  (awaits human)
        │
        ▼
  agent + status: ready
        │
        ▼ (issue worker)
  agent + status: in-progress
        │
        ├─── no plan found ──▶ status: need plan  (replanner picks up)
        │
        ▼
  agent + status: in-review
        │
        ▼ (human merges PR)
  issue closed
```

---

## Required Labels

| Label | Color | Description |
|-------|-------|-------------|
| `agent` | `#0075ca` | Issue is assigned to agent processing |
| `status: need plan` | `#fbca04` | Awaiting implementation plan |
| `status: ready` | `#0e8a16` | Planned and ready for the worker |
| `status: in-progress` | `#e4e669` | Worker is actively implementing |
| `status: in-review` | `#d93f0b` | PR open, awaiting human review |
| `status: follow up` | `#c5def5` | Needs follow-up after human review |
| `human` | `#b60205` | Requires human attention |
