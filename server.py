#!/usr/bin/env python3
"""Dashboard server — reads tasks.md, shopping.md, ideas.md and serves HTML."""

import calendar
import http.server
import re
import socketserver
import urllib.parse
from datetime import date as date_cls, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent / "lists"
CHEATSHEETS_DIR = Path(__file__).parent / "cheatsheets"
PORT = 6969

NOTEPAD_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="{size}" height="{size}" fill="none" stroke="currentColor" '
    'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" '
    'aria-hidden="true" class="nookpad-icon">'
    '<rect x="4" y="5" width="16" height="16" rx="2"/>'
    '<line x1="8" y1="11" x2="16" y2="11"/>'
    '<line x1="8" y1="14" x2="16" y2="14"/>'
    '<line x1="8" y1="17" x2="14" y2="17"/>'
    '<circle cx="9" cy="5" r="1.3"/>'
    '<circle cx="15" cy="5" r="1.3"/>'
    '</svg>'
)


def notepad_icon(size_px: int) -> str:
    return NOTEPAD_SVG.format(size=size_px)


FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
    'width="32" height="32">'
    '<rect x="2" y="1" width="12" height="14" rx="2" fill="#2f3e52"/>'
    '<rect x="4" y="4" width="8" height="1.2" rx="0.5" fill="#f5f5f0"/>'
    '<rect x="4" y="7" width="8" height="1.2" rx="0.5" fill="#f5f5f0"/>'
    '<rect x="4" y="10" width="5.5" height="1.2" rx="0.5" fill="#f5f5f0"/>'
    '</svg>'
)
FAVICON_LINK = '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'


_FILE_DEFAULTS = {
    "tasks.md": (
        "| **#** | **Status** | **Priority** | **Due Date** | **Task** | **Notes** | **Category** | **Parent** | **ID** | **Recur** |\n"
        "|-------|------------|--------------|--------------|----------|-----------|---|--------|----|-------|\n"
        "\n## Completed Tasks\n\n"
        "| **#** | **Status** | **Priority** | **Due Date** | **Task** | **Notes** | **Category** | **Parent** | **ID** | **Recur** | **Date Completed** |\n"
        "|-------|------------|--------------|--------------|----------|-----------|---|--------|----|-------|-----------|\n"
    ),
    "ideas.md": "# Ideas\n",
    "notes.md": "# Notes\n",
    "shopping.md": "# Shopping\n",
    "categories.md": "# Categories\n\n| **Code** | **Description** | **Sort Order** |\n|----------|-----------------|----------------|\n",
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

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2, "None": 3}
VALID_PRIORITIES = {"High", "Medium", "Low", "None"}
VALID_RECUR = {"", "daily", "weekly", "monthly", "yearly"}


def html_escape(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _status_for(due_date_str: str) -> str:
    """Return ⚠️ when the due date is strictly before today, else &nbsp;.

    Falls back to &nbsp; on parse failure (matches prior silent-pass behavior).
    Accepts `YYYY-MM-DD` or `YYYY-MM-DD HH:MM`.
    """
    try:
        due = date_cls.fromisoformat(due_date_str.split()[0])
    except (ValueError, IndexError):
        return "&nbsp;"
    return "⚠️" if due < date_cls.today() else "&nbsp;"


def js_escape(s: str, multiline: bool = False) -> str:
    """Escape a Python string for safe interpolation into a JS string literal.

    Mirrors the chain previously inlined at every call site.  When
    `multiline=True`, also encodes `\\n` and strips `\\r` (used by notes whose
    body can contain newlines).
    """
    out = (s.replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace('"', "&quot;")
            .replace("`", "\\`"))
    if multiline:
        out = out.replace("\n", "\\n").replace("\r", "")
    return out


COL_HEADER = "| **#** | **Status** | **Priority** | **Due Date** | **Task** | **Notes** | **Category** | **Parent** | **ID** | **Recur** |"
COL_SEP    = "|---|--------|----------|----------|------|-------|---|---|---|---|"


def _parse_active(content: str):
    """Return (header_lines, rows, completed_section).

    rows is a list of dicts: #, Status, Priority, Due Date, Task, Notes, Category, Parent, ID.
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
                "Category": cols[6] if len(cols) > 6 else "",
                "Parent": cols[7] if len(cols) > 7 else "",
                "ID": cols[8] if len(cols) > 8 else "",
                "Recur": cols[9] if len(cols) > 9 else "",
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
    for r in _completed_rows(completed_section):
        try:
            ids.append(int(r.get("ID", 0) or 0))
        except ValueError:
            pass
    return max(ids, default=0) + 1


def _next_recur_due(due_date: str, recur: str) -> str:
    """Compute the next Due Date for a recurring task.

    Handles month-end clamping (Jan 31 monthly → Feb 28/29) and Feb 29 yearly
    rollover on non-leap years (→ Feb 28). Preserves the HH:MM portion.
    Returns the formatted string `YYYY-MM-DD HH:MM`.
    """
    parts = due_date.split()
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else "00:00"
    y, mo, d = (int(x) for x in date_part.split("-"))
    if recur == "daily":
        nxt = date_cls(y, mo, d) + timedelta(days=1)
        y, mo, d = nxt.year, nxt.month, nxt.day
    elif recur == "weekly":
        nxt = date_cls(y, mo, d) + timedelta(days=7)
        y, mo, d = nxt.year, nxt.month, nxt.day
    elif recur == "monthly":
        mo += 1
        if mo > 12:
            mo = 1
            y += 1
        last = calendar.monthrange(y, mo)[1]
        d = min(d, last)
    elif recur == "yearly":
        y += 1
        last = calendar.monthrange(y, mo)[1]
        d = min(d, last)
    return f"{y:04d}-{mo:02d}-{d:02d} {time_part}"


def _sync_parent_due_dates(rows):
    """Set each parent task's due date to the nearest (earliest) due date among its subtasks."""
    id_to_row = {r["ID"]: r for r in rows if r.get("ID")}

    # Group subtasks by parent ID
    children = {}  # parent_id → [subtask rows]
    for r in rows:
        p = r.get("Parent", "")
        if p:
            children.setdefault(p, []).append(r)

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
        nearest_due = min(dates)
        parent_row["Due Date"] = nearest_due
        parent_row["Status"] = _status_for(nearest_due)


def _render_active(header_lines, rows) -> str:
    lines = header_lines + [COL_HEADER, COL_SEP]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"| {i} | {r['Status']} | {r['Priority']} | {r['Due Date']} | {r['Task']} | {r['Notes']} | {r.get('Category', '')} | {r.get('Parent', '')} | {r.get('ID', '')} | {r.get('Recur', '')} |"
        )
    return "\n".join(lines) + "\n"


def _save_active(header_lines, rows, completed_section: str) -> None:
    """Sync parent due dates, sort, render, and write tasks.md."""
    _sync_parent_due_dates(rows)
    rows.sort(key=lambda r: (r["Due Date"], PRIORITY_ORDER.get(r["Priority"], 99)))
    new_content = _render_active(header_lines, rows)
    if completed_section:
        new_content += "\n" + completed_section
    (BASE / "tasks.md").write_text(new_content)


def _parse_ideas(content: str):
    """Return list of dicts: id, date, desc, parent, notes, category."""
    _, blocks = _idea_blocks(content)
    ideas = []
    for heading, body in blocks:
        m = re.match(r"^## (\d+) \| (\d{4}-\d{2}-\d{2}) \| (.+?)(?:\s*\|\s*(\d*))?$", heading)
        if m:
            notes = ""
            category = ""
            for line in body:
                if line.startswith("notes: "):
                    notes = line[7:]
                elif line.startswith("category: "):
                    category = line[10:].strip()
            ideas.append({
                "id": m.group(1),
                "date": m.group(2),
                "desc": m.group(3).strip(),
                "parent": m.group(4) or "",
                "notes": notes,
                "category": category,
            })
    return ideas


