#!/usr/bin/env python3
"""Dashboard server — reads tasks.md, shopping.md, ideas.md and serves HTML."""

import http.server
import re
import socketserver
import urllib.parse
from datetime import date as date_cls, datetime
from pathlib import Path

BASE = Path(__file__).parent / "lists"
CHEATSHEETS_DIR = Path(__file__).parent / "cheatsheets"
PORT = 6969


_FILE_DEFAULTS = {
    "tasks.md": (
        "| **#** | **Status** | **Priority** | **Due Date** | **Task** | **Notes** | **Parent** | **ID** |\n"
        "|-------|------------|--------------|--------------|----------|-----------|--------|----|\n"
        "\n## Completed Tasks\n\n"
        "| **#** | **Status** | **Priority** | **Due Date** | **Task** | **Notes** | **Parent** | **ID** | **Date Completed** |\n"
        "|-------|------------|--------------|--------------|----------|-----------|--------|----|-----------|\n"
    ),
    "ideas.md": "# Ideas\n",
    "shopping.md": "# Shopping\n",
}


def _ensure_files():
    BASE.mkdir(parents=True, exist_ok=True)
    for name, default in _FILE_DEFAULTS.items():
        p = BASE / name
        if not p.exists():
            p.write_text(default)


def read(name):
    return (BASE / name).read_text()


# ---------------------------------------------------------------------------
# Markdown renderer (for cheatsheets)
# ---------------------------------------------------------------------------

def inline_md(text):
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return text


def md_to_html(text):
    lines = text.splitlines()
    html = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Fenced code block
        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            code = "\n".join(code_lines)
            code = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lang_class = f' class="lang-{lang}"' if lang else ""
            html.append(f"<pre{lang_class}><code>{code}</code></pre>")
            i += 1
            continue

        # Table
        if line.strip().startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            headers = [h.strip().strip("*") for h in table_lines[0].split("|")[1:-1]]
            html.append("<table><thead><tr>")
            for h in headers:
                html.append(f"<th>{inline_md(h)}</th>")
            html.append("</tr></thead><tbody>")
            for row_line in table_lines[2:]:
                cols = [c.strip() for c in row_line.split("|")[1:-1]]
                html.append("<tr>")
                for c in cols:
                    html.append(f"<td>{inline_md(c)}</td>")
                html.append("</tr>")
            html.append("</tbody></table>")
            continue

        # Blockquote
        if line.startswith(">"):
            content = line[1:].strip()
            html.append(f"<blockquote>{inline_md(content)}</blockquote>")
            i += 1
            continue

        # Headers
        if line.startswith("### "):
            html.append(f"<h3>{inline_md(line[4:])}</h3>")
            i += 1
            continue
        if line.startswith("## "):
            html.append(f"<h2>{inline_md(line[3:])}</h2>")
            i += 1
            continue
        if line.startswith("# "):
            html.append(f"<h1>{inline_md(line[2:])}</h1>")
            i += 1
            continue

        # Unordered list
        if line.strip().startswith("- ") or line.strip().startswith("* "):
            html.append("<ul>")
            while i < len(lines) and (
                lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")
            ):
                html.append(f"<li>{inline_md(lines[i].strip()[2:])}</li>")
                i += 1
            html.append("</ul>")
            continue

        # Empty line
        if not line.strip():
            i += 1
            continue

        # Paragraph
        html.append(f"<p>{inline_md(line)}</p>")
        i += 1

    return "\n".join(html)


# ---------------------------------------------------------------------------
# Task writer
# ---------------------------------------------------------------------------

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
VALID_PRIORITIES = {"High", "Medium", "Low"}


def html_escape(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


COL_HEADER = "| **#** | **Status** | **Priority** | **Due Date** | **Task** | **Notes** | **Parent** | **ID** |"
COL_SEP    = "|---|--------|----------|----------|------|-------|---|---|"


def _parse_active(content: str):
    """Return (header_lines, rows, completed_section).

    rows is a list of dicts: #, Status, Priority, Due Date, Task, Notes, Parent, ID.
    completed_section is the raw string from '## Completed Tasks' onward, or ''.
    """
    split_marker = "## Completed Tasks"
    if split_marker in content:
        active_part, comp_part = content.split(split_marker, 1)
        completed_section = split_marker + comp_part
    else:
        active_part = content
        completed_section = ""

    lines = active_part.strip().splitlines()
    header_lines, table_start = [], None
    for idx, line in enumerate(lines):
        if line.strip().startswith("|"):
            table_start = idx
            break
        header_lines.append(line)

    if table_start is None:
        return header_lines, [], completed_section

    rows = []
    for line in lines[table_start + 2:]:
        if not line.strip().startswith("|"):
            continue
        cols = [c.strip() for c in line.split("|")[1:-1]]
        if len(cols) >= 6:
            rows.append({
                "#": cols[0],
                "Status": cols[1],
                "Priority": cols[2],
                "Due Date": cols[3],
                "Task": cols[4],
                "Notes": cols[5],
                "Parent": cols[6] if len(cols) > 6 else "",
                "ID": cols[7] if len(cols) > 7 else "",
            })
    return header_lines, rows, completed_section


def _next_task_id(rows, completed_section: str) -> int:
    """Return the next available task ID (max across active + completed + 1)."""
    ids = []
    for r in rows:
        try:
            ids.append(int(r.get("ID", 0) or 0))
        except ValueError:
            pass
    if completed_section:
        comp_rows = parse_md_table(completed_section.split("## Completed Tasks", 1)[1])
        for r in comp_rows:
            try:
                ids.append(int(r.get("ID", 0) or 0))
            except ValueError:
                pass
    return max(ids, default=0) + 1


def _sync_parent_due_dates(rows):
    """Set each parent task's due date to the latest due date among its subtasks."""
    id_to_row = {r["ID"]: r for r in rows if r.get("ID")}

    # Group subtasks by parent ID
    children = {}  # parent_id → [subtask rows]
    for r in rows:
        p = r.get("Parent", "")
        if p:
            children.setdefault(p, []).append(r)

    today = date_cls.today()
    for parent_id, subtask_rows in children.items():
        parent_row = id_to_row.get(parent_id)
        if parent_row is None:
            continue
        dates = []
        for sr in subtask_rows:
            try:
                dates.append(sr["Due Date"])
            except (KeyError, ValueError):
                pass
        if not dates:
            continue
        max_due = max(dates)
        parent_row["Due Date"] = max_due
        try:
            due = date_cls.fromisoformat(max_due.split()[0])
            parent_row["Status"] = "⚠️" if due < today else "&nbsp;"
        except ValueError:
            pass


def _render_active(header_lines, rows) -> str:
    lines = header_lines + [COL_HEADER, COL_SEP]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"| {i} | {r['Status']} | {r['Priority']} | {r['Due Date']} | {r['Task']} | {r['Notes']} | {r.get('Parent', '')} | {r.get('ID', '')} |"
        )
    return "\n".join(lines) + "\n"


