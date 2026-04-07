# Dashboard User Guide

A live web dashboard that displays your tasks, shopping list, and ideas.

## Access

Open in any browser on your local network:

```
http://192.168.50.11:6969
```

The page auto-refreshes every 30 seconds.

## Starting & Stopping

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
python3 ~/documents/vibe-coding/tasklist/server.py
```

Press `Ctrl+C` to stop it. If you get an "address already in use" error when restarting, kill the process still holding the port:

```
sudo fuser -k 6969/tcp
```

To keep it running after closing the terminal, use a tmux session:

```
tmux new -s dashboard
python3 ~/documents/vibe-coding/tasklist/server.py
# Press Ctrl+B then D to detach
```

To reattach later: `tmux attach -t dashboard`

## Uninstalling the Service

```
sudo systemctl stop dashboard
sudo systemctl disable dashboard
sudo rm /etc/systemd/system/dashboard.service
sudo systemctl daemon-reload
```

## Adding & Managing Items

Each panel has a **+ Add** button in the header to add new entries without editing the files directly.

### Tasks
- Click **+ Add** in the Tasks panel to open the form
- Fields: Due Date, Priority (High / Medium / Low), Task, Notes, Parent Task (optional)
- Select a **Parent Task** to create a sub-task — it will appear indented (↳) directly below its parent in the list
- When a sub-task is added or edited, the parent task's due date automatically updates to the furthest due date among all its sub-tasks
- Click the **✓** button on any task row to mark it complete — it moves to the Completed Tasks section in `tasks.md` with today's date
- Hover over any task row to reveal the **✎** (edit) and **✕** (delete) buttons
- **✎** opens an edit modal pre-filled with the task's due date, priority, name, and notes
- **✕** permanently deletes the task — a confirmation dialog appears first

### Completed Tasks
- Click the **Completed Tasks** link in the header (left of the cheatsheet links) to open the completed tasks page
- Lists all completed tasks with their priority, original due date, notes, and date completed
- Hover over any row to reveal the **✕** (delete) button
- **✕** permanently removes the completed task — a confirmation dialog appears first

### Shopping
- Click **+ Add** in the Shopping panel to open the form
- Fields: Store (autocompletes existing stores), Item
- Click the **✓** button next to any item to mark it as purchased — it is removed from the list

### Ideas
- Click **+ Add** in the Ideas panel to open the form
- Fields: Idea description, Parent Idea (optional)
- Select a **Parent Idea** to create a sub-idea — it will appear indented (↳) directly below its parent
- The ID and date are assigned automatically
- Hover over any idea to reveal the **✎** (edit) and **✕** (delete) buttons
- **✎** opens an edit modal pre-filled with the current description
- **✕** permanently deletes the idea and any of its sub-ideas — a confirmation dialog appears first

## How It Works

- Reads `lists/tasks.md`, `lists/shopping.md`, and `lists/ideas.md` directly on each page load
- Writes changes back to those files immediately when forms are submitted
- Any manual edits to those files will appear on the next refresh (within 30 seconds)
- No build step or database required

## Installing the Service (first time setup)

```
sudo cp ~/documents/vibe-coding/tasklist/dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dashboard
sudo systemctl start dashboard
```