def add_idea(description: str, parent: str = "", notes: str = "", category: str = ""):
    """Append a new idea to ideas.md with the next sequential ID."""
    path = BASE / "ideas.md"
    content = path.read_text()
    ids = re.findall(r"^## (\d+) \|", content, re.MULTILINE)
    next_id = max((int(i) for i in ids), default=0) + 1
    # Validate parent refers to an existing idea
    valid_ids = {m for m in ids}
    if parent not in valid_ids:
        parent = ""
    valid_cats = {c["code"] for c in load_categories() if c["code"]}
    if category and category not in valid_cats:
        category = ""
    today = date_cls.today().isoformat()
    block = f"\n\n## {next_id} | {today} | {description} | {parent}\n"
    if notes:
        block += f"notes: {notes}\n"
    if category:
        block += f"category: {category}\n"
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


def edit_idea(idea_id: str, description: str, notes: str = "", parent: str = "", category: str = ""):
    """Update description, notes, parent, and category of an existing idea, preserving date and sub-points."""
    path = BASE / "ideas.md"
    preamble, blocks = _idea_blocks(path.read_text())

    heading_re = re.compile(r"^## (\d+) \| (\d{4}-\d{2}-\d{2}) \| (.+?)(?:\s*\|\s*(\d*))?\s*$")
    parents = {}
    for heading, _ in blocks:
        m = heading_re.match(heading)
        if m:
            parents[m.group(1)] = m.group(4) or ""
    valid_ids = set(parents.keys())

    # Cycle guard: parent must exist, not be self, and not be a descendant of idea_id.
    if parent:
        descendants = set()
        stack = [idea_id]
        while stack:
            cur = stack.pop()
            for cid, pid in parents.items():
                if pid == cur and cid not in descendants:
                    descendants.add(cid)
                    stack.append(cid)
        if parent == idea_id or parent in descendants or parent not in valid_ids:
            parent = ""

    valid_cats = {c["code"] for c in load_categories() if c["code"]}
    if category and category not in valid_cats:
        category = ""

    new_blocks = []
    for heading, body in blocks:
        m = heading_re.match(heading)
        if m and m.group(1) == idea_id:
            parent_seg = f" | {parent}" if parent else " | "
            heading = f"## {m.group(1)} | {m.group(2)} | {description}{parent_seg}"
            body = [l for l in body if not l.startswith("notes: ") and not l.startswith("category: ")]
            prepended = []
            if notes:
                prepended.append(f"notes: {notes}")
            if category:
                prepended.append(f"category: {category}")
            body = prepended + body
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


_NOTE_HEADER_RE = re.compile(r"^##\s+(\d+)\s*\|\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s*$")


def _parse_notes(content: str):
    """Return list of dicts: {id, timestamp, body}. File order is preserved (newest-first)."""
    notes = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        m = _NOTE_HEADER_RE.match(lines[i])
        if m:
            note_id, ts = m.group(1), m.group(2)
            body_lines = []
            i += 1
            while i < len(lines) and not _NOTE_HEADER_RE.match(lines[i]):
                body_lines.append(lines[i])
                i += 1
            while body_lines and not body_lines[0].strip():
                body_lines.pop(0)
            while body_lines and not body_lines[-1].strip():
                body_lines.pop()
            notes.append({"id": note_id, "timestamp": ts, "body": "\n".join(body_lines)})
        else:
            i += 1
    return notes


def _write_notes(notes):
    path = BASE / "notes.md"
    out = "# Notes\n"
    for n in notes:
        out += f"\n## {n['id']} | {n['timestamp']}\n{n['body']}\n"
    path.write_text(out)


def add_note(body: str):
    path = BASE / "notes.md"
    existing = _parse_notes(path.read_text())
    next_id = max((int(n["id"]) for n in existing), default=0) + 1
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_notes = [{"id": str(next_id), "timestamp": timestamp, "body": body}] + existing
    _write_notes(new_notes)


def edit_note(note_id: str, body: str):
    path = BASE / "notes.md"
    notes = _parse_notes(path.read_text())
    for n in notes:
        if n["id"] == note_id:
            n["body"] = body
            break
    _write_notes(notes)


