# NookPad Instructions

## GitHub Workflow
- **Before starting any change**: Draft the issue title and body, then show it to the user for review and approval before creating it. The issue must be detailed enough to be worked on independently — include what is changing, why, and any relevant context or acceptance criteria.
- **Create the issue**: Only after the user approves the draft, create it with `gh issue create`.
- **Create a branch**: Name it `issue-{number}-short-description` off `main`.
- **Commit changes** to that branch.
- **When done**: Open a PR with `gh pr create` referencing the issue (e.g. `Closes #123` in the body).
- Never push directly to `main`.

## Files
- `lists/tasks.md` — the active task list
- `lists/ideas.md` — a running list of ideas
- `lists/notes.md` — quick-capture free-form notes
- `lists/shopping.md` — shopping list organized by store
- `lists/categories.md` — task categories (code, description, sort order)
- `cheatsheets/` — reference cheatsheets (raspberry-pi, tmux)
- `server.py` — dashboard web server (port 6969)
- `dashboard.service` — systemd service file for the dashboard

## Table Structure
| **Column** | **Description** |
|--------|-------------|
| `#` | Display number, renumbered sequentially after any sort |
| `Status` | `✅` when complete, `⚠️` when overdue (due date has passed), `&nbsp;` when incomplete |
| `Priority` | `High`, `Medium`, `Low`, or `None`. `None` displays as blank on the dashboard |
| `Due Date` | Format: `YYYY-MM-DD HH:MM` (24h). Default time is `00:00` if none given |
| `Task` | Short description of the task |
| `Notes` | Optional context or details |
| `Category` | Category code from `categories.md`; blank if uncategorized |
| `Parent` | Internal `ID` of the parent task if this is a sub-task; blank for top-level tasks |
| `ID` | Permanent internal identifier. Assigned at creation, never changes, never reused |

## Formatting
- Column headings must be **bold** using `**heading**` syntax.
- Tasks are sorted by due date, then priority (High → Medium → Low) within the same date.
- Renumber `#` sequentially after any sort. `Parent` and `ID` values are never renumbered.

## Column Order
`#` | `Status` | `Priority` | `Due Date` | `Task` | `Notes` | `Category` | `Parent` | `ID`

## Sub-tasks
- A sub-task has its parent's `ID` in the `Parent` column.
- In the dashboard, sub-tasks are displayed indented (↳) immediately below their parent task.
- Sub-tasks are otherwise treated like any other task (same sorting, completion, deletion rules).