def _parse_ideas(content: str):
    """Return list of dicts: id, date, desc, parent, notes."""
    _, blocks = _idea_blocks(content)
    ideas = []
    for heading, body in blocks:
        m = re.match(r"^## (\d+) \| (\d{4}-\d{2}-\d{2}) \| (.+?)(?:\s*\|\s*(\d*))?$", heading)
        if m:
            notes = ""
            for line in body:
                if line.startswith("notes: "):
                    notes = line[7:]
                    break
            ideas.append({
                "id": m.group(1),
                "date": m.group(2),
                "desc": m.group(3).strip(),
                "parent": m.group(4) or "",
                "notes": notes,
            })
    return ideas


def add_idea(description: str, parent: str = "", notes: str = ""):
    """Append a new idea to ideas.md with the next sequential ID."""
    path = BASE / "ideas.md"
    content = path.read_text()
    ids = re.findall(r"^## (\d+) \|", content, re.MULTILINE)
    next_id = max((int(i) for i in ids), default=0) + 1
    # Validate parent refers to an existing idea
    valid_ids = {m for m in ids}
    if parent not in valid_ids:
        parent = ""
    today = date_cls.today().isoformat()
    block = f"\n\n## {next_id} | {today} | {description} | {parent}\n"
    if notes:
        block += f"notes: {notes}\n"
    content = content.rstrip("\n") + block
    path.write_text(content)


def _idea_blocks(content: str):
    """Split ideas.md into (preamble_lines, [(heading, body_lines), ...])."""
    lines = content.splitlines()
    preamble, blocks, cur_heading, cur_body = [], [], None, []
    for line in lines:
        if re.match(r"^## \d+ \|", line):
            if cur_heading is not None:
                blocks.append((cur_heading, cur_body))
            cur_heading, cur_body = line, []
        elif cur_heading is None:
            preamble.append(line)
        else:
            cur_body.append(line)
    if cur_heading is not None:
        blocks.append((cur_heading, cur_body))
    return preamble, blocks


def _reassemble_ideas(preamble, blocks) -> str:
    parts = ["\n".join(preamble)]
    for heading, body in blocks:
        block_lines = [heading] + body
        parts.append("\n".join(block_lines))
    return "\n\n".join(p for p in parts if p.strip()) + "\n"


def edit_idea(idea_id: str, description: str, notes: str = ""):
    """Update the description and notes of an existing idea, preserving date, parent, and sub-points."""
    path = BASE / "ideas.md"
    preamble, blocks = _idea_blocks(path.read_text())
    new_blocks = []
    for heading, body in blocks:
        m = re.match(r"^## (\d+) \| (\d{4}-\d{2}-\d{2}) \| .+?(\s*\|\s*\d*)?\s*$", heading)
        if m and m.group(1) == idea_id:
            parent_seg = m.group(3) or " | "
            heading = f"## {m.group(1)} | {m.group(2)} | {description}{parent_seg}"
            # Replace existing notes line or remove it; keep all other body lines
            body = [l for l in body if not l.startswith("notes: ")]
            if notes:
                body = [f"notes: {notes}"] + body
        new_blocks.append((heading, body))
    path.write_text(_reassemble_ideas(preamble, new_blocks))


def delete_idea(idea_id: str):
    """Remove an idea and any of its sub-ideas from ideas.md."""
    path = BASE / "ideas.md"
    preamble, blocks = _idea_blocks(path.read_text())
    # Collect IDs to delete (the idea itself + any direct sub-ideas)
    to_delete = {idea_id}
    for heading, _ in blocks:
        m = re.match(r"^## (\d+) \| \d{4}-\d{2}-\d{2} \| .+?\s*\|\s*(\d*)\s*$", heading)
        if m and m.group(2) == idea_id:
            to_delete.add(m.group(1))
    new_blocks = []
    for heading, body in blocks:
        m = re.match(r"^## (\d+) \|", heading)
        if m and m.group(1) in to_delete:
            continue
        new_blocks.append((heading, body))
    path.write_text(_reassemble_ideas(preamble, new_blocks))


def add_shopping_item(store: str, item: str):
    """Add an item to a store section in shopping.md, creating the section if needed."""
    path = BASE / "shopping.md"
    content = path.read_text()

    section = f"## {store}"
    if section in content:
        # Insert item before the next ## section or end of file
        pattern = rf"(## {re.escape(store)}\n)(.*?)(?=\n## |\Z)"
        def replacer(m):
            existing = m.group(2).rstrip("\n")
            return f"{m.group(1)}{existing}\n- {item}\n"
        content = re.sub(pattern, replacer, content, flags=re.DOTALL)
    else:
        content = content.rstrip("\n") + f"\n\n## {store}\n- {item}\n"

    path.write_text(content)


def complete_task(task_num: int):
    """Move a task from active to the Completed Tasks section."""
    path = BASE / "tasks.md"
    header_lines, rows, completed_section = _parse_active(path.read_text())

    found = next((r for r in rows if r["#"].isdigit() and int(r["#"]) == task_num), None)
    if found is None:
        return

    # Find parent in active list (by ID)
    parent_id = found.get("Parent", "").strip()
    parent_row = next((r for r in rows if r.get("ID") == parent_id), None) if parent_id else None

    # Remove completed task (and parent if it's being auto-completed) from active
    to_remove = {id(found)}
    if parent_row:
        to_remove.add(id(parent_row))
    remaining = [r for r in rows if id(r) not in to_remove]
    new_content = _render_active(header_lines, remaining)

    if not completed_section:
        completed_section = "## Completed Tasks\n\n| **#** | **Status** | **Priority** | **Due Date** | **Task** | **Notes** | **Parent** | **ID** | **Date Completed** |\n|---|---|---|---|---|---|---|---|---|\n"

    existing_comp = parse_md_table(completed_section.split("## Completed Tasks", 1)[1])
    today = date_cls.today().isoformat()
    next_num = len(existing_comp) + 1

    # Check if parent is already in completed (don't duplicate)
    parent_already_completed = any(r.get("ID") == parent_id for r in existing_comp) if parent_id else True

    new_rows_text = ""
    # If parent needs to be auto-completed, add it first so sub-task groups under it
    if parent_row and not parent_already_completed:
        new_rows_text += f"| {next_num} | ✅ | {parent_row['Priority']} | {parent_row['Due Date']} | {parent_row['Task']} | {parent_row['Notes']} | {parent_row.get('Parent', '')} | {parent_row.get('ID', '')} | {today} |\n"
        next_num += 1

    new_rows_text += f"| {next_num} | ✅ | {found['Priority']} | {found['Due Date']} | {found['Task']} | {found['Notes']} | {found.get('Parent', '')} | {found.get('ID', '')} | {today} |\n"

    completed_section = completed_section.rstrip("\n") + "\n" + new_rows_text
    path.write_text(new_content + "\n" + completed_section)


