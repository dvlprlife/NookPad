# NookPad

A self-hosted web dashboard for tasks, shopping lists, and ideas — one Python file, no database.

## Features

- Tasks with priorities, due dates, overdue flagging, categories, sub-tasks, and a completed history.
- Shopping list organised by store.
- Ideas with sub-ideas and optional notes.
- Quick-capture notes on a dedicated page.
- Category management page.
- Cheatsheet viewer (any markdown file in `cheatsheets/` is rendered read-only).
- Auto-refresh every 30 seconds; no build step, no database.

## Requirements

- Python 3 — standard library only, no `pip install` needed.
- Linux with systemd if you want to install as a background service. The manual `python3` run works on any OS with Python 3.

## Installation

1. Clone the repo into your home directory:

   ```
   git clone https://github.com/dvlprlife/NookPad.git ~/NookPad
   cd ~/NookPad
   ```

2. (Service install only) Edit `dashboard.service` and replace `USERNAME` with your Linux user on the `ExecStart`, `WorkingDirectory`, and `User=` lines.

3. Install as a systemd service:

   ```
   sudo cp dashboard.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now dashboard
   ```

## Running

The dashboard runs as a background service and starts automatically on boot.

| Command | Description |
|---|---|
| `sudo systemctl start dashboard` | Start the server |
| `sudo systemctl stop dashboard` | Stop the server |
| `sudo systemctl restart dashboard` | Restart the server |
| `sudo systemctl status dashboard` | Check if it's running |

### Running Manually (without the service)

If you want to run the server directly in a terminal instead:

```
python3 ~/NookPad/server.py
```

Press `Ctrl+C` to stop it. If you get an "address already in use" error when restarting, kill the process still holding the port:

```
sudo fuser -k 6969/tcp
```

To keep it running after closing the terminal, use a tmux session:

```
tmux new -s dashboard
python3 ~/NookPad/server.py
# Press Ctrl+B then D to detach
```

To reattach later: `tmux attach -t dashboard`

## Access

Open in any browser:

```
http://localhost:6969
```

To reach the dashboard from other devices on your LAN, replace `localhost` with the host machine's IP address (e.g. `http://192.168.1.42:6969`).

The page auto-refreshes every 30 seconds.

## Usage

Each panel has a **+ Add** button in the header to add new entries without editing the files directly.

### Tasks
- Click **+ Add** in the Tasks panel to open the form
- Fields: Due Date, Priority (High / Medium / Low), Category (optional), Task, Notes, Parent Task (optional)
- Select a **Parent Task** to create a sub-task — it will appear indented (↳) directly below its parent in the list
- When a sub-task is added or edited, the parent task's due date automatically updates to the earliest due date among all its sub-tasks
- Tasks are grouped by **Category** in the panel — groups are ordered by each category's Sort Order (ascending), with ties broken alphabetically by description. Tasks without a category appear under a **None** group that always sorts last
- Sub-tasks stay under their parent's group regardless of their own category
- Click a category header to collapse or expand that group's rows; all groups start expanded on page load
- Click the **✓** button on any task row to mark it complete — it moves to the Completed Tasks section in `tasks.md` with today's date
- Sub-tasks appear indented (↳) under their parent on the Completed Tasks page as well
- Hover over any task row to reveal the **✎** (edit) and **✕** (delete) buttons
- **✎** opens an edit modal pre-filled with the task's due date, priority, category, name, notes, and parent task
- **✕** permanently deletes the task — a confirmation dialog appears first. If a parent task is deleted while sub-tasks exist, those sub-tasks remain but lose their parent relationship

### Completed Tasks
- Click the **Completed Tasks** link in the header (left of the cheatsheet links) to open the completed tasks page
- Lists all completed tasks with their priority, original due date, notes, and date completed
- Rows are grouped by **Category** using the same ordering as the active Tasks panel; click a category header to collapse or expand that group
- Hover over any row to reveal the **↩** (reopen) and **✕** (delete) buttons
- **↩** moves the task back to the active list, re-evaluating its overdue status based on the original due date
- **✕** permanently removes the completed task — a confirmation dialog appears first

### Agenda
- Click the **Agenda** link in the header to open a read-only view of upcoming work
- Active tasks are grouped into sections: **Overdue**, **Today**, **Tomorrow**, then each of the next 12 days, and finally **Unscheduled** for tasks without a due date
- Sections with no tasks are omitted; `Overdue` sorts oldest due-date first, all other sections sort by priority (High → Medium → Low) then task name
- No edit or complete controls — use the main dashboard to act on a task

### Shopping
- Click **+ Add** in the Shopping panel to open the form
- Fields: Store (autocompletes existing stores), Item
- Click the **✓** button next to any item to mark it as purchased — it is removed from the list

### Ideas
- Click **+ Add** in the Ideas panel to open the form
- Fields: Idea description, Notes (optional), Parent Idea (optional)
- Select a **Parent Idea** to create a sub-idea — it will appear indented (↳) directly below its parent
- The ID and date are assigned automatically
- Notes appear below the idea title in a smaller, muted font
- Hover over any idea to reveal the **✎** (edit) and **✕** (delete) buttons
- **✎** opens an edit modal pre-filled with the current description and notes
- **✕** permanently deletes the idea and any of its sub-ideas — a confirmation dialog appears first

### Notes
- Click the **Notes** link in the header to open the notes page
- A free-form scratchpad for quick thoughts, URLs, reminders — anything that doesn't fit the structured Tasks / Shopping / Ideas buckets
- Click **+ Add** to open a modal with a single text area; submitting creates a new note stamped with the current date and time
- Notes are displayed newest-first; IDs are assigned automatically and never reused
- Hover over any note to reveal the **✎** (edit) and **✕** (delete) buttons
- **✎** opens an edit modal pre-filled with the note's body; ID and timestamp are preserved
- **✕** permanently deletes the note — a confirmation dialog appears first

## How It Works

- Reads `lists/tasks.md`, `lists/shopping.md`, `lists/ideas.md`, and `lists/notes.md` directly on each page load
- Writes changes back to those files immediately when forms are submitted
- Any manual edits to those files will appear on the next refresh (within 30 seconds)
- No build step or database required

## Uninstalling

```
sudo systemctl stop dashboard
sudo systemctl disable dashboard
sudo rm /etc/systemd/system/dashboard.service
sudo systemctl daemon-reload
```