## Rules
- **Adding a task**: Append a new row, increment `#`, assign the next `ID` (max across all active + completed tasks + 1), set Status to `&nbsp;`, assign a Priority, use `00:00` if no time is specified.
- **Completing a task**: Remove the row from the active task list and move it to the **Completed Tasks** section at the bottom of `tasks.md`, setting Status to `✅` and Date Completed to today's date (`YYYY-MM-DD`). Renumber both tables sequentially after the move. The task's `ID` is preserved.
- **Completed Tasks section**: A separate table at the bottom of `tasks.md` under a `## Completed Tasks` heading. Same column structure as the active task list, plus an additional `Date Completed` column (`YYYY-MM-DD`) at the end. Numbers are independent of the active list (start at 1, increment sequentially). `ID` and `Parent` values are preserved.
- **Due date format**: Always `YYYY-MM-DD HH:MM` in 24-hour format.
- **Overdue tasks**: Use `⚠️` in the Status column for incomplete tasks whose due date has passed (strictly before today's date). Tasks due today are not overdue. Always update overdue statuses automatically without asking the user.
- **Status alignment**: Always use `&nbsp;` (not empty) for incomplete tasks to keep columns aligned.
- **Never delete tasks manually**: Move to Completed Tasks instead of removing rows. The dashboard delete button is the exception — it permanently removes a task after browser confirmation.
- **Editing a task**: Update the row fields (Due Date, Priority, Task, Notes) in-place, re-sort by due date then priority, and renumber. Re-evaluate Status (overdue or not) based on the new due date.
- **Parent due date sync**: After adding or editing a sub-task, automatically set the parent task's due date to the nearest (earliest) due date among all its sub-tasks. Re-evaluate the parent's Status after updating.
- **Notes are optional**: Leave as blank space if none provided, do not use `&nbsp;` in Notes.
- **Category is optional**: Leave as blank space if none provided. Use the category code from `categories.md`.

## Ideas (`ideas.md`)
- Format: `## {id} | {YYYY-MM-DD} | {description} | {parent_id}`
- `{parent_id}` is the ID of the parent idea for sub-ideas, or blank for top-level ideas.
- Notes are stored as a `notes: {text}` line in the block body, before any bullet sub-points.
- Sub-points are optional bullet lists beneath the heading (after the notes line if present).
- IDs increment sequentially, never reuse or delete an idea.
- Date added uses format `YYYY-MM-DD`.
- Sub-ideas display indented (↳) under their parent in the dashboard.
- Ideas can be edited (description and notes; ID and date are preserved) or deleted via the dashboard.
- Deleting an idea also deletes its sub-ideas (cascade). IDs of deleted ideas are never reused.

## Notes (`notes.md`)
- Format per note: `## {id} | {YYYY-MM-DD HH:MM}` heading followed by free-form body text.
- `id` is a monotonically increasing integer, assigned by the server. Never reused, even after deletion.
- Timestamp is assigned by the server at creation time (local time, `YYYY-MM-DD HH:MM`).
- Notes are stored and displayed newest-first.
- No parent/child relationships — deliberately flat.
- Notes can be edited (body only; ID and timestamp are preserved) or deleted via the `/notes` page.

## Shopping (`shopping.md`)
- Organized by store: `## {Store Name}` headings.
- Items are bullet points: `- {item}`.
- Add new store sections at the end if the store doesn't exist yet.
- Removing a purchased item deletes the bullet; keep the store heading even if empty.

## User Guide (`README.md`)
- `README.md` is the user-facing guide for the dashboard.
- **Always update `README.md` when dashboard functionality is added or changed** — new features, changed behavior, new endpoints, removed features, etc.

## Dashboard (`server.py`)
- Serves a read/write dashboard at `http://localhost:6969`.
- Panels: Tasks, Shopping, Ideas, and Cheatsheet links.
- Supports adding tasks (`/add-task`), shopping items (`/add-shopping`), and ideas (`/add-idea`) via POST.
- Supports completing tasks (`/complete-task`), editing tasks (`/edit-task`), deleting tasks (`/delete-task`), and removing purchased shopping items (`/complete-shopping`) via POST.
- Supports editing ideas (`/edit-idea`) and deleting ideas (`/delete-idea`) via POST.
- Supports adding, editing, and deleting notes (`/add-note`, `/edit-note`, `/delete-note`) via POST.
- Supports permanently deleting completed tasks (`/delete-completed-task`) via POST — browser confirmation required.
- Deleting an active task removes it permanently (no archive) — browser confirmation required.
- Editing a task updates fields in-place, re-sorts, and recalculates overdue status.
- On task rows: ✓ (complete) is always visible; ✎ (edit) and ✕ (delete) appear on hover.
- On idea rows: ✎ (edit) and ✕ (delete) appear on hover.
- Dashboard layout: Tasks (top-left), Ideas (bottom-left), Shopping (right, full height).
- Sub-tasks are displayed indented under their parent task in the Tasks panel.
- Completing a task via the dashboard follows the same rules as completing one manually (move to Completed Tasks, set Date Completed to today, renumber both tables).
- Header nav links (left to right): Completed Tasks, Agenda, Categories, Notes, then cheatsheet links.
- Completed Tasks page (`/completed`): lists all completed tasks with priority, due date, task, notes, and date completed. ✕ (delete) appears on hover to permanently remove a row; redirects back to `/completed` after deletion.
- To install as a service: `sudo cp dashboard.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now dashboard`
- To restart after changes: `sudo systemctl restart dashboard`

## Categories (`categories.md`)
- Format: `| **Code** | **Description** | **Sort Order** |` table in `lists/categories.md`.
- `Code` is a short identifier (e.g. `WORK`, `HOME`). Used as the value stored in task rows.
- `Description` is the human-readable label shown in dropdowns.
- `Sort Order` is an integer controlling display order in dropdowns and the categories page.
- Managed via the `/categories` dashboard page (add, edit, delete).
- Categories can be added, edited, or deleted via POST endpoints: `/add-category`, `/edit-category`, `/delete-category`.