def delete_task(task_num: int):
    """Permanently remove a task from the active list without archiving it."""
    path = BASE / "tasks.md"
    header_lines, rows, completed_section = _parse_active(path.read_text())
    remaining = [r for r in rows if not (r["#"].isdigit() and int(r["#"]) == task_num)]
    new_content = _render_active(header_lines, remaining)
    if completed_section:
        new_content += "\n" + completed_section
    path.write_text(new_content)


def reopen_completed_task(task_num: int):
    """Move a completed task back to the active list and remove it from Completed Tasks."""
    path = BASE / "tasks.md"
    content = path.read_text()
    split_marker = "## Completed Tasks"
    if split_marker not in content:
        return
    active_part, comp_part = content.split(split_marker, 1)
    comp_rows = parse_md_table(comp_part)
    found = next((r for r in comp_rows if r.get("#", "").isdigit() and int(r["#"]) == task_num), None)
    if found is None:
        return
    kept = [r for r in comp_rows if r is not found]

    # Rebuild completed section
    header = "## Completed Tasks\n\n| **#** | **Status** | **Priority** | **Due Date** | **Task** | **Notes** | **Parent** | **ID** | **Date Completed** |\n|---|---|---|---|---|---|---|---|---|\n"
    rows_text = ""
    for i, r in enumerate(kept, 1):
        rows_text += f"| {i} | {r.get('Status','✅')} | {r.get('Priority','')} | {r.get('Due Date','')} | {r.get('Task','')} | {r.get('Notes','')} | {r.get('Parent','')} | {r.get('ID','')} | {r.get('Date Completed','')} |\n"
    new_completed = header + rows_text

    # Re-add to active list
    header_lines, rows, _ = _parse_active(active_part)
    today = date_cls.today()
    due_raw = found.get("Due Date", "")
    try:
        due_date = date_cls.fromisoformat(due_raw.split()[0]) if due_raw else None
        status = "⚠️" if due_date and due_date < today else "&nbsp;"
    except ValueError:
        status = "&nbsp;"
    new_row = {
        "#": str(len(rows) + 1),
        "Status": status,
        "Priority": found.get("Priority", "Medium"),
        "Due Date": due_raw,
        "Task": found.get("Task", ""),
        "Notes": found.get("Notes", ""),
        "Parent": found.get("Parent", ""),
        "ID": found.get("ID", ""),
    }
    rows.append(new_row)
    rows.sort(key=lambda r: (r["Due Date"], PRIORITY_ORDER.get(r["Priority"], 99)))
    new_active = _render_active(header_lines, rows)
    path.write_text(new_active + "\n" + new_completed)


def delete_completed_task(task_num: int):
    """Permanently remove a row from the Completed Tasks section and renumber."""
    path = BASE / "tasks.md"
    content = path.read_text()
    split_marker = "## Completed Tasks"
    if split_marker not in content:
        return
    active_part, comp_part = content.split(split_marker, 1)
    comp_rows = parse_md_table(comp_part)
    kept = [r for r in comp_rows if not (r.get("#", "").isdigit() and int(r["#"]) == task_num)]
    if len(kept) == len(comp_rows):
        return  # nothing removed
    # Rebuild completed section with renumbered rows
    header = "## Completed Tasks\n\n| **#** | **Status** | **Priority** | **Due Date** | **Task** | **Notes** | **Parent** | **ID** | **Date Completed** |\n|---|---|---|---|---|---|---|---|---|\n"
    rows_text = ""
    for i, r in enumerate(kept, 1):
        rows_text += f"| {i} | {r.get('Status','✅')} | {r.get('Priority','')} | {r.get('Due Date','')} | {r.get('Task','')} | {r.get('Notes','')} | {r.get('Parent','')} | {r.get('ID','')} | {r.get('Date Completed','')} |\n"
    path.write_text(active_part + header + rows_text)


def edit_task(task_num: int, due_date: str, task: str, notes: str, priority: str, parent: str = ""):
    """Update a task's fields in-place, re-sort, and save."""
    if priority not in VALID_PRIORITIES:
        priority = "Medium"
    path = BASE / "tasks.md"
    header_lines, rows, completed_section = _parse_active(path.read_text())
    # Validate parent ID exists and isn't the task itself
    valid_ids = {r["ID"] for r in rows if r.get("ID")}
    editing_id = next((r["ID"] for r in rows if r["#"].isdigit() and int(r["#"]) == task_num), None)
    if parent not in valid_ids or parent == editing_id:
        parent = ""
    today = date_cls.today()
    for r in rows:
        if r["#"].isdigit() and int(r["#"]) == task_num:
            try:
                due = date_cls.fromisoformat(due_date.split()[0])
                r["Status"] = "⚠️" if due < today else "&nbsp;"
            except ValueError:
                pass
            r["Due Date"] = due_date
            r["Task"] = task
            r["Notes"] = notes
            r["Priority"] = priority
            r["Parent"] = parent
            break
    _sync_parent_due_dates(rows)
    rows.sort(key=lambda r: (r["Due Date"], PRIORITY_ORDER.get(r["Priority"], 99)))
    new_content = _render_active(header_lines, rows)
    if completed_section:
        new_content += "\n" + completed_section
    path.write_text(new_content)


def remove_shopping_item(store: str, item: str):
    """Remove a specific item from a store section in shopping.md."""
    path = BASE / "shopping.md"
    lines = path.read_text().splitlines()
    new_lines, current_store = [], None
    for line in lines:
        if line.startswith("## "):
            current_store = line[3:].strip()
        if current_store == store and line.strip() == f"- {item}":
            continue
        new_lines.append(line)
    path.write_text("\n".join(new_lines) + "\n")


