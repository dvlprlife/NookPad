# Task List Instructions

## Files
- `lists/tasks.md` — the active task list
- `lists/ideas.md` — a running list of ideas
- `lists/shopping.md` — shopping list organized by store
- `cheatsheets/` — reference cheatsheets (raspberry-pi, tmux)
- `server.py` — dashboard web server (port 6969)
- `dashboard.service` — systemd service file for the dashboard

## Table Structure
| **Column** | **Description** |
|--------|-------------|
| `#` | Unique task number, increment sequentially |
| `Status` | `✅` when complete, `⚠️` when overdue (due date has passed), `&nbsp;` when incomplete |
| `Priority` | `High`, `Medium`, or `Low` |
| `Due Date` | Format: `YYYY-MM-DD HH:MM` (24h). Default time is `00:00` if none given |
| `Task` | Short description of the task |
| `Notes` | Optional context or details |
| `Parent` | Task `#` of the parent task if this is a sub-task; blank for top-level tasks |

## Formatting
- Column headings must be **bold** using `**heading**` syntax.
- Tasks are sorted by due date, then priority (High → Medium → Low) within the same date.
- Renumber `#` sequentially after any sort.
- When renumbering, update any `Parent` column values to match the new `#` of the referenced task.

## Column Order
`#` | `Status` | `Priority` | `Due Date` | `Task` | `Notes` | `Parent`

## Sub-tasks
- A sub-task has its parent's task `#` in the `Parent` column.
- In the dashboard, sub-tasks are displayed indented (↳) immediately below their parent task.
- Sub-tasks are otherwise treated like any other task (same sorting, completion, deletion rules).

## Rules
- **Adding a task**: Append a new row, increment `#`, set Status to `&nbsp;`, assign a Priority, use `00:00` if no time is specified.
- **Completing a task**: Remove the row from the active task list and move it to the **Completed Tasks** section at the bottom of `tasks.md`, setting Status to `✅` and Date Completed to today's date (`YYYY-MM-DD`). Renumber both tables sequentially after the move.
- **Completed Tasks section**: A separate table at the bottom of `tasks.md` under a `## Completed Tasks` heading. Same column structure as the active task list, plus an additional `Date Completed` column (`YYYY-MM-DD`) at the end. Numbers are independent of the active list (start at 1, increment sequentially).
- **Due date format**: Always `YYYY-MM-DD HH:MM` in 24-hour format.
- **Overdue tasks**: Use `⚠️` in the Status column for incomplete tasks whose due date has passed (strictly before today's date). Tasks due today are not overdue. Always update overdue statuses automatically without asking the user.
- **Status alignment**: Always use `&nbsp;` (not empty) for incomplete tasks to keep columns aligned.
- **Never delete tasks manually**: Move to Completed Tasks instead of removing rows. The dashboard delete button is the exception — it permanently removes a task after browser confirmation.
- **Editing a task**: Update the row fields (Due Date, Priority, Task, Notes) in-place, re-sort by due date then priority, and renumber. Re-evaluate Status (overdue or not) based on the new due date.
- **Parent due date sync**: After adding or editing a sub-task, automatically set the parent task's due date to the latest due date among all its sub-tasks. Re-evaluate the parent's Status after updating.
- **Notes are optional**: Leave as blank space if none provided, do not use `&nbsp;` in Notes.

## Ideas (`ideas.md`)
- Format: `## {id} | {YYYY-MM-DD} | {description} | {parent_id}`
- `{parent_id}` is the ID of the parent idea for sub-ideas, or blank for top-level ideas.
- Sub-points are optional bullet lists beneath the heading.
- IDs increment sequentially, never reuse or delete an idea.
- Date added uses format `YYYY-MM-DD`.
- Sub-ideas display indented (↳) under their parent in the dashboard.
- Ideas can be edited (description only; ID and date are preserved) or deleted via the dashboard.
- Deleting an idea also deletes its sub-ideas (cascade). IDs of deleted ideas are never reused.

## Shopping (`shopping.md`)
- Organized by store: `## {Store Name}` headings.
- Items are bullet points: `- {item}`.
- Add new store sections at the end if the store doesn't exist yet.
- Removing a purchased item deletes the bullet; keep the store heading even if empty.

## User Guide (`DASHBOARD.md`)
- `DASHBOARD.md` is the user-facing guide for the dashboard.
- **Always update `DASHBOARD.md` when dashboard functionality is added or changed** — new features, changed behavior, new endpoints, removed features, etc.

## Dashboard (`server.py`)
- Serves a read/write dashboard at `http://localhost:6969`.
- Panels: Tasks, Shopping, Ideas, and Cheatsheet links.
- Supports adding tasks (`/add-task`), shopping items (`/add-shopping`), and ideas (`/add-idea`) via POST.
- Supports completing tasks (`/complete-task`), editing tasks (`/edit-task`), deleting tasks (`/delete-task`), and removing purchased shopping items (`/complete-shopping`) via POST.
- Supports editing ideas (`/edit-idea`) and deleting ideas (`/delete-idea`) via POST.
- Supports permanently deleting completed tasks (`/delete-completed-task`) via POST — browser confirmation required.
- Deleting an active task removes it permanently (no archive) — browser confirmation required.
- Editing a task updates fields in-place, re-sorts, and recalculates overdue status.
- On task rows: ✓ (complete) is always visible; ✎ (edit) and ✕ (delete) appear on hover.
- On idea rows: ✎ (edit) and ✕ (delete) appear on hover.
- Dashboard layout: Tasks (top-left), Ideas (bottom-left), Shopping (right, full height).
- Sub-tasks are displayed indented under their parent task in the Tasks panel.
- Completing a task via the dashboard follows the same rules as completing one manually (move to Completed Tasks, set Date Completed to today, renumber both tables).
- Header nav links (left to right): Completed Tasks, then cheatsheet links.
- Completed Tasks page (`/completed`): lists all completed tasks with priority, due date, task, notes, and date completed. ✕ (delete) appears on hover to permanently remove a row; redirects back to `/completed` after deletion.
- To install as a service: `sudo cp dashboard.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now dashboard`
- To restart after changes: `sudo systemctl restart dashboard`
