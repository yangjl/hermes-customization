"""Backend for the Hermes Project Kanban desktop page."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hermes_cli import kanban_db as kb

router = APIRouter()

CATEGORIES = ("main-research", "student-projects", "systems-admin")
LOCAL_BOARD = "todos"
INBOX_BOARD = "inbox"
LANE_IDS = {"next", "doing", "waiting", "review"}
NATIVE_STATUS_LANES = {
    "triage": "next",
    "todo": "next",
    "scheduled": "next",
    "ready": "next",
    "running": "doing",
    "blocked": "waiting",
    "review": "review",
}
ACTIVE_CANDIDATE_STATUSES = {"blocked", "triage", "todo", "ready"}


class TaskCreate(BaseModel):
    title: str
    body: str = ""
    category: Literal["main-research", "student-projects", "systems-admin"] = "systems-admin"
    lane: Literal["next", "doing", "waiting", "review"] = "next"


class TaskMove(BaseModel):
    lane: Literal["next", "doing", "waiting", "review"]


class InboxCapture(BaseModel):
    title: str
    source: Literal["email", "slack", "telegram", "github", "manual"]
    reason: str = ""
    details: str = ""
    idempotency_key: str | None = None


class InboxAccept(BaseModel):
    title: str
    category: Literal["main-research", "student-projects", "systems-admin"]


def _frontmatter(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip().strip("'\"")
    return values


def _project_counts() -> dict[str, Any]:
    vault = Path(os.environ.get("TODO_VAULT", "~/Documents/WikiHub/todo-list")).expanduser()
    counts = {category: 0 for category in CATEGORIES}
    active: dict[str, str] = {}
    projects = vault / "Projects"
    if projects.is_dir():
        notes = sorted(projects.rglob("*.md"), key=lambda path: (len(path.relative_to(projects).parts), str(path)))
        for note in notes:
            metadata = _frontmatter(note)
            if metadata.get("knowledge_status", "").lower() != "active":
                continue
            project = metadata.get("project") or metadata.get("hermes_project") or note.stem
            category = metadata.get("project_category", "")
            if project not in active or (active[project] not in counts and category in counts):
                active[project] = category
    for category in active.values():
        if category in counts:
            counts[category] += 1
    return {
        "total_active": len(active),
        "categories": counts,
        "needs_category": sum(category not in counts for category in active.values()),
    }


def _suggestion(title: str, body: str) -> tuple[str, str]:
    text = f"{title} {body}".lower()
    groups = (
        ("student-projects", ("student", "thesis", "dissertation", "draft", "chapter", "maya")),
        ("systems-admin", ("admin", "backup", "server", "website", "invoice", "install", "system")),
    )
    for category, words in groups:
        for word in words:
            if word in text:
                return category, f"Matched the explicit word “{word}”; review before accepting."
    return "main-research", "No student or systems keyword matched; review before accepting."


def _metadata(body: str | None) -> dict[str, Any]:
    try:
        value = json.loads(body or "")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _human_task_body(details: str, lane: str, *, accepted_from: str | None = None) -> str:
    project_kanban: dict[str, Any] = {"human_managed": True, "lane": lane}
    if accepted_from:
        project_kanban["accepted_from"] = accepted_from
    return json.dumps({"details": details, "project_kanban": project_kanban})


def _candidate_body(payload: InboxCapture) -> str:
    return json.dumps(
        {
            "source": payload.source,
            "reason": payload.reason.strip(),
            "details": payload.details.strip(),
            "review_candidate": True,
            "candidate_stage": "captured",
        }
    )


def _links(details: str) -> dict[str, str]:
    """Obsidian note and GitHub URL as written into a card's details block.

    `scripts/refresh-todo-vault.py` writes `GitHub: <url>` and `Note: <path>`
    lines when it raises a card. Parsing them here keeps the desktop plugin
    free of body-format knowledge.
    """
    links = {"obsidian": "", "github": ""}
    for line in details.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        label = key.strip().lower()
        if label == "note" and not links["obsidian"]:
            links["obsidian"] = value.strip()
        elif label == "github" and not links["github"]:
            links["github"] = value.strip()
    return links


def _task_view(task: kb.Task) -> dict[str, Any]:
    source = "manual"
    reason = ""
    body = task.body or ""
    metadata = _metadata(task.body)
    if metadata.get("source"):
        source = str(metadata["source"])
        reason = str(metadata.get("reason", ""))
        body = str(metadata.get("details", ""))
    workflow = metadata.get("project_kanban")
    if isinstance(workflow, dict):
        body = str(metadata.get("details", ""))
        human_managed = workflow.get("human_managed") is True
        workflow_lane = str(workflow.get("lane", ""))
    else:
        human_managed = False
        workflow_lane = ""
    if workflow_lane not in LANE_IDS:
        workflow_lane = ""
    suggested_category, suggestion_reason = _suggestion(task.title, body)
    return {
        "id": task.id,
        "title": task.title,
        "body": body,
        "status": task.status,
        "priority": task.priority,
        "category": task.tenant if task.tenant in CATEGORIES else "systems-admin",
        "assignee": task.assignee,
        "created_at": task.created_at,
        "source": source,
        "reason": reason,
        "suggested_title": task.title,
        "suggested_category": suggested_category,
        "suggestion_reason": suggestion_reason,
        "human_managed": human_managed,
        "workflow_lane": workflow_lane or None,
        "links": _links(body),
    }


def _board_lanes(board: str) -> dict[str, list[dict[str, Any]]]:
    if not kb.board_exists(board):
        raise HTTPException(status_code=404, detail=f"Board {board!r} is unavailable")
    conn = kb.connect(board=board)
    try:
        tasks = kb.list_tasks(conn, include_archived=False)
    finally:
        conn.close()
    lanes: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANE_IDS}
    for task in tasks:
        view = _task_view(task)
        lane = view["workflow_lane"] if view["human_managed"] else NATIVE_STATUS_LANES.get(task.status)
        if lane in lanes:
            lanes[lane].append(view)
    return lanes


def _park_for_human(conn: Any, task_id: str, *, reason: str) -> None:
    now = int(time.time())
    with kb.write_txn(conn):
        conn.execute(
            "UPDATE tasks SET status = 'blocked', block_kind = 'needs_input', "
            "claim_lock = NULL, claim_expires = NULL, worker_pid = NULL WHERE id = ?",
            (task_id,),
        )
        conn.execute(
            "INSERT INTO task_events (task_id, kind, payload, created_at) VALUES (?, 'blocked', ?, ?)",
            (task_id, json.dumps({"reason": reason, "kind": "needs_input", "source": "project-kanban"}), now),
        )


def _move_human_lane(conn: Any, task_id: str, lane: str) -> kb.Task:
    now = int(time.time())
    with kb.write_txn(conn):
        current = conn.execute(
            "SELECT body, status, claim_lock, worker_pid FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Task not found")
        metadata = _metadata(current["body"])
        workflow = metadata.get("project_kanban")
        if (
            not isinstance(workflow, dict)
            or workflow.get("human_managed") is not True
            or current["status"] != "blocked"
            or current["claim_lock"]
            or current["worker_pid"]
        ):
            raise HTTPException(status_code=409, detail="Native worker lifecycle tasks are read-only")
        workflow["lane"] = lane
        metadata["project_kanban"] = workflow
        updated = conn.execute(
            "UPDATE tasks SET body = ? WHERE id = ? AND status = 'blocked' "
            "AND claim_lock IS NULL AND worker_pid IS NULL",
            (json.dumps(metadata), task_id),
        )
        if updated.rowcount != 1:
            raise HTTPException(status_code=409, detail="Task changed while it was being moved")
        conn.execute(
            "INSERT INTO task_events (task_id, kind, payload, created_at) VALUES (?, 'status', ?, ?)",
            (task_id, json.dumps({"workflow_lane": lane, "source": "project-kanban"}), now),
        )
    task = kb.get_task(conn, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _read_inbox_tasks() -> list[kb.Task]:
    conn = kb.connect(board=INBOX_BOARD)
    try:
        return kb.list_tasks(conn, include_archived=False)
    finally:
        conn.close()


def _inbox_unavailable(detail: str) -> dict[str, Any]:
    return {
        "available": False,
        "stages": {},
        "reason": (
            f"Inbox is unavailable on this gateway-local board store ({detail}). "
            "Project Kanban does not sync boards from another machine."
        ),
    }


def _inbox_snapshot() -> dict[str, Any]:
    try:
        if not kb.board_exists(INBOX_BOARD):
            return _inbox_unavailable("the Inbox board does not exist here")
        tasks = _read_inbox_tasks()
    except Exception as exc:
        return _inbox_unavailable(type(exc).__name__)
    stages = {
        "captured": [
            _task_view(task)
            for task in tasks
            if task.status == "triage"
            or (
                task.status == "blocked"
                and _metadata(task.body).get("review_candidate") is True
            )
        ],
        "suggested": [_task_view(task) for task in tasks if task.status in {"todo", "ready"}],
        "accepted": [_task_view(task) for task in tasks if task.status == "done"],
    }
    return {"available": True, "stages": stages}


def _require_local_board(board: str) -> str:
    if board != LOCAL_BOARD:
        raise HTTPException(status_code=403, detail="Project Kanban is authorized only for the local todos board")
    if not kb.board_exists(LOCAL_BOARD):
        raise HTTPException(status_code=404, detail="The local todos board is unavailable")
    return LOCAL_BOARD


@router.get("/snapshot")
def snapshot(board: str = LOCAL_BOARD) -> dict[str, Any]:
    board = _require_local_board(board)
    metadata = kb.read_board_metadata(board)
    return {
        "machine": {"board": metadata["slug"], "name": metadata["name"]},
        "projects": _project_counts(),
        "lanes": _board_lanes(board),
        "inbox": _inbox_snapshot(),
    }


@router.post("/tasks", status_code=201)
def create_task(payload: TaskCreate, board: str = LOCAL_BOARD) -> dict[str, Any]:
    board = _require_local_board(board)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title is required")
    conn = kb.connect(board=board)
    try:
        task_id = kb.create_task(
            conn,
            title=title,
            body=_human_task_body(payload.body.strip(), payload.lane),
            tenant=payload.category,
            created_by="project-kanban",
            initial_status="blocked",
            board=board,
        )
        _park_for_human(conn, task_id, reason="Human-managed Project Kanban card")
        task = kb.get_task(conn, task_id)
        if task is None:
            raise HTTPException(status_code=500, detail="Task creation failed")
        return _task_view(task)
    finally:
        conn.close()


@router.patch("/tasks/{task_id}")
def move_task(task_id: str, payload: TaskMove, board: str = LOCAL_BOARD) -> dict[str, Any]:
    board = _require_local_board(board)
    conn = kb.connect(board=board)
    try:
        return _task_view(_move_human_lane(conn, task_id, payload.lane))
    finally:
        conn.close()


@router.post("/inbox/capture", status_code=201)
def capture_inbox(payload: InboxCapture) -> dict[str, Any]:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title is required")
    if not kb.board_exists(INBOX_BOARD):
        kb.create_board(INBOX_BOARD, name="Inbox")
    conn = kb.connect(board=INBOX_BOARD)
    try:
        task_id = kb.create_task(
            conn,
            title=title,
            body=_candidate_body(payload),
            tenant="inbox",
            created_by="project-kanban",
            initial_status="blocked",
            idempotency_key=(payload.idempotency_key or "").strip() or None,
            board=INBOX_BOARD,
        )
        task = kb.get_task(conn, task_id)
        if task is None:
            raise HTTPException(status_code=500, detail="Inbox capture failed")
        if task.status == "blocked" and task.block_kind != "needs_input":
            _park_for_human(conn, task_id, reason="Inbox candidate awaiting human review")
            task = kb.get_task(conn, task_id)
        if task is None:
            raise HTTPException(status_code=500, detail="Inbox capture failed")
        return _task_view(task)
    finally:
        conn.close()


@router.post("/inbox/{task_id}/accept")
def accept_inbox(task_id: str, payload: InboxAccept, board: str = LOCAL_BOARD) -> dict[str, Any]:
    board = _require_local_board(board)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title is required")
    if not kb.board_exists(INBOX_BOARD):
        raise HTTPException(status_code=404, detail="Inbox is unavailable")
    inbox_conn = kb.connect(board=INBOX_BOARD)
    target_conn = kb.connect(board=board)
    try:
        with kb.write_txn(inbox_conn):
            candidate = kb.get_task(inbox_conn, task_id)
            if candidate is None or candidate.status not in ACTIVE_CANDIDATE_STATUSES:
                raise HTTPException(status_code=409, detail="Inbox candidate is no longer active")
            action_id = kb.create_task(
                target_conn,
                title=title,
                body=_human_task_body(
                    f"Accepted from Inbox candidate {task_id}.",
                    "next",
                    accepted_from=task_id,
                ),
                tenant=payload.category,
                created_by="project-kanban",
                initial_status="blocked",
                idempotency_key=f"project-kanban:accept:{task_id}:{board}",
                board=board,
            )
            _park_for_human(target_conn, action_id, reason="Accepted Inbox action awaiting human work")
            action = kb.get_task(target_conn, action_id)
            if action is None:
                raise HTTPException(status_code=500, detail="Action creation failed")
            now = int(time.time())
            result = f"accepted:{board}:{action_id}"
            updated = inbox_conn.execute(
                "UPDATE tasks SET status = 'done', completed_at = ?, result = ?, "
                "idempotency_key = NULL WHERE id = ? AND status = ?",
                (now, result, task_id, candidate.status),
            )
            if updated.rowcount != 1:
                raise HTTPException(status_code=409, detail="Inbox candidate changed while it was being accepted")
            inbox_conn.execute(
                "INSERT INTO task_events (task_id, kind, payload, created_at) VALUES (?, 'completed', ?, ?)",
                (task_id, json.dumps({"result": result, "source": "project-kanban"}), now),
            )
        accepted = kb.get_task(inbox_conn, task_id)
        if accepted is None:
            raise HTTPException(status_code=500, detail="Inbox update failed")
        return {"task": _task_view(action), "candidate": _task_view(accepted)}
    finally:
        target_conn.close()
        inbox_conn.close()


@router.delete("/inbox/{task_id}")
def dismiss_inbox(task_id: str) -> dict[str, bool]:
    if not kb.board_exists(INBOX_BOARD):
        raise HTTPException(status_code=404, detail="Inbox is unavailable")
    conn = kb.connect(board=INBOX_BOARD)
    try:
        now = int(time.time())
        with kb.write_txn(conn):
            placeholders = ",".join("?" for _ in ACTIVE_CANDIDATE_STATUSES)
            updated = conn.execute(
                f"UPDATE tasks SET status = 'archived', claim_lock = NULL, "
                f"claim_expires = NULL, worker_pid = NULL WHERE id = ? "
                f"AND status IN ({placeholders})",
                (task_id, *sorted(ACTIVE_CANDIDATE_STATUSES)),
            )
            if updated.rowcount != 1:
                raise HTTPException(status_code=409, detail="Inbox candidate is no longer active")
            conn.execute(
                "INSERT INTO task_events (task_id, kind, payload, created_at) VALUES (?, 'archived', ?, ?)",
                (task_id, json.dumps({"source": "project-kanban"}), now),
            )
        return {"ok": True}
    finally:
        conn.close()