def add_task(due_date: str, task: str, notes: str, priority: str = "Medium", parent: str = ""):
    """Append a task to tasks.md, re-sort active tasks, renumber, and save."""
    if priority not in VALID_PRIORITIES:
        priority = "Medium"

    path = BASE / "tasks.md"
    header_lines, rows, completed_section = _parse_active(path.read_text())

    today = date_cls.today()
    try:
        due = date_cls.fromisoformat(due_date.split()[0])
        status = "⚠️" if due < today else "&nbsp;"
    except ValueError:
        status = "&nbsp;"

    # Validate parent refers to an existing task ID
    valid_ids = {r["ID"] for r in rows if r.get("ID")}
    if parent not in valid_ids:
        parent = ""

    new_id = str(_next_task_id(rows, completed_section))
    rows.append({"#": "", "Status": status, "Priority": priority, "Due Date": due_date, "Task": task, "Notes": notes, "Parent": parent, "ID": new_id})
    _sync_parent_due_dates(rows)
    rows.sort(key=lambda r: (r["Due Date"], PRIORITY_ORDER.get(r["Priority"], 99)))

    new_content = _render_active(header_lines, rows)
    if completed_section:
        new_content += "\n" + completed_section
    path.write_text(new_content)


# ---------------------------------------------------------------------------
# Dashboard panels
# ---------------------------------------------------------------------------

def parse_md_table(text):
    lines = [l.strip() for l in text.strip().splitlines()]
    rows = [l for l in lines if l.startswith("|")]
    if len(rows) < 2:
        return []
    headers = [h.strip().strip("*") for h in rows[0].split("|")[1:-1]]
    result = []
    for row in rows[2:]:
        cols = [c.strip() for c in row.split("|")[1:-1]]
        if cols:
            result.append(dict(zip(headers, cols)))
    return result


def tasks_html():
    _, active, _ = _parse_active(read("tasks.md"))

    today_str = date_cls.today().isoformat()

    def row_class(r):
        if "⚠️" in r.get("Status", ""):
            return "overdue"
        due_raw = r.get("Due Date", "")
        due_date = due_raw.split()[0] if due_raw else ""
        if due_date == today_str:
            return "due-today"
        return ""

    def priority_badge(p):
        cls = {"High": "high", "Medium": "medium", "Low": "low"}.get(p, "")
        return f'<span class="badge {cls}">{p}</span>'

    def make_row(r, indent=False):
        cls = row_class(r)
        icon = "⚠️" if cls == "overdue" else "·"
        due_raw = r.get("Due Date", "")
        due = html_escape(due_raw.replace(" 00:00", ""))
        due_date_val = html_escape(due_raw.split()[0] if due_raw else "")
        num = html_escape(r.get("#", ""))
        task_text = html_escape(r.get("Task", ""))
        notes_text = html_escape(r.get("Notes", ""))
        priority = r.get("Priority", "Medium")
        task_js = r.get("Task", "").replace("\\", "\\\\").replace("'", "\\'").replace('"', '&quot;').replace("`", "\\`")
        notes_js = r.get("Notes", "").replace("\\", "\\\\").replace("'", "\\'").replace('"', '&quot;').replace("`", "\\`")
        parent_id_js = html_escape(r.get("Parent", ""))
        indent_prefix = '<span class="subtask-indent">↳</span>' if indent else ""
        row_cls = f"{cls} subtask" if indent else cls
        return f"""<tr class="{row_cls}">
            <td>{icon}</td>
            <td>{priority_badge(priority)}</td>
            <td class="due">{due}</td>
            <td>{indent_prefix}{task_text}</td>
            <td class="notes">{notes_text}</td>
            <td class="action-cell">
                <form method="POST" action="/complete-task" style="display:inline"><input type="hidden" name="num" value="{num}"><button type="submit" class="done-btn" title="Mark complete">✓</button></form>
                <span class="task-hover-actions">
                    <button type="button" class="edit-btn" title="Edit task" onclick="openEditTask('{num}','{task_js}','{notes_js}','{due_date_val}','{priority}','{parent_id_js}')">✎</button>
                    <form method="POST" action="/delete-task" style="display:inline"><input type="hidden" name="num" value="{num}"><button type="submit" class="del-btn" title="Delete task" onclick="return confirm('Delete this task permanently?')">✕</button></form>
                </span>
            </td>
        </tr>"""

    # Group: top-level tasks, each followed immediately by their sub-tasks
    by_id = {r.get("ID", ""): r for r in active if r.get("ID")}
    sub_of = {}  # parent_id → [child rows]
    top_level = []
    for r in active:
        p = r.get("Parent", "")
        if p and p in by_id:
            sub_of.setdefault(p, []).append(r)
        else:
            top_level.append(r)

    rows = ""
    for r in top_level:
        rows += make_row(r)
        for child in sub_of.get(r.get("ID", ""), []):
            rows += make_row(child, indent=True)

    total = len(active)
    overdue_count = sum(1 for r in active if "⚠️" in r.get("Status", ""))
    badge_extra = f' <span class="overdue-badge">{overdue_count} overdue</span>' if overdue_count else ""
    # Parent selector options (value = internal ID)
    parent_opts = '<option value="">None (top-level task)</option>'
    for r in top_level:
        task_id = html_escape(r.get("ID", ""))
        num = html_escape(r.get("#", ""))
        label = html_escape(r.get("Task", ""))
        parent_opts += f'<option value="{task_id}">#{num} — {label}</option>'

    return f"""<section class="card tasks-card">
        <h2>Tasks <span class="count">{total}</span>{badge_extra}
            <button class="add-btn" onclick="document.getElementById('task-modal').classList.add('open')">+ Add</button>
        </h2>
        <table>
            <thead><tr><th></th><th>Priority</th><th>Due</th><th>Task</th><th>Notes</th><th></th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </section>

    <div id="task-modal" class="modal-overlay" onclick="if(event.target===this)this.classList.remove('open')">
        <div class="modal">
            <h3>Add Task</h3>
            <form method="POST" action="/add-task">
                <label>Due Date
                    <input type="date" name="due_date" required value="{today_str}">
                </label>
                <label>Priority
                    <select name="priority">
                        <option value="High">High</option>
                        <option value="Medium" selected>Medium</option>
                        <option value="Low">Low</option>
                    </select>
                </label>
                <label>Task
                    <input type="text" name="task" required placeholder="What needs to be done?">
                </label>
                <label>Notes
                    <input type="text" name="notes" placeholder="Optional context">
                </label>
                <label>Parent Task
                    <select name="parent">{parent_opts}</select>
                </label>
                <div class="modal-actions">
                    <button type="button" class="cancel-btn" onclick="document.getElementById('task-modal').classList.remove('open')">Cancel</button>
                    <button type="submit" class="submit-btn">Add Task</button>
                </div>
            </form>
        </div>
    </div>

    <div id="task-edit-modal" class="modal-overlay" onclick="if(event.target===this)this.classList.remove('open')">
        <div class="modal">
            <h3>Edit Task</h3>
            <form method="POST" action="/edit-task">
                <input type="hidden" name="num" id="edit-task-num">
                <label>Due Date
                    <input type="date" name="due_date" id="edit-task-due" required>
                </label>
                <label>Priority
                    <select name="priority" id="edit-task-priority">
                        <option value="High">High</option>
                        <option value="Medium">Medium</option>
                        <option value="Low">Low</option>
                    </select>
                </label>
                <label>Task
                    <input type="text" name="task" id="edit-task-task" required placeholder="What needs to be done?">
                </label>
                <label>Notes
                    <input type="text" name="notes" id="edit-task-notes" placeholder="Optional context">
                </label>
                <label>Parent Task
                    <select name="parent" id="edit-task-parent">{parent_opts}</select>
                </label>
                <div class="modal-actions">
                    <button type="button" class="cancel-btn" onclick="document.getElementById('task-edit-modal').classList.remove('open')">Cancel</button>
                    <button type="submit" class="submit-btn">Save</button>
                </div>
            </form>
        </div>
    </div>

    <script>
    function openEditTask(num, task, notes, due, priority, parentId) {{
        document.getElementById('edit-task-num').value = num;
        document.getElementById('edit-task-task').value = task;
        document.getElementById('edit-task-notes').value = notes;
        document.getElementById('edit-task-due').value = due;
        document.getElementById('edit-task-priority').value = priority;
        document.getElementById('edit-task-parent').value = parentId || '';
        document.getElementById('task-edit-modal').classList.add('open');
    }}
    </script>"""