def delete_note(note_id: str):
    path = BASE / "notes.md"
    notes = _parse_notes(path.read_text())
    notes = [n for n in notes if n["id"] != note_id]
    _write_notes(notes)


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
    """Move a task from active to the Completed Tasks section.

    If the task is recurring (non-empty Recur), also append a fresh active row
    with the next computed Due Date and a new ID.
    """
    path = BASE / "tasks.md"
    header_lines, rows, completed_section = _parse_active(path.read_text())

    found = next((r for r in rows if r["#"].isdigit() and int(r["#"]) == task_num), None)
    if found is None:
        return

    remaining = [r for r in rows if id(r) != id(found)]

    # If the completed task was recurring, schedule the next instance.
    recur = found.get("Recur", "")
    if recur in VALID_RECUR and recur:
        try:
            next_due = _next_recur_due(found["Due Date"], recur)
            next_id = str(_next_task_id(remaining + [found], completed_section))
            next_status = _status_for(next_due)
            remaining.append({
                "#": "",
                "Status": next_status,
                "Priority": found.get("Priority", "Medium"),
                "Due Date": next_due,
                "Task": found.get("Task", ""),
                "Notes": found.get("Notes", ""),
                "Category": found.get("Category", ""),
                "Parent": found.get("Parent", ""),
                "ID": next_id,
                "Recur": recur,
            })
            remaining.sort(key=lambda r: (r["Due Date"], PRIORITY_ORDER.get(r["Priority"], 99)))
        except (ValueError, IndexError):
            pass

    new_content = _render_active(header_lines, remaining)

    existing_comp = _completed_rows(completed_section)
    today = date_cls.today().isoformat()
    existing_comp.append({
        "Status": "✅",
        "Priority": found.get("Priority", ""),
        "Due Date": found.get("Due Date", ""),
        "Task": found.get("Task", ""),
        "Notes": found.get("Notes", ""),
        "Category": found.get("Category", ""),
        "Parent": found.get("Parent", ""),
        "ID": found.get("ID", ""),
        "Recur": found.get("Recur", ""),
        "Date Completed": today,
    })

    header = "## Completed Tasks\n\n| **#** | **Status** | **Priority** | **Due Date** | **Task** | **Notes** | **Category** | **Parent** | **ID** | **Recur** | **Date Completed** |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
    rows_text = ""
    for i, r in enumerate(existing_comp, 1):
        rows_text += f"| {i} | {r.get('Status','✅')} | {r.get('Priority','')} | {r.get('Due Date','')} | {r.get('Task','')} | {r.get('Notes','')} | {r.get('Category','')} | {r.get('Parent','')} | {r.get('ID','')} | {r.get('Recur','')} | {r.get('Date Completed','')} |\n"
    path.write_text(new_content + "\n" + header + rows_text)


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
    header = "## Completed Tasks\n\n| **#** | **Status** | **Priority** | **Due Date** | **Task** | **Notes** | **Category** | **Parent** | **ID** | **Recur** | **Date Completed** |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
    rows_text = ""
    for i, r in enumerate(kept, 1):
        rows_text += f"| {i} | {r.get('Status','✅')} | {r.get('Priority','')} | {r.get('Due Date','')} | {r.get('Task','')} | {r.get('Notes','')} | {r.get('Category','')} | {r.get('Parent','')} | {r.get('ID','')} | {r.get('Recur','')} | {r.get('Date Completed','')} |\n"
    new_completed = header + rows_text

    # Re-add to active list
    header_lines, rows, _ = _parse_active(active_part)
    due_raw = found.get("Due Date", "")
    status = _status_for(due_raw) if due_raw else "&nbsp;"
    new_row = {
        "#": str(len(rows) + 1),
        "Status": status,
        "Priority": found.get("Priority", "Medium"),
        "Due Date": due_raw,
        "Task": found.get("Task", ""),
        "Notes": found.get("Notes", ""),
        "Category": found.get("Category", ""),
        "Parent": found.get("Parent", ""),
        "ID": found.get("ID", ""),
        "Recur": found.get("Recur", ""),
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
    header = "## Completed Tasks\n\n| **#** | **Status** | **Priority** | **Due Date** | **Task** | **Notes** | **Category** | **Parent** | **ID** | **Recur** | **Date Completed** |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
    rows_text = ""
    for i, r in enumerate(kept, 1):
        rows_text += f"| {i} | {r.get('Status','✅')} | {r.get('Priority','')} | {r.get('Due Date','')} | {r.get('Task','')} | {r.get('Notes','')} | {r.get('Category','')} | {r.get('Parent','')} | {r.get('ID','')} | {r.get('Recur','')} | {r.get('Date Completed','')} |\n"
    path.write_text(active_part + header + rows_text)


def edit_task(task_num: int, due_date: str, task: str, notes: str, priority: str, parent: str = "", category: str = "", recur: str = ""):
    """Update a task's fields in-place, re-sort, and save."""
    if priority not in VALID_PRIORITIES:
        priority = "Medium"
    if recur not in VALID_RECUR:
        recur = ""
    path = BASE / "tasks.md"
    header_lines, rows, completed_section = _parse_active(path.read_text())
    # Validate parent ID exists and isn't the task itself
    valid_ids = {r["ID"] for r in rows if r.get("ID")}
    editing_id = next((r["ID"] for r in rows if r["#"].isdigit() and int(r["#"]) == task_num), None)
    if parent not in valid_ids or parent == editing_id:
        parent = ""
    for r in rows:
        if r["#"].isdigit() and int(r["#"]) == task_num:
            r["Status"] = _status_for(due_date)
            r["Due Date"] = due_date
            r["Task"] = task
            r["Notes"] = notes
            r["Priority"] = priority
            r["Parent"] = parent
            r["Category"] = category
            r["Recur"] = recur
            break
    _save_active(header_lines, rows, completed_section)


SNOOZE_DELTAS = {"1d": timedelta(days=1), "1w": timedelta(days=7)}


def snooze_task(task_id: str, delta: str):
    """Push a task's due date forward by a preset delta, preserving HH:MM."""
    if delta not in SNOOZE_DELTAS:
        return
    header_lines, rows, completed_section = _parse_active((BASE / "tasks.md").read_text())
    for r in rows:
        if r.get("ID") != task_id:
            continue
        due_raw = r.get("Due Date", "")
        parts = due_raw.split()
        date_part = parts[0] if parts else ""
        time_part = parts[1] if len(parts) > 1 else "00:00"
        try:
            new_date = date_cls.fromisoformat(date_part) + SNOOZE_DELTAS[delta]
        except ValueError:
            return
        new_due = f"{new_date.isoformat()} {time_part}"
        r["Due Date"] = new_due
        r["Status"] = _status_for(new_due)
        break
    else:
        return
    _save_active(header_lines, rows, completed_section)


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


def add_task(due_date: str, task: str, notes: str, priority: str = "Medium", parent: str = "", category: str = "", recur: str = ""):
    """Append a task to tasks.md, re-sort active tasks, renumber, and save."""
    if priority not in VALID_PRIORITIES:
        priority = "Medium"
    if recur not in VALID_RECUR:
        recur = ""

    header_lines, rows, completed_section = _parse_active((BASE / "tasks.md").read_text())

    # Validate parent refers to an existing task ID
    valid_ids = {r["ID"] for r in rows if r.get("ID")}
    if parent not in valid_ids:
        parent = ""

    new_id = str(_next_task_id(rows, completed_section))
    rows.append({"#": "", "Status": _status_for(due_date), "Priority": priority, "Due Date": due_date, "Task": task, "Notes": notes, "Category": category, "Parent": parent, "ID": new_id, "Recur": recur})
    _save_active(header_lines, rows, completed_section)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

def load_categories():
    """Return list of dicts {code, description, sort_order} sorted by sort_order."""
    content = read("categories.md")
    rows = parse_md_table(content)
    result = []
    for r in rows:
        try:
            sort_order = int(r.get("Sort Order", "0") or "0")
        except ValueError:
            sort_order = 0
        result.append({
            "code": r.get("Code", "").strip(),
            "description": r.get("Description", "").strip(),
            "sort_order": sort_order,
        })
    return sorted(result, key=lambda r: r["sort_order"])


def save_categories(cats):
    """Write categories list back to categories.md."""
    path = BASE / "categories.md"
    lines = [
        "# Categories\n",
        "| **Code** | **Description** | **Sort Order** |",
        "|----------|-----------------|----------------|",
    ]
    for c in cats:
        lines.append(f"| {c['code']} | {c['description']} | {c['sort_order']} |")
    path.write_text("\n".join(lines) + "\n")


def add_category(code: str, description: str, sort_order: int):
    cats = load_categories()
    cats.append({"code": code, "description": description, "sort_order": sort_order})
    cats.sort(key=lambda c: c["sort_order"])
    save_categories(cats)


def edit_category(original_code: str, code: str, description: str, sort_order: int):
    cats = load_categories()
    for c in cats:
        if c["code"] == original_code:
            c["code"] = code
            c["description"] = description
            c["sort_order"] = sort_order
            break
    cats.sort(key=lambda c: c["sort_order"])
    save_categories(cats)


def delete_category(code: str):
    cats = [c for c in load_categories() if c["code"] != code]
    save_categories(cats)


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


def _completed_rows(text: str):
    """Parse the rows inside a `## Completed Tasks` section.

    Accepts either the section alone (as returned by `_parse_active`) or a
    larger body that contains it; returns `[]` when the marker is absent.
    """
    marker = "## Completed Tasks"
    if not text or marker not in text:
        return []
    return parse_md_table(text.split(marker, 1)[1])


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
        if not p or p == "None":
            return ""
        cls = {"High": "high", "Medium": "medium", "Low": "low"}.get(p, "")
        return f'<span class="badge {cls}">{p}</span>'

    def make_row(r, indent=False, is_parent=False):
        cls = row_class(r)
        icon = "⚠️" if cls == "overdue" else "·"
        due_raw = r.get("Due Date", "")
        due = html_escape(due_raw.replace(" 00:00", ""))
        due_date_val = html_escape(due_raw.split()[0] if due_raw else "")
        num = html_escape(r.get("#", ""))
        task_id = html_escape(r.get("ID", ""))
        task_text = html_escape(r.get("Task", ""))
        notes_text = html_escape(r.get("Notes", ""))
        priority = r.get("Priority", "Medium")
        task_js = js_escape(r.get("Task", ""))
        notes_js = js_escape(r.get("Notes", ""))
        parent_id_js = html_escape(r.get("Parent", ""))
        category_js = html_escape(r.get("Category", ""))
        recur = r.get("Recur", "")
        recur_js = html_escape(recur)
        recur_badge = f' <span class="recur-badge" title="{recur.capitalize()}">↻</span>' if recur else ""
        indent_prefix = '<span class="subtask-indent">↳</span>' if indent else ""
        priority_cell = "" if is_parent else priority_badge(priority)
        classes = [cls]
        if indent:
            classes.append("subtask")
        if is_parent:
            classes.append("parent-task")
        row_cls = " ".join(c for c in classes if c)
        return f"""<tr class="{row_cls}">
            <td>{icon}</td>
            <td>{priority_cell}</td>
            <td class="due">{due}</td>
            <td>{indent_prefix}{task_text}{recur_badge}</td>
            <td class="notes">{notes_text}</td>
            <td class="action-cell">
                <form method="POST" action="/complete-task" style="display:inline"><input type="hidden" name="num" value="{num}"><button type="submit" class="done-btn" title="Mark complete">✓</button></form>
                <span class="task-hover-actions">
                    <form method="POST" action="/snooze-task" style="display:inline"><input type="hidden" name="id" value="{task_id}"><input type="hidden" name="delta" value="1d"><button type="submit" class="snooze-btn" title="Snooze +1 day">+1d</button></form>
                    <form method="POST" action="/snooze-task" style="display:inline"><input type="hidden" name="id" value="{task_id}"><input type="hidden" name="delta" value="1w"><button type="submit" class="snooze-btn" title="Snooze +1 week">+1w</button></form>
                    <button type="button" class="edit-btn" title="Edit task" onclick="openEditTask('{num}','{task_js}','{notes_js}','{due_date_val}','{priority}','{parent_id_js}','{category_js}','{recur_js}')">✎</button>
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

    parent_ids = set(sub_of.keys())

    cats = load_categories()
    cat_meta = {c["code"]: c for c in cats if c["code"]}

    buckets = {}
    for r in top_level:
        code = r.get("Category", "").strip()
        key = code if code in cat_meta else ""
        buckets.setdefault(key, []).append(r)

    def group_sort_key(code):
        meta = cat_meta.get(code)
        return (meta["sort_order"], meta["description"].lower())

    ordered_keys = sorted([k for k in buckets if k != ""], key=group_sort_key)
    if "" in buckets:
        ordered_keys.append("")

    groups_html = ""
    for key in ordered_keys:
        bucket = buckets[key]
        group_rows = ""
        task_count = 0
        for r in bucket:
            is_parent = r.get("ID", "") in parent_ids
            group_rows += make_row(r, is_parent=is_parent)
            task_count += 1
            for child in sub_of.get(r.get("ID", ""), []):
                group_rows += make_row(child, indent=True)
                task_count += 1
        label = html_escape(cat_meta[key]["description"]) if key else "None"
        groups_html += (
            f'<tbody class="cat-group">'
            f'<tr class="cat-header" onclick="toggleCategory(this)">'
            f'<td colspan="6"><span class="cat-caret">▼</span> {label} '
            f'<span class="cat-count">{task_count}</span></td></tr>'
            f'{group_rows}'
            f'</tbody>'
        )

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

    # Category selector options
    cat_opts = '<option value="">— No Category —</option>'
    for c in cats:
        cat_opts += f'<option value="{html_escape(c["code"])}">{html_escape(c["description"])}</option>'

    return f"""<section class="card tasks-card">
        <h2>Tasks <span class="count">{total}</span>{badge_extra}
            <button class="add-btn" onclick="document.getElementById('task-modal').classList.add('open')">+ Add</button>
        </h2>
        <table>
            <thead><tr><th></th><th>Priority</th><th>Due</th><th>Task</th><th>Notes</th><th></th></tr></thead>
            {groups_html}
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
                        <option value="None">None</option>
                    </select>
                </label>
                <label>Category
                    <select name="category">{cat_opts}</select>
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
                <label>Recur
                    <select name="recur">
                        <option value="">None</option>
                        <option value="daily">Daily</option>
                        <option value="weekly">Weekly</option>
                        <option value="monthly">Monthly</option>
                        <option value="yearly">Yearly</option>
                    </select>
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
                        <option value="None">None</option>
                    </select>
                </label>
                <label>Category
                    <select name="category" id="edit-task-category">{cat_opts}</select>
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
                <label>Recur
                    <select name="recur" id="edit-task-recur">
                        <option value="">None</option>
                        <option value="daily">Daily</option>
                        <option value="weekly">Weekly</option>
                        <option value="monthly">Monthly</option>
                        <option value="yearly">Yearly</option>
                    </select>
                </label>
                <div class="modal-actions">
                    <button type="button" class="cancel-btn" onclick="document.getElementById('task-edit-modal').classList.remove('open')">Cancel</button>
                    <button type="submit" class="submit-btn">Save</button>
                </div>
            </form>
        </div>
    </div>

    <script>
    function openEditTask(num, task, notes, due, priority, parentId, category, recur) {{
        document.getElementById('edit-task-num').value = num;
        document.getElementById('edit-task-task').value = task;
        document.getElementById('edit-task-notes').value = notes;
        document.getElementById('edit-task-due').value = due;
        document.getElementById('edit-task-priority').value = priority;
        document.getElementById('edit-task-parent').value = parentId || '';
        document.getElementById('edit-task-category').value = category || '';
        document.getElementById('edit-task-recur').value = recur || '';
        document.getElementById('task-edit-modal').classList.add('open');
    }}
    function toggleCategory(headerTr) {{
        const tbody = headerTr.parentElement;
        const caret = headerTr.querySelector('.cat-caret');
        tbody.classList.toggle('collapsed');
        caret.textContent = tbody.classList.contains('collapsed') ? '▶' : '▼';
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
    today_str = date_cls.today().isoformat()
    cats = load_categories()
    cat_meta = {c["code"]: c for c in cats if c["code"]}
    cat_opts = '<option value="">— No Category —</option>'
    for c in cats:
        if c["code"]:
            cat_opts += f'<option value="{html_escape(c["code"])}">{html_escape(c["description"])}</option>'
    promote_cat_opts = cat_opts

    def make_item(r, indent=False):
        id_ = html_escape(r["id"])
        title = html_escape(r["desc"])
        date = html_escape(r["date"])
        notes = html_escape(r.get("notes", ""))
        desc_js = js_escape(r["desc"])
        notes_js = js_escape(r.get("notes", ""))
        parent_js = html_escape(r.get("parent", ""))
        category_js = html_escape(r.get("category", ""))
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
            f'<button class="edit-btn" onclick="openPromoteIdea(\'{id_}\',\'{desc_js}\',\'{category_js}\')" title="Convert to task">➜</button>'
            f'<button class="edit-btn" onclick="openEditIdea(\'{id_}\',\'{desc_js}\',\'{notes_js}\',\'{parent_js}\',\'{category_js}\')" title="Edit idea">✎</button>'
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

    buckets = {}
    for r in top_level:
        code = r.get("category", "").strip()
        key = code if code in cat_meta else ""
        buckets.setdefault(key, []).append(r)

    def group_sort_key(code):
        meta = cat_meta.get(code)
        return (meta["sort_order"], meta["description"].lower())

    ordered_keys = sorted([k for k in buckets if k != ""], key=group_sort_key)
    if "" in buckets:
        ordered_keys.append("")

    groups_html = ""
    for key in ordered_keys:
        bucket = buckets[key]
        group_items = ""
        idea_count = 0
        for r in bucket:
            group_items += make_item(r)
            idea_count += 1
            for child in sub_of.get(r["id"], []):
                group_items += make_item(child, indent=True)
                idea_count += 1
        label = html_escape(cat_meta[key]["description"]) if key else "None"
        groups_html += (
            f'<section class="idea-cat-group">'
            f'<h3 class="cat-header" onclick="toggleIdeaCategory(this)">'
            f'<span class="cat-caret">▼</span> {label} '
            f'<span class="cat-count">{idea_count}</span></h3>'
            f'<ul class="ideas">{group_items}</ul>'
            f'</section>'
        )

    parent_opts = '<option value="">None (top-level idea)</option>'
    for r in ideas:
        id_ = html_escape(r["id"])
        label = html_escape(r["desc"])
        parent_opts += f'<option value="{id_}">#{id_} — {label}</option>'

    return f"""<section class="card ideas-card">
        <h2>Ideas <span class="count">{len(ideas)}</span>
            <button class="add-btn" onclick="document.getElementById('idea-modal').classList.add('open')">+ Add</button>
        </h2>
        {groups_html}
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
                <label>Category
                    <select name="category">{cat_opts}</select>
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
                <label>Category
                    <select name="category" id="edit-idea-category">{cat_opts}</select>
                </label>
                <label>Parent Idea
                    <select name="parent" id="edit-idea-parent">{parent_opts}</select>
                </label>
                <div class="modal-actions">
                    <button type="button" class="cancel-btn" onclick="document.getElementById('idea-edit-modal').classList.remove('open')">Cancel</button>
                    <button type="submit" class="submit-btn">Save</button>
                </div>
            </form>
        </div>
    </div>

    <div id="idea-promote-modal" class="modal-overlay" onclick="if(event.target===this)this.classList.remove('open')">
        <div class="modal">
            <h3>Convert Idea to Task</h3>
            <form method="POST" action="/idea-to-task">
                <input type="hidden" name="idea_id" id="promote-idea-id">
                <label>Idea
                    <input type="text" id="promote-idea-desc" disabled>
                </label>
                <label>Due Date
                    <input type="date" name="due_date" id="promote-idea-due" value="{today_str}" required>
                </label>
                <label>Priority
                    <select name="priority" id="promote-idea-priority">
                        <option value="None" selected>None</option>
                        <option value="High">High</option>
                        <option value="Medium">Medium</option>
                        <option value="Low">Low</option>
                    </select>
                </label>
                <label>Category
                    <select name="category" id="promote-idea-category">{promote_cat_opts}</select>
                </label>
                <div class="modal-actions">
                    <button type="button" class="cancel-btn" onclick="document.getElementById('idea-promote-modal').classList.remove('open')">Cancel</button>
                    <button type="submit" class="submit-btn">Create Task</button>
                </div>
            </form>
        </div>
    </div>

    <script>
    function openEditIdea(id, desc, notes, parent, category) {{
        document.getElementById('edit-idea-id').value = id;
        document.getElementById('edit-idea-desc').value = desc;
        document.getElementById('edit-idea-notes').value = notes || '';
        document.getElementById('edit-idea-parent').value = parent || '';
        document.getElementById('edit-idea-category').value = category || '';
        document.getElementById('idea-edit-modal').classList.add('open');
    }}
    function openPromoteIdea(id, desc, category) {{
        document.getElementById('promote-idea-id').value = id;
        document.getElementById('promote-idea-desc').value = desc;
        document.getElementById('promote-idea-due').value = '{today_str}';
        document.getElementById('promote-idea-priority').value = 'None';
        document.getElementById('promote-idea-category').value = category || '';
        document.getElementById('idea-promote-modal').classList.add('open');
    }}
    function toggleIdeaCategory(headerEl) {{
        const section = headerEl.parentElement;
        const caret = headerEl.querySelector('.cat-caret');
        section.classList.toggle('collapsed');
        caret.textContent = section.classList.contains('collapsed') ? '▶' : '▼';
    }}
    </script>"""


def cheatsheet_links():
    links = '<a href="/completed" class="nav-link">Completed Tasks</a>'
    links += '<a href="/review" class="nav-link">Review</a>'
    links += '<a href="/agenda" class="nav-link">Agenda</a>'
    links += '<a href="/categories" class="nav-link">Categories</a>'
    links += '<a href="/notes" class="nav-link">Notes</a>'
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
.nookpad-icon {
    vertical-align: -0.15em;
    flex-shrink: 0;
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
.snooze-btn {
    background: transparent;
    border: 1px solid #334155;
    border-radius: 4px;
    color: #475569;
    font-size: 0.7rem;
    padding: 0.1rem 0.35rem;
    cursor: pointer;
    line-height: 1.4;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.snooze-btn:hover { background: #422006; border-color: #b45309; color: #fcd34d; }
.action-cell { width: 1px; white-space: nowrap; padding-right: 0.25rem; vertical-align: middle; }
.task-hover-actions { display: inline-flex; gap: 0.3rem; opacity: 0; transition: opacity 0.15s; vertical-align: middle; }
tr:hover .task-hover-actions { opacity: 1; }
tr.subtask td { background: #182032; }
tr.subtask td:first-child { color: #64748b; }
.subtask-indent { color: #475569; margin-right: 0.35rem; font-size: 0.8rem; }
.recur-badge { margin-left: 0.3rem; color: #6b7280; font-size: 0.85em; }
tr.parent-task td { background: #141c2b; color: #94a3b8; }
tr.parent-task td:first-child { color: #475569; }
tr.parent-task .due { color: #64748b; }
tr.cat-header td {
    background: #0f2942;
    color: #7dd3fc;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.4rem 0.6rem;
    cursor: pointer;
    user-select: none;
    border-bottom: 1px solid #1e4a7a;
}
tr.cat-header:hover td { background: #1e4a7a; color: #e0f2fe; }
.cat-caret { display: inline-block; width: 0.9rem; color: #7dd3fc; font-size: 0.7rem; }
.cat-count { color: #64748b; font-size: 0.7rem; margin-left: 0.35rem; font-weight: 500; text-transform: none; }
tbody.cat-group.collapsed tr:not(.cat-header) { display: none; }
.idea-cat-group h3.cat-header {
    background: #0f2942;
    color: #7dd3fc;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.4rem 0.6rem;
    margin: 0;
    cursor: pointer;
    user-select: none;
    border-bottom: 1px solid #1e4a7a;
}
.idea-cat-group h3.cat-header:hover { background: #1e4a7a; color: #e0f2fe; }
.idea-cat-group.collapsed > ul { display: none; }
.agenda-heading {
    margin: 1.25rem 0 0.4rem;
    font-size: 0.95rem;
    color: #7dd3fc;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.agenda-heading:first-of-type { margin-top: 0.25rem; }
.agenda-count { color: #64748b; font-size: 0.75rem; margin-left: 0.35rem; font-weight: 500; }
.agenda-table { width: 100%; }
.agenda-cat { color: #64748b; font-size: 0.75rem; margin-left: 0.4rem; text-transform: uppercase; letter-spacing: 0.04em; }
.review-bars { width: 100%; border-collapse: collapse; }
.review-bars td { padding: 0.25rem 0.4rem; vertical-align: middle; }
.review-bar-label {
    font-size: 0.8rem;
    color: #94a3b8;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    width: 1%;
}
.review-bar-cell { position: relative; }
.review-bar-fill {
    display: inline-block;
    height: 0.85rem;
    background: #3b82f6;
    border-radius: 2px;
    vertical-align: middle;
    transition: width 0.2s;
}
.review-bar-count {
    font-size: 0.78rem;
    color: #cbd5e1;
    margin-left: 0.5rem;
    font-variant-numeric: tabular-nums;
}
.shop-item { flex: 1; }
.notes-list { display: flex; flex-direction: column; gap: 0.65rem; }
.note-card { padding: 0.75rem 0.9rem; border-radius: 6px; background: #0f172a; border: 1px solid #1e293b; position: relative; }
.note-card:hover { border-color: #334155; }
.note-head { display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; color: #64748b; }
.note-ts { font-variant-numeric: tabular-nums; letter-spacing: 0.02em; }
.note-id { color: #475569; margin-right: 0.4rem; }
.note-body { margin-top: 0.4rem; white-space: pre-wrap; color: #e2e8f0; font-size: 0.95rem; line-height: 1.45; }
.note-card .task-hover-actions { opacity: 0; transition: opacity 0.1s; }
.note-card:hover .task-hover-actions { opacity: 1; }
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
  <title>NookPad</title>
  <link rel="stylesheet" href="/style.css">
  {FAVICON_LINK}
  <meta http-equiv="refresh" content="30">
</head>
<body>
  <header>
    <h1>{notepad_icon(28)} NookPad</h1>
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
  {FAVICON_LINK}
</head>
<body>
  <header>
    <a href="/" class="back">← {notepad_icon(18)} NookPad</a>
  </header>
  <main class="cheatsheet">
    {body}
  </main>
</body>
</html>"""


def completed_tasks_page():
    content = read("tasks.md")
    comp_rows = _completed_rows(content)

    def priority_badge(p):
        if not p or p == "None":
            return ""
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

    cats = load_categories()
    cat_meta = {c["code"]: c for c in cats if c["code"]}

    buckets = {}
    for r in top_level_comp:
        code = r.get("Category", "").strip()
        key = code if code in cat_meta else ""
        buckets.setdefault(key, []).append(r)

    ordered_keys = sorted(
        [k for k in buckets if k != ""],
        key=lambda k: (cat_meta[k]["sort_order"], cat_meta[k]["description"].lower()),
    )
    if "" in buckets:
        ordered_keys.append("")

    groups_html = ""
    for key in ordered_keys:
        bucket = buckets[key]
        group_rows = ""
        task_count = 0
        for r in bucket:
            group_rows += make_comp_row(r)
            task_count += 1
            for child in sub_of.get(r.get("ID", ""), []):
                group_rows += make_comp_row(child, indent=True)
                task_count += 1
        label = html_escape(cat_meta[key]["description"]) if key else "None"
        groups_html += (
            f'<tbody class="cat-group">'
            f'<tr class="cat-header" onclick="toggleCategory(this)">'
            f'<td colspan="7"><span class="cat-caret">▼</span> {label} '
            f'<span class="cat-count">{task_count}</span></td></tr>'
            f'{group_rows}'
            f'</tbody>'
        )

    total = len(comp_rows)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Completed Tasks</title>
  <link rel="stylesheet" href="/style.css">
  {FAVICON_LINK}
</head>
<body>
  <header>
    <a href="/" class="back">← {notepad_icon(18)} NookPad</a>
  </header>
  <main style="max-width:900px;margin:0 auto;">
    <div class="card">
      <h2>Completed Tasks <span class="count">{total}</span></h2>
      <table>
        <thead><tr><th></th><th>Priority</th><th>Due</th><th>Task</th><th>Notes</th><th>Completed</th><th></th></tr></thead>
        {groups_html}
      </table>
    </div>
  </main>
  <script>
  function toggleCategory(headerTr) {{
      const tbody = headerTr.parentElement;
      const caret = headerTr.querySelector('.cat-caret');
      tbody.classList.toggle('collapsed');
      caret.textContent = tbody.classList.contains('collapsed') ? '▶' : '▼';
  }}
  </script>
</body>
</html>"""


def notes_page():
    notes = _parse_notes(read("notes.md"))

    def make_card(n):
        nid = html_escape(n["id"])
        ts = html_escape(n["timestamp"])
        body_html = html_escape(n["body"])
        body_js = js_escape(n["body"].replace("&", "&amp;"), multiline=True)
        return f"""<div class="note-card">
          <div class="note-head">
            <span><span class="note-id">#{nid}</span><span class="note-ts">{ts}</span></span>
            <span class="task-hover-actions">
              <button type="button" class="edit-btn" title="Edit note" onclick="openEditNote('{nid}','{body_js}')">✎</button>
              <form method="POST" action="/delete-note" style="display:inline">
                <input type="hidden" name="id" value="{nid}">
                <button type="submit" class="del-btn" title="Delete note" onclick="return confirm('Delete this note?')">✕</button>
              </form>
            </span>
          </div>
          <div class="note-body">{body_html}</div>
        </div>"""

    cards_html = "".join(make_card(n) for n in notes) or \
        '<p class="empty"><em>No notes yet. Click + Add to write one.</em></p>'
    total = len(notes)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Notes</title>
  <link rel="stylesheet" href="/style.css">
  {FAVICON_LINK}
</head>
<body>
  <header>
    <a href="/" class="back">← {notepad_icon(18)} NookPad</a>
  </header>
  <main style="max-width:800px;margin:0 auto;">
    <div class="card">
      <h2>Notes <span class="count">{total}</span>
        <button class="add-btn" onclick="document.getElementById('note-modal').classList.add('open')">+ Add</button>
      </h2>
      <div class="notes-list">{cards_html}</div>
    </div>
  </main>

  <div id="note-modal" class="modal-overlay" onclick="if(event.target===this)this.classList.remove('open')">
    <div class="modal">
      <h3>Add Note</h3>
      <form method="POST" action="/add-note">
        <label>Note
          <textarea name="body" rows="6" required placeholder="Quick thought, URL, reminder..."></textarea>
        </label>
        <div class="modal-actions">
          <button type="button" class="cancel-btn" onclick="document.getElementById('note-modal').classList.remove('open')">Cancel</button>
          <button type="submit" class="submit-btn">Add Note</button>
        </div>
      </form>
    </div>
  </div>

  <div id="note-edit-modal" class="modal-overlay" onclick="if(event.target===this)this.classList.remove('open')">
    <div class="modal">
      <h3>Edit Note</h3>
      <form method="POST" action="/edit-note">
        <input type="hidden" name="id" id="edit-note-id">
        <label>Note
          <textarea name="body" id="edit-note-body" rows="6" required></textarea>
        </label>
        <div class="modal-actions">
          <button type="button" class="cancel-btn" onclick="document.getElementById('note-edit-modal').classList.remove('open')">Cancel</button>
          <button type="submit" class="submit-btn">Save</button>
        </div>
      </form>
    </div>
  </div>

  <script>
  function openEditNote(id, body) {{
    document.getElementById('edit-note-id').value = id;
    document.getElementById('edit-note-body').value = body;
    document.getElementById('note-edit-modal').classList.add('open');
  }}
  </script>
</body>
</html>"""


def agenda_page():
    _, active, _ = _parse_active(read("tasks.md"))
    today = date_cls.today()
    window_end = today + timedelta(days=13)

    def priority_badge(p):
        if not p or p == "None":
            return ""
        cls = {"High": "high", "Medium": "medium", "Low": "low"}.get(p, "")
        return f'<span class="badge {cls}">{p}</span>'

    priority_rank = {"High": 0, "Medium": 1, "Low": 2}

    def sort_key(r):
        return (priority_rank.get(r.get("Priority", ""), 3), r.get("Task", "").lower())

    overdue, today_tasks, tomorrow_tasks, unscheduled = [], [], [], []
    by_day = {}
    tomorrow = today + timedelta(days=1)

    for r in active:
        due_raw = r.get("Due Date", "").strip()
        if not due_raw:
            unscheduled.append(r)
            continue
        try:
            d = date_cls.fromisoformat(due_raw.split()[0])
        except ValueError:
            unscheduled.append(r)
            continue
        if d < today:
            overdue.append(r)
        elif d == today:
            today_tasks.append(r)
        elif d == tomorrow:
            tomorrow_tasks.append(r)
        elif d <= window_end:
            by_day.setdefault(d, []).append(r)

    def make_row(r):
        priority = r.get("Priority", "Medium")
        task_text = html_escape(r.get("Task", ""))
        category = html_escape(r.get("Category", "").strip())
        cat_span = f'<span class="agenda-cat">{category}</span>' if category else ""
        due_raw = r.get("Due Date", "").strip()
        due_display = html_escape(due_raw.replace(" 00:00", "")) if due_raw else ""
        return (
            f'<tr>'
            f'<td>{priority_badge(priority)}</td>'
            f'<td>{task_text} {cat_span}</td>'
            f'<td class="due">{due_display}</td>'
            f'</tr>'
        )

    def render_group(title, rows, sort_overdue=False):
        if not rows:
            return ""
        if sort_overdue:
            rows = sorted(rows, key=lambda r: (r.get("Due Date", ""), *sort_key(r)))
        else:
            rows = sorted(rows, key=sort_key)
        body = "".join(make_row(r) for r in rows)
        return (
            f'<h3 class="agenda-heading">{title} '
            f'<span class="agenda-count">{len(rows)}</span></h3>'
            f'<table class="agenda-table"><tbody>{body}</tbody></table>'
        )

    sections = []
    sections.append(render_group("Overdue", overdue, sort_overdue=True))
    sections.append(render_group(f"Today ({today.strftime('%a %b %d')})", today_tasks))
    sections.append(render_group(
        f"Tomorrow ({tomorrow.strftime('%a %b %d')})", tomorrow_tasks
    ))
    for offset in range(2, 14):
        d = today + timedelta(days=offset)
        if d in by_day:
            sections.append(render_group(d.strftime('%a %b %d'), by_day[d]))
    sections.append(render_group("Unscheduled", unscheduled))

    body_html = "".join(sections)
    if not body_html:
        body_html = '<p class="empty"><em>Nothing scheduled in the next 14 days.</em></p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agenda</title>
  <link rel="stylesheet" href="/style.css">
  {FAVICON_LINK}
</head>
<body>
  <header>
    <a href="/" class="back">← {notepad_icon(18)} NookPad</a>
  </header>
  <main style="max-width:800px;margin:0 auto;">
    <div class="card">
      <h2>Agenda</h2>
      {body_html}
    </div>
  </main>
</body>
</html>"""


def review_page():
    _, active, completed_section = _parse_active(read("tasks.md"))
    comp_rows = _completed_rows(completed_section)

    today = date_cls.today()
    monday = today - timedelta(days=today.weekday())

    cat_desc = {c["code"]: c["description"] for c in load_categories() if c["code"]}

    def priority_badge(p):
        if not p or p == "None":
            return ""
        cls = {"High": "high", "Medium": "medium", "Low": "low"}.get(p, "")
        return f'<span class="badge {cls}">{p}</span>'

    # Section 1: Completions this week
    week_completions = []
    for r in comp_rows:
        date_done = r.get("Date Completed", "").strip()
        try:
            d = date_cls.fromisoformat(date_done)
        except ValueError:
            continue
        if d >= monday:
            week_completions.append(r)

    cat_buckets = {}
    for r in week_completions:
        code = r.get("Category", "").strip()
        label = cat_desc.get(code, "Uncategorized") if code else "Uncategorized"
        cat_buckets[label] = cat_buckets.get(label, 0) + 1

    if cat_buckets:
        sorted_labels = sorted(
            cat_buckets.keys(),
            key=lambda k: (k == "Uncategorized", k.lower()),
        )
        bucket_rows = "".join(
            f'<tr><td>{html_escape(k)}</td>'
            f'<td class="due">{cat_buckets[k]}</td></tr>'
            for k in sorted_labels
        )
        week_body = f'<table class="agenda-table"><tbody>{bucket_rows}</tbody></table>'
    else:
        week_body = '<p class="empty"><em>No tasks completed this week yet.</em></p>'

    week_section = (
        f'<h3 class="agenda-heading">This Week '
        f'<span class="agenda-count">{len(week_completions)}</span></h3>'
        f'{week_body}'
    )

    # Section 2: Overdue
    overdue = []
    for r in active:
        due_raw = r.get("Due Date", "").strip()
        if not due_raw:
            continue
        try:
            d = date_cls.fromisoformat(due_raw.split()[0])
        except ValueError:
            continue
        if d < today:
            overdue.append((r, d))
    overdue.sort(key=lambda pair: pair[1])

    if overdue:
        overdue_rows = ""
        for r, d in overdue:
            task = html_escape(r.get("Task", ""))
            due_display = html_escape(r.get("Due Date", "").replace(" 00:00", ""))
            days = (today - d).days
            overdue_rows += (
                f'<tr><td>{task}</td>'
                f'<td class="due">{due_display}</td>'
                f'<td class="due">{days}d</td></tr>'
            )
        overdue_body = f'<table class="agenda-table"><tbody>{overdue_rows}</tbody></table>'
    else:
        overdue_body = '<p class="empty"><em>Nothing overdue.</em></p>'

    overdue_section = (
        f'<h3 class="agenda-heading">Overdue '
        f'<span class="agenda-count">{len(overdue)}</span></h3>'
        f'{overdue_body}'
    )

    # Section 3: Oldest open
    def id_key(r):
        try:
            return int(r.get("ID", "") or 0)
        except ValueError:
            return 0

    oldest = sorted(active, key=id_key)[:5]

    if oldest:
        oldest_rows = ""
        for r in oldest:
            task = html_escape(r.get("Task", ""))
            due_raw = r.get("Due Date", "").strip()
            due_display = html_escape(due_raw.replace(" 00:00", "")) if due_raw else ""
            oldest_rows += (
                f'<tr><td>{task}</td>'
                f'<td class="due">{due_display}</td>'
                f'<td>{priority_badge(r.get("Priority", ""))}</td></tr>'
            )
        oldest_body = f'<table class="agenda-table"><tbody>{oldest_rows}</tbody></table>'
    else:
        oldest_body = '<p class="empty"><em>No open tasks.</em></p>'

    oldest_section = (
        f'<h3 class="agenda-heading">Oldest Open</h3>'
        f'{oldest_body}'
    )

    # Section 4: Completions per day, last 7 days
    day_counts = {today - timedelta(days=i): 0 for i in range(7)}
    for r in comp_rows:
        date_done = r.get("Date Completed", "").strip()
        try:
            d = date_cls.fromisoformat(date_done)
        except ValueError:
            continue
        if d in day_counts:
            day_counts[d] += 1

    max_count = max(day_counts.values())
    bar_rows = ""
    for d in sorted(day_counts.keys()):
        count = day_counts[d]
        width_pct = int((count / max_count) * 100) if max_count > 0 else 0
        label = d.strftime("%a %b %d")
        bar_rows += (
            f'<tr>'
            f'<td class="review-bar-label">{label}</td>'
            f'<td class="review-bar-cell">'
            f'<div class="review-bar-fill" style="width:{width_pct}%"></div>'
            f'<span class="review-bar-count">{count}</span>'
            f'</td></tr>'
        )
    trend_section = (
        f'<h3 class="agenda-heading">Last 7 Days</h3>'
        f'<table class="review-bars"><tbody>{bar_rows}</tbody></table>'
    )

    sections = week_section + overdue_section + oldest_section + trend_section

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Review</title>
  <link rel="stylesheet" href="/style.css">
  {FAVICON_LINK}
</head>
<body>
  <header>
    <a href="/" class="back">← {notepad_icon(18)} NookPad</a>
  </header>
  <main style="max-width:800px;margin:0 auto;">
    <div class="card">
      <h2>Review</h2>
      {sections}
    </div>
  </main>
</body>
</html>"""


def categories_page():
    cats = load_categories()
    _, active_tasks, _ = _parse_active(read("tasks.md"))
    counts = {}
    for t in active_tasks:
        code = t.get("Category", "").strip()
        if code:
            counts[code] = counts.get(code, 0) + 1

    def make_row(c):
        code = html_escape(c["code"])
        desc = html_escape(c["description"])
        sort = html_escape(str(c["sort_order"]))
        count = counts.get(c["code"], 0)
        code_js = c["code"].replace("'", "\\'")
        desc_js = js_escape(c["description"])
        return f"""<tr>
            <td>{code}</td>
            <td>{desc}</td>
            <td>{sort}</td>
            <td>{count}</td>
            <td class="action-cell">
                <span class="task-hover-actions">
                    <button type="button" class="edit-btn" title="Edit category" onclick="openEditCategory('{code_js}','{desc_js}','{sort}')">✎</button>
                    <form method="POST" action="/delete-category" style="display:inline"><input type="hidden" name="code" value="{code}"><button type="submit" class="del-btn" title="Delete category" onclick="return confirm('Delete category {code}?')">✕</button></form>
                </span>
            </td>
        </tr>"""

    rows_html = "".join(make_row(c) for c in cats)
    total = len(cats)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Categories</title>
  <link rel="stylesheet" href="/style.css">
  {FAVICON_LINK}
</head>
<body>
  <header>
    <a href="/" class="back">← {notepad_icon(18)} NookPad</a>
  </header>
  <main style="max-width:700px;margin:0 auto;">
    <div class="card">
      <h2>Categories <span class="count">{total}</span>
        <button class="add-btn" onclick="document.getElementById('cat-modal').classList.add('open')">+ Add</button>
      </h2>
      <table>
        <thead><tr><th>Code</th><th>Description</th><th>Sort Order</th><th>Tasks</th><th></th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
  </main>

  <div id="cat-modal" class="modal-overlay" onclick="if(event.target===this)this.classList.remove('open')">
    <div class="modal">
      <h3>Add Category</h3>
      <form method="POST" action="/add-category">
        <label>Code
          <input type="text" name="code" required placeholder="e.g. WORK">
        </label>
        <label>Description
          <input type="text" name="description" required placeholder="e.g. Work Projects">
        </label>
        <label>Sort Order
          <input type="number" name="sort_order" required value="{(cats[-1]['sort_order'] + 1) if cats else 1}">
        </label>
        <div class="modal-actions">
          <button type="button" class="cancel-btn" onclick="document.getElementById('cat-modal').classList.remove('open')">Cancel</button>
          <button type="submit" class="submit-btn">Add Category</button>
        </div>
      </form>
    </div>
  </div>

  <div id="cat-edit-modal" class="modal-overlay" onclick="if(event.target===this)this.classList.remove('open')">
    <div class="modal">
      <h3>Edit Category</h3>
      <form method="POST" action="/edit-category">
        <input type="hidden" name="original_code" id="edit-cat-original-code">
        <label>Code
          <input type="text" name="code" id="edit-cat-code" required>
        </label>
        <label>Description
          <input type="text" name="description" id="edit-cat-description" required>
        </label>
        <label>Sort Order
          <input type="number" name="sort_order" id="edit-cat-sort" required>
        </label>
        <div class="modal-actions">
          <button type="button" class="cancel-btn" onclick="document.getElementById('cat-edit-modal').classList.remove('open')">Cancel</button>
          <button type="submit" class="submit-btn">Save</button>
        </div>
      </form>
    </div>
  </div>

  <script>
  function openEditCategory(code, desc, sort) {{
    document.getElementById('edit-cat-original-code').value = code;
    document.getElementById('edit-cat-code').value = code;
    document.getElementById('edit-cat-description').value = desc;
    document.getElementById('edit-cat-sort').value = sort;
    document.getElementById('cat-edit-modal').classList.add('open');
  }}
  </script>
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

        if path == "/favicon.svg":
            body = FAVICON_SVG.encode()
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.send_header("Cache-Control", "max-age=3600")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/":
            body = dashboard_page().encode()
        elif path == "/completed":
            body = completed_tasks_page().encode()
        elif path == "/review":
            body = review_page().encode()
        elif path == "/agenda":
            body = agenda_page().encode()
        elif path == "/categories":
            body = categories_page().encode()
        elif path == "/notes":
            body = notes_page().encode()
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
            category = get("category")
            recur = get("recur", "")
            if due_raw and task:
                add_task(due_raw + " 00:00", task, notes, priority, parent, category, recur)

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
            category = get("category", "")
            recur = get("recur", "")
            if num.isdigit() and due_raw and task:
                edit_task(int(num), due_raw + " 00:00", task, notes, priority, parent, category, recur)

        elif path == "/snooze-task":
            task_id = get("id")
            delta = get("delta")
            if task_id and delta in SNOOZE_DELTAS:
                snooze_task(task_id, delta)

        elif path == "/complete-shopping":
            store = get("store")
            item = get("item")
            if store and item:
                remove_shopping_item(store, item)

        elif path == "/add-idea":
            description = get("description")
            parent = get("parent")
            notes = get("notes")
            category = get("category", "")
            if description:
                add_idea(description, parent, notes, category)

        elif path == "/edit-idea":
            idea_id = get("id")
            description = get("description")
            notes = get("notes")
            parent = get("parent")
            category = get("category", "")
            if idea_id and description:
                edit_idea(idea_id, description, notes, parent, category)

        elif path == "/delete-idea":
            idea_id = get("id")
            if idea_id:
                delete_idea(idea_id)

        elif path == "/idea-to-task":
            idea_id = get("idea_id")
            priority = get("priority", "None")
            due_raw = get("due_date")
            category = get("category", "")
            if idea_id and due_raw:
                ideas = _parse_ideas(read("ideas.md"))
                idea = next((i for i in ideas if i["id"] == idea_id), None)
                if idea:
                    add_task(due_raw + " 00:00", idea["desc"], idea.get("notes", ""), priority, "", category, "")

        elif path == "/add-note":
            body_text = get("body")
            if body_text:
                add_note(body_text)
            self.send_response(303)
            self.send_header("Location", "/notes")
            self.end_headers()
            return

        elif path == "/edit-note":
            note_id = get("id")
            body_text = get("body")
            if note_id and body_text:
                edit_note(note_id, body_text)
            self.send_response(303)
            self.send_header("Location", "/notes")
            self.end_headers()
            return

        elif path == "/delete-note":
            note_id = get("id")
            if note_id:
                delete_note(note_id)
            self.send_response(303)
            self.send_header("Location", "/notes")
            self.end_headers()
            return

        elif path == "/add-category":
            code = get("code")
            description = get("description")
            sort_order = get("sort_order", "0")
            if code and description:
                try:
                    add_category(code, description, int(sort_order))
                except ValueError:
                    add_category(code, description, 0)
            self.send_response(303)
            self.send_header("Location", "/categories")
            self.end_headers()
            return

        elif path == "/edit-category":
            original_code = get("original_code")
            code = get("code")
            description = get("description")
            sort_order = get("sort_order", "0")
            if original_code and code and description:
                try:
                    edit_category(original_code, code, description, int(sort_order))
                except ValueError:
                    edit_category(original_code, code, description, 0)
            self.send_response(303)
            self.send_header("Location", "/categories")
            self.end_headers()
            return

        elif path == "/delete-category":
            code = get("code")
            if code:
                delete_category(code)
            self.send_response(303)
            self.send_header("Location", "/categories")
            self.end_headers()
            return

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