def shopping_html():
    content = read("shopping.md")
    stores = re.findall(r"## (.+?)\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    inner = ""
    total = 0
    store_names = []
    for store, items_text in stores:
        store_names.append(store.strip())
        items = [
            i.lstrip("- ").strip()
            for i in items_text.strip().splitlines()
            if i.strip().startswith("-")
        ]
        if not items:
            continue
        total += len(items)
        inner += f"<h3>{html_escape(store)}</h3><ul>"
        for item in items:
            safe_store = html_escape(store)
            safe_item = html_escape(item)
            inner += f'<li><span class="shop-item">{safe_item}</span><form method="POST" action="/complete-shopping" style="display:inline"><input type="hidden" name="store" value="{safe_store}"><input type="hidden" name="item" value="{safe_item}"><button type="submit" class="done-btn" title="Mark purchased">✓</button></form></li>'
        inner += "</ul>"

    datalist_opts = "".join(f'<option value="{html_escape(s)}">' for s in store_names)

    return f"""<section class="card shopping-card">
        <h2>Shopping <span class="count">{total}</span>
            <button class="add-btn" onclick="document.getElementById('shopping-modal').classList.add('open')">+ Add</button>
        </h2>
        {inner}
    </section>

    <div id="shopping-modal" class="modal-overlay" onclick="if(event.target===this)this.classList.remove('open')">
        <div class="modal">
            <h3>Add Shopping Item</h3>
            <form method="POST" action="/add-shopping">
                <label>Store
                    <input type="text" name="store" required placeholder="e.g. Target" list="store-list">
                    <datalist id="store-list">{datalist_opts}</datalist>
                </label>
                <label>Item
                    <input type="text" name="item" required placeholder="What to buy?">
                </label>
                <div class="modal-actions">
                    <button type="button" class="cancel-btn" onclick="document.getElementById('shopping-modal').classList.remove('open')">Cancel</button>
                    <button type="submit" class="submit-btn">Add Item</button>
                </div>
            </form>
        </div>
    </div>"""


def ideas_html():
    ideas = _parse_ideas(read("ideas.md"))
    by_id = {r["id"]: r for r in ideas}

    def make_item(r, indent=False):
        id_ = html_escape(r["id"])
        title = html_escape(r["desc"])
        date = html_escape(r["date"])
        notes = html_escape(r.get("notes", ""))
        desc_js = r["desc"].replace("\\", "\\\\").replace("'", "\\'").replace('"', '&quot;').replace("`", "\\`")
        notes_js = r.get("notes", "").replace("\\", "\\\\").replace("'", "\\'").replace('"', '&quot;').replace("`", "\\`")
        prefix = '<span class="subtask-indent">↳</span>' if indent else ""
        li_cls = ' class="sub-idea"' if indent else ""
        notes_html = f'<span class="idea-notes">{notes}</span>' if notes else ""
        id_html = "" if indent else f'<span class="idea-id">#{id_}</span>'
        return (
            f'<li{li_cls}>{prefix}'
            f'{id_html}'
            f'<span class="idea-title">{title}</span>'
            f'{notes_html}'
            f'<span class="idea-date">{date}</span>'
            f'<span class="idea-actions">'
            f'<button class="edit-btn" onclick="openEditIdea(\'{id_}\',\'{desc_js}\',\'{notes_js}\')" title="Edit idea">✎</button>'
            f'<form method="POST" action="/delete-idea" style="display:inline">'
            f'<input type="hidden" name="id" value="{id_}">'
            f'<button type="submit" class="del-btn" title="Delete idea" onclick="return confirm(\'Delete this idea permanently?\')">✕</button>'
            f'</form>'
            f'</span>'
            f'</li>'
        )

    sub_of = {}
    top_level = []
    for r in ideas:
        p = r["parent"]
        if p and p in by_id:
            sub_of.setdefault(p, []).append(r)
        else:
            top_level.append(r)

    items = ""
    for r in top_level:
        items += make_item(r)
        for child in sub_of.get(r["id"], []):
            items += make_item(child, indent=True)

    parent_opts = '<option value="">None (top-level idea)</option>'
    for r in ideas:
        id_ = html_escape(r["id"])
        label = html_escape(r["desc"])
        parent_opts += f'<option value="{id_}">#{id_} — {label}</option>'

    return f"""<section class="card ideas-card">
        <h2>Ideas <span class="count">{len(ideas)}</span>
            <button class="add-btn" onclick="document.getElementById('idea-modal').classList.add('open')">+ Add</button>
        </h2>
        <ul class="ideas">{items}</ul>
    </section>

    <div id="idea-modal" class="modal-overlay" onclick="if(event.target===this)this.classList.remove('open')">
        <div class="modal">
            <h3>Add Idea</h3>
            <form method="POST" action="/add-idea">
                <label>Idea
                    <input type="text" name="description" required placeholder="Describe the idea">
                </label>
                <label>Notes
                    <input type="text" name="notes" placeholder="Optional notes">
                </label>
                <label>Parent Idea
                    <select name="parent">{parent_opts}</select>
                </label>
                <div class="modal-actions">
                    <button type="button" class="cancel-btn" onclick="document.getElementById('idea-modal').classList.remove('open')">Cancel</button>
                    <button type="submit" class="submit-btn">Add Idea</button>
                </div>
            </form>
        </div>
    </div>

    <div id="idea-edit-modal" class="modal-overlay" onclick="if(event.target===this)this.classList.remove('open')">
        <div class="modal">
            <h3>Edit Idea</h3>
            <form method="POST" action="/edit-idea">
                <input type="hidden" name="id" id="edit-idea-id">
                <label>Idea
                    <input type="text" name="description" id="edit-idea-desc" required placeholder="Describe the idea">
                </label>
                <label>Notes
                    <input type="text" name="notes" id="edit-idea-notes" placeholder="Optional notes">
                </label>
                <div class="modal-actions">
                    <button type="button" class="cancel-btn" onclick="document.getElementById('idea-edit-modal').classList.remove('open')">Cancel</button>
                    <button type="submit" class="submit-btn">Save</button>
                </div>
            </form>
        </div>
    </div>

    <script>
    function openEditIdea(id, desc, notes) {{
        document.getElementById('edit-idea-id').value = id;
        document.getElementById('edit-idea-desc').value = desc;
        document.getElementById('edit-idea-notes').value = notes || '';
        document.getElementById('idea-edit-modal').classList.add('open');
    }}
    </script>"""


def cheatsheet_links():
    links = '<a href="/completed" class="nav-link">Completed Tasks</a>'
    for path in sorted(CHEATSHEETS_DIR.glob("*.md")):
        label = path.stem.replace("-cheatsheet", "").replace("-", " ").title()
        links += f'<a href="/cheatsheet/{path.name}" class="nav-link">{label}</a>'
    return f'<nav class="cheatsheets">{links}</nav>'


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: system-ui, -apple-system, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    min-height: 100vh;
    padding: 2rem;
}
a { color: inherit; text-decoration: none; }

/* ── Header ── */
header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
}
h1 {
    font-size: 1.4rem;
    font-weight: 700;
    color: #f8fafc;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.updated {
    font-size: 0.75rem;
    color: #94a3b8;
    margin-right: auto;
}
.cheatsheets { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.nav-link {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #94a3b8;
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 999px;
    padding: 0.25rem 0.75rem;
    transition: background 0.15s, color 0.15s;
}
.nav-link:hover { background: #334155; color: #f1f5f9; }

/* ── Dashboard grid ── */
.grid {
    display: grid;
    grid-template-columns: 2fr 1fr;
    grid-template-areas: "tasks shopping" "ideas shopping";
    gap: 1.5rem;
    align-items: start;
}
.tasks-card    { grid-area: tasks; }
.ideas-card    { grid-area: ideas; }
.shopping-card { grid-area: shopping; }
.card {
    background: #1e293b;
    border-radius: 12px;
    padding: 1.5rem;
    border: 1px solid #334155;
}
.card h2 {
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #94a3b8;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
}
.card h3 {
    font-size: 0.75rem;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 1rem 0 0.4rem;
}
.card h3:first-of-type { margin-top: 0; }
.count {
    background: #334155;
    color: #94a3b8;
    border-radius: 999px;
    padding: 0.1rem 0.5rem;
    font-size: 0.7rem;
}
.overdue-badge {
    background: #450a0a;
    color: #fca5a5;
    border-radius: 999px;
    padding: 0.1rem 0.5rem;
    font-size: 0.7rem;
}
table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
th {
    text-align: left;
    color: #94a3b8;
    font-weight: 500;
    font-size: 0.75rem;
    padding: 0.3rem 0.5rem;
    border-bottom: 1px solid #334155;
}
td {
    padding: 0.55rem 0.5rem;
    border-bottom: 1px solid #263348;
    vertical-align: top;
}
tr:last-child td { border-bottom: none; }
tr.overdue td { color: #fca5a5; }
tr.overdue td:first-child { font-size: 1rem; }
tr.due-today td { background: #1e293b; }
tr.due-today .due { color: #e2e8f0; font-weight: 600;}
td:first-child { color: #94a3b8; font-size: 0.9rem; }
.due { color: #cbd5e1; white-space: nowrap; font-size: 0.8rem; }
tr.overdue .due { color: #fca5a5; }
.notes { color: #94a3b8; font-size: 0.8rem; }
.badge {
    font-size: 0.65rem;
    padding: 0.15rem 0.45rem;
    border-radius: 999px;
    font-weight: 700;
    white-space: nowrap;
}
.badge.high   { background: #7f1d1d; color: #fca5a5; }
.badge.medium { background: #78350f; color: #fcd34d; }
.badge.low    { background: #14532d; color: #86efac; }
ul { list-style: none; }
ul li {
    padding: 0.45rem 0;
    border-bottom: 1px solid #263348;
    font-size: 0.875rem;
    color: #cbd5e1;
}
ul li:last-child { border-bottom: none; }
ul.ideas li { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
ul.ideas li.sub-idea { background: #182032; padding-left: 0.75rem; }
.idea-id      { color: #64748b; font-size: 0.7rem; font-family: monospace; flex-shrink: 0; }
.idea-title   { flex: 1; }
.idea-notes   { display: block; font-size: 0.72rem; color: #94a3b8; margin-top: 0.15rem; padding-left: 1.6rem; flex-basis: 100%; order: 99; }
.idea-date    { color: #64748b; font-size: 0.72rem; flex-shrink: 0; }
.idea-actions { display: flex; gap: 0.3rem; flex-shrink: 0; opacity: 0; transition: opacity 0.15s; }
ul.ideas li:hover .idea-actions { opacity: 1; }
.edit-btn {
    background: transparent;
    border: 1px solid #334155;
    border-radius: 4px;
    color: #475569;
    font-size: 0.75rem;
    padding: 0.1rem 0.35rem;
    cursor: pointer;
    line-height: 1.4;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.edit-btn:hover { background: #1e3a5f; border-color: #3b82f6; color: #93c5fd; }

/* ── Add Task button ── */
.add-btn {
    margin-left: auto;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #7dd3fc;
    background: #0f2942;
    border: 1px solid #1e4a7a;
    border-radius: 999px;
    padding: 0.2rem 0.65rem;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
}
.add-btn:hover { background: #1e4a7a; color: #e0f2fe; }

/* ── Modal ── */
.modal-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    z-index: 100;
    align-items: center;
    justify-content: center;
}
.modal-overlay.open { display: flex; }
.modal {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 1.75rem;
    width: 100%;
    max-width: 420px;
    box-shadow: 0 25px 60px rgba(0,0,0,0.5);
}
.modal h3 {
    font-size: 0.85rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #94a3b8;
    margin-bottom: 1.25rem;
}
.modal form { display: flex; flex-direction: column; gap: 0.85rem; }
.modal label {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #64748b;
}
.modal input, .modal select {
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #e2e8f0;
    font-size: 0.875rem;
    padding: 0.5rem 0.65rem;
    outline: none;
    transition: border-color 0.15s;
}
.modal input:focus, .modal select:focus { border-color: #3b82f6; }
.modal input::placeholder { color: #475569; }
.modal-actions { display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 0.4rem; }
.cancel-btn {
    font-size: 0.8rem;
    padding: 0.45rem 1rem;
    border-radius: 6px;
    border: 1px solid #334155;
    background: transparent;
    color: #94a3b8;
    cursor: pointer;
}
.cancel-btn:hover { background: #263348; }
.submit-btn {
    font-size: 0.8rem;
    font-weight: 600;
    padding: 0.45rem 1rem;
    border-radius: 6px;
    border: none;
    background: #2563eb;
    color: #fff;
    cursor: pointer;
    transition: background 0.15s;
}
.submit-btn:hover { background: #1d4ed8; }

/* ── Done / remove buttons ── */
.done-btn, .del-btn, .reopen-btn {
    background: transparent;
    border: 1px solid #334155;
    border-radius: 4px;
    color: #475569;
    font-size: 0.75rem;
    padding: 0.1rem 0.35rem;
    cursor: pointer;
    line-height: 1.4;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.done-btn:hover { background: #166534; border-color: #16a34a; color: #86efac; }
.del-btn:hover { background: #7f1d1d; border-color: #dc2626; color: #fca5a5; }
.reopen-btn:hover { background: #1e3a5f; border-color: #3b82f6; color: #93c5fd; }
.action-cell { width: 1px; white-space: nowrap; padding-right: 0.25rem; vertical-align: middle; }
.task-hover-actions { display: inline-flex; gap: 0.3rem; opacity: 0; transition: opacity 0.15s; vertical-align: middle; }
tr:hover .task-hover-actions { opacity: 1; }
tr.subtask td { background: #182032; }
tr.subtask td:first-child { color: #64748b; }
.subtask-indent { color: #475569; margin-right: 0.35rem; font-size: 0.8rem; }
.shop-item { flex: 1; }
.card ul li { display: flex; align-items: center; gap: 0.5rem; }

/* ── Cheatsheet page ── */
.back {
    font-size: 0.8rem;
    color: #94a3b8;
    font-weight: 500;
}
.back:hover { color: #e2e8f0; }
main.cheatsheet {
    max-width: 860px;
}
main.cheatsheet h1 {
    font-size: 1.6rem;
    color: #f8fafc;
    margin-bottom: 1.5rem;
    text-transform: none;
    letter-spacing: normal;
}
main.cheatsheet h2 {
    font-size: 1rem;
    color: #7dd3fc;
    font-weight: 600;
    text-transform: none;
    letter-spacing: normal;
    margin: 2rem 0 0.75rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #1e3a5f;
}
main.cheatsheet h3 {
    font-size: 0.875rem;
    color: #cbd5e1;
    font-weight: 600;
    text-transform: none;
    letter-spacing: normal;
    margin: 1.25rem 0 0.5rem;
}
main.cheatsheet table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
    margin-bottom: 1rem;
    background: #1e293b;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #334155;
}
main.cheatsheet th {
    background: #263348;
    color: #cbd5e1;
    font-size: 0.75rem;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid #334155;
}
main.cheatsheet td {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid #263348;
    color: #cbd5e1;
}
main.cheatsheet tr:last-child td { border-bottom: none; }
main.cheatsheet td:first-child { font-family: monospace; font-size: 0.82rem; color: #7dd3fc; }
main.cheatsheet pre {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 1rem;
    overflow-x: auto;
    margin-bottom: 1rem;
}
main.cheatsheet code {
    font-family: 'Menlo', 'Consolas', monospace;
    font-size: 0.82rem;
    color: #a5f3fc;
    white-space: pre;
}
main.cheatsheet p code, main.cheatsheet li code, main.cheatsheet td code {
    background: #263348;
    padding: 0.1rem 0.3rem;
    border-radius: 4px;
    font-size: 0.82rem;
    color: #7dd3fc;
    white-space: nowrap;
}
main.cheatsheet blockquote {
    background: #1e293b;
    border-left: 3px solid #64748b;
    padding: 0.6rem 1rem;
    border-radius: 0 6px 6px 0;
    color: #cbd5e1;
    font-size: 0.875rem;
    margin: 1rem 0;
}
main.cheatsheet p {
    color: #cbd5e1;
    font-size: 0.875rem;
    margin-bottom: 0.75rem;
    line-height: 1.6;
}
main.cheatsheet ul {
    list-style: disc;
    padding-left: 1.25rem;
    margin-bottom: 0.75rem;
}
main.cheatsheet ul li {
    border: none;
    padding: 0.2rem 0;
    font-size: 0.875rem;
}
"""


# ---------------------------------------------------------------------------
# Page generators
# ---------------------------------------------------------------------------

def dashboard_page():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dashboard</title>
  <link rel="stylesheet" href="/style.css">
  <meta http-equiv="refresh" content="30">
</head>
<body>
  <header>
    <h1>Dashboard</h1>
    <span class="updated">updated {now}</span>
    {cheatsheet_links()}
  </header>
  <div class="grid">
    {tasks_html()}
    {ideas_html()}
    {shopping_html()}
  </div>
</body>
</html>"""


def cheatsheet_page(filename):
    path = (CHEATSHEETS_DIR / filename).resolve()
    if not str(path).startswith(str(CHEATSHEETS_DIR.resolve())) or not path.exists():
        return None
    content = path.read_text()
    title = path.stem.replace("-cheatsheet", "").replace("-", " ").title() + " Cheatsheet"
    body = md_to_html(content)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <header>
    <a href="/" class="back">← Dashboard</a>
  </header>
  <main class="cheatsheet">
    {body}
  </main>
</body>
</html>"""


def completed_tasks_page():
    content = read("tasks.md")
    split_marker = "## Completed Tasks"
    comp_rows = []
    if split_marker in content:
        comp_part = content.split(split_marker, 1)[1]
        comp_rows = parse_md_table(comp_part)

    def priority_badge(p):
        cls = {"High": "high", "Medium": "medium", "Low": "low"}.get(p, "")
        return f'<span class="badge {cls}">{p}</span>'

    def make_comp_row(r, indent=False):
        num = html_escape(r.get("#", ""))
        task_text = html_escape(r.get("Task", ""))
        task_display = f'<span class="subtask-indent">↳</span>{task_text}' if indent else task_text
        notes_text = html_escape(r.get("Notes", ""))
        priority = r.get("Priority", "Medium")
        due_raw = r.get("Due Date", "")
        due = html_escape(due_raw.replace(" 00:00", ""))
        date_done = html_escape(r.get("Date Completed", ""))
        row_cls = "subtask" if indent else ""
        return f"""<tr class="{row_cls}">
            <td>✅</td>
            <td>{priority_badge(priority)}</td>
            <td class="due">{due}</td>
            <td>{task_display}</td>
            <td class="notes">{notes_text}</td>
            <td class="due">{date_done}</td>
            <td class="action-cell">
                <span class="task-hover-actions">
                    <form method="POST" action="/reopen-completed-task" style="display:inline"><input type="hidden" name="num" value="{num}"><button type="submit" class="reopen-btn" title="Reopen task">↩</button></form>
                    <form method="POST" action="/delete-completed-task" style="display:inline"><input type="hidden" name="num" value="{num}"><button type="submit" class="del-btn" title="Delete permanently" onclick="return confirm('Delete this completed task permanently?')">✕</button></form>
                </span>
            </td>
        </tr>"""

    # Group sub-tasks immediately under their parent (matched by internal ID)
    by_id = {r.get("ID", ""): r for r in comp_rows if r.get("ID")}
    sub_of = {}   # parent_id → [child rows]
    top_level_comp = []
    for r in comp_rows:
        p = r.get("Parent", "").strip()
        if p and p in by_id:
            sub_of.setdefault(p, []).append(r)
        else:
            top_level_comp.append(r)

    rows_html = ""
    for r in top_level_comp:
        rows_html += make_comp_row(r)
        for child in sub_of.get(r.get("ID", ""), []):
            rows_html += make_comp_row(child, indent=True)

    total = len(comp_rows)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Completed Tasks</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <header>
    <a href="/" class="back">← Dashboard</a>
  </header>
  <main style="max-width:900px;margin:0 auto;">
    <div class="card">
      <h2>Completed Tasks <span class="count">{total}</span></h2>
      <table>
        <thead><tr><th></th><th>Priority</th><th>Due</th><th>Task</th><th>Notes</th><th>Completed</th><th></th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
  </main>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/style.css":
            body = CSS.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.send_header("Cache-Control", "max-age=3600")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/":
            body = dashboard_page().encode()
        elif path == "/completed":
            body = completed_tasks_page().encode()
        elif path.startswith("/cheatsheet/"):
            filename = path[len("/cheatsheet/"):]
            page = cheatsheet_page(filename)
            if page is None:
                self.send_response(404)
                self.end_headers()
                return
            body = page.encode()
        else:
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = self.path.split("?")[0]

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        data = urllib.parse.parse_qs(body)

        def get(key, default=""):
            return data.get(key, [default])[0].strip()

        if path == "/add-task":
            due_raw = get("due_date")
            task = get("task")
            notes = get("notes")
            priority = get("priority", "Medium")
            parent = get("parent")
            if due_raw and task:
                add_task(due_raw + " 00:00", task, notes, priority, parent)

        elif path == "/add-shopping":
            store = get("store")
            item = get("item")
            if store and item:
                add_shopping_item(store, item)

        elif path == "/complete-task":
            num = get("num")
            if num.isdigit():
                complete_task(int(num))

        elif path == "/delete-task":
            num = get("num")
            if num.isdigit():
                delete_task(int(num))

        elif path == "/edit-task":
            num = get("num")
            due_raw = get("due_date")
            task = get("task")
            notes = get("notes")
            priority = get("priority", "Medium")
            parent = get("parent", "")
            if num.isdigit() and due_raw and task:
                edit_task(int(num), due_raw + " 00:00", task, notes, priority, parent)

        elif path == "/complete-shopping":
            store = get("store")
            item = get("item")
            if store and item:
                remove_shopping_item(store, item)

        elif path == "/add-idea":
            description = get("description")
            parent = get("parent")
            notes = get("notes")
            if description:
                add_idea(description, parent, notes)

        elif path == "/edit-idea":
            idea_id = get("id")
            description = get("description")
            notes = get("notes")
            if idea_id and description:
                edit_idea(idea_id, description, notes)

        elif path == "/delete-idea":
            idea_id = get("id")
            if idea_id:
                delete_idea(idea_id)

        elif path == "/reopen-completed-task":
            num = get("num")
            if num.isdigit():
                reopen_completed_task(int(num))
            self.send_response(303)
            self.send_header("Location", "/completed")
            self.end_headers()
            return

        elif path == "/delete-completed-task":
            num = get("num")
            if num.isdigit():
                delete_completed_task(int(num))
            self.send_response(303)
            self.send_header("Location", "/completed")
            self.end_headers()
            return

        else:
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, fmt, *args):
        pass


_ensure_files()
class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

with ThreadingTCPServer(("", PORT), Handler) as s:
    print(f"Dashboard → http://localhost:{PORT}")
    s.serve_forever()
