"""Backend for the Hermes Project Kanban desktop page."""

from __future__ import annotations

import datetime
import json
import os
import re
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


class TaskCreate(BaseModel):
    title: str
    body: str = ""
    project_id: str
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
    project_id: str


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


def _heading_re(heading: str) -> re.Pattern[str]:
    return re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.IGNORECASE)


# Any level-2 heading. The section terminator must recognise the same shapes as
# _heading_re, or a heading it accepts (e.g. tab-separated) fails to end the
# previous section and gets swallowed into it.
_ANY_HEADING_RE = re.compile(r"^##\s+")


def _section(text: str, heading: str) -> str:
    # Must use the same matcher as _has_heading, or a note can pass the
    # presence gate and still yield empty text (e.g. "##  Goal").
    marker = _heading_re(heading)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not marker.match(line):
            continue
        body: list[str] = []
        for value in lines[index + 1:]:
            if _ANY_HEADING_RE.match(value):
                break
            body.append(value)
        return "\n".join(body).strip()
    return ""


def _has_heading(text: str, heading: str) -> bool:
    return any(_heading_re(heading).match(line) for line in text.splitlines())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _timestamp(value: object) -> datetime.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _is_stale(observed_at: str) -> bool:
    observed = _timestamp(observed_at)
    return observed is None or _now() - observed > datetime.timedelta(days=7)


def _evidence_counts(raw: dict[str, Any]) -> tuple[int, int, int] | None:
    try:
        counts = (
            int(raw.get("dirty_count") or 0),
            int(raw.get("ahead") or 0),
            int(raw.get("behind") or 0),
        )
    except (TypeError, ValueError):
        return None
    return counts if all(value >= 0 for value in counts) else None


def _observations(vault: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    latest: dict[str, dict[str, Any]] = {}
    unmatched: list[dict[str, Any]] = []
    warnings: list[str] = []
    folder = vault / "Observations" / "devices"
    if not folder.is_dir():
        return latest, unmatched, warnings
    for path in sorted(folder.glob("*.json")):
        relative = path.relative_to(vault)
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            warnings.append(f"{relative}: malformed observation snapshot")
            continue
        if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1:
            warnings.append(f"{relative}: unsupported observation snapshot")
            continue
        device = str(snapshot.get("device", ""))
        observed_at = str(snapshot.get("observed_at", ""))
        observed = _timestamp(observed_at)
        if not device or observed is None:
            warnings.append(f"{relative}: missing device or observed_at")
            continue
        raw_projects = snapshot.get("projects", [])
        if not isinstance(raw_projects, list):
            warnings.append(f"{relative}: projects must be a list")
            raw_projects = []
        for raw in raw_projects:
            if not isinstance(raw, dict):
                continue
            project_id = str(raw.get("project_id", ""))
            if not project_id:
                continue
            counts = _evidence_counts(raw)
            if counts is None:
                warnings.append(f"{relative}: invalid evidence counts")
                continue
            evidence = {
                "device": device,
                "observed_at": observed_at,
                "activity_at": str(raw.get("activity_at", "")),
                "head": str(raw.get("head", "")),
                "dirty_count": counts[0],
                "ahead": counts[1],
                "behind": counts[2],
                "github_repo": str(raw.get("github_repo", "")),
                "github_pushed_at": str(raw.get("github_pushed_at", "")),
                "stale": _is_stale(observed_at),
            }
            previous = latest.get(project_id)
            if previous is None or observed > (_timestamp(previous["observed_at"]) or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)):
                latest[project_id] = evidence
        raw_unmatched = snapshot.get("unmatched", [])
        if not isinstance(raw_unmatched, list):
            warnings.append(f"{relative}: unmatched must be a list")
            raw_unmatched = []
        for raw in raw_unmatched:
            if not isinstance(raw, dict) or not raw.get("source"):
                continue
            counts = _evidence_counts(raw)
            if counts is None:
                warnings.append(f"{relative}: invalid evidence counts")
                continue
            unmatched.append({
                "source": str(raw["source"]),
                "kind": str(raw.get("kind", "unknown")),
                "device": device,
                "observed_at": observed_at,
                "activity_at": str(raw.get("activity_at", "")),
                "dirty_count": counts[0],
                "ahead": counts[1],
                "behind": counts[2],
                "stale": _is_stale(observed_at),
            })
    unmatched.sort(key=lambda row: (row["source"], row["device"], row["observed_at"]))
    return latest, unmatched, warnings


def _project_records() -> dict[str, Any]:
    vault = Path(os.environ.get("TODO_VAULT", "~/Documents/WikiHub/todo-list")).expanduser()
    counts = {category: 0 for category in CATEGORIES}
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    projects = vault / "Projects"
    if projects.is_dir():
        notes = sorted(projects.rglob("*.md"), key=lambda path: (len(path.relative_to(projects).parts), str(path)))
        # Pass 1: resolve identity before any other validation. Every active note
        # with a syntactically valid project_id is a claimant, so an ID claimed
        # by a valid note AND a malformed one is still ambiguous and must be
        # excluded entirely rather than silently resolving to the valid note.
        claims: dict[str, list[Path]] = {}
        for note in notes:
            metadata = _frontmatter(note)
            if metadata.get("knowledge_status", "").lower() != "active":
                continue
            project_id = metadata.get("project_id", "")
            if not project_id:
                continue
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", project_id):
                warnings.append(f"{note.relative_to(vault)}: invalid project_id {project_id!r}")
                continue
            claims.setdefault(project_id, []).append(note)
        ambiguous = {pid for pid, notes_ in claims.items() if len(notes_) > 1}
        for project_id in sorted(ambiguous):
            paths = ", ".join(str(note.relative_to(vault)) for note in claims[project_id])
            warnings.append(f"duplicate project_id {project_id!r} claimed by {paths}; all claimants excluded")

        # Pass 2: validate only unambiguous claims.
        for project_id in sorted(set(claims) - ambiguous):
            note = claims[project_id][0]
            metadata = _frontmatter(note)
            relative = note.relative_to(vault)
            category = metadata.get("project_category", "")
            if category not in counts:
                warnings.append(f"{relative}: invalid or missing project_category")
                continue
            try:
                text = note.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                warnings.append(f"{relative}: unreadable project note")
                continue
            sections = {
                "goal": _section(text, "Goal"),
                "next_action": _section(text, "Next action"),
                "blocker": _section(text, "Blocker"),
            }
            missing = [
                heading for heading in ("Goal", "Next action", "Blocker")
                if not _has_heading(text, heading)
            ]
            for heading in missing:
                warnings.append(f"{relative}: missing {heading} heading")
            if missing:
                continue
            title = next(
                (line[2:].strip() for line in text.splitlines() if line.startswith("# ")),
                note.stem,
            )
            counts[category] += 1
            items.append({
                "project_id": project_id,
                "title": title,
                "status": "active",
                "category": category,
                **sections,
                "github_repo": metadata.get("github_repo", ""),
                "updated": metadata.get("updated", ""),
                "note": str(relative),
                "note_path": str(note),
            })
    items.sort(key=lambda item: item["project_id"])
    observations, unmatched, observation_warnings = _observations(vault)
    warnings.extend(observation_warnings)
    for item in items:
        observation = observations.get(item["project_id"])
        item["github"] = {
            "repo": item["github_repo"],
            "pushed_at": observation["github_pushed_at"] if observation else "",
        }
        item["observation"] = observation
    return {
        "total_active": len(items),
        "categories": counts,
        "needs_category": 0,
        "items": items,
        "warnings": warnings,
        "unmatched": unmatched,
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


def _human_task_body(
    details: str,
    lane: str,
    *,
    accepted_from: str | None = None,
    project_id: str | None = None,
) -> str:
    project_kanban: dict[str, Any] = {"human_managed": True, "lane": lane}
    if accepted_from:
        project_kanban["accepted_from"] = accepted_from
    if project_id:
        project_kanban["project_id"] = project_id
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


def _task_view(task: kb.Task, projects: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
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
        project_id = str(workflow.get("project_id", ""))
    else:
        human_managed = False
        workflow_lane = ""
        project_id = ""
    if workflow_lane not in LANE_IDS:
        workflow_lane = ""
    suggested_category, suggestion_reason = _suggestion(task.title, body)
    return {
        "id": task.id,
        "title": task.title,
        "body": body,
        "status": task.status,
        "priority": task.priority,
        "category": task.tenant if task.tenant in {*CATEGORIES, "unsorted"} else "unsorted",
        "assignee": task.assignee,
        "created_at": task.created_at,
        "source": source,
        "reason": reason,
        "suggested_title": task.title,
        "suggested_category": suggested_category,
        "suggestion_reason": suggestion_reason,
        "human_managed": human_managed,
        "workflow_lane": workflow_lane or None,
        "project_id": project_id or None,
        "project": (projects or {}).get(project_id),
        "links": _links(body),
    }


def _board_lanes(
    board: str,
    projects: dict[str, dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if not kb.board_exists(board):
        raise HTTPException(status_code=404, detail=f"Board {board!r} is unavailable")
    conn = kb.connect(board=board)
    try:
        tasks = kb.list_tasks(conn, include_archived=False)
    finally:
        conn.close()
    lanes: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANE_IDS}
    for task in tasks:
        view = _task_view(task, projects)
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


def _candidate_stage(task: kb.Task) -> str | None:
    """The Inbox review stage a task belongs to, or None if it is not a candidate.

    This is the ONE eligibility predicate shared by listing, accepting, and
    dismissing, so a task that is not visible in the Inbox can never be mutated
    through it. A blocked task must carry the `review_candidate` metadata this
    plugin writes on capture; native worker-lifecycle tasks are not candidates,
    and a claimed task belongs to its worker.
    """
    if task.claim_lock or task.worker_pid:
        return None
    if task.status == "triage":
        return "captured"
    if task.status == "blocked":
        metadata = _metadata(task.body)
        if metadata.get("review_candidate") is True:
            return "captured"
        return None
    if task.status in {"todo", "ready"}:
        return "suggested"
    return None


def _inbox_snapshot() -> dict[str, Any]:
    try:
        if not kb.board_exists(INBOX_BOARD):
            return _inbox_unavailable("the Inbox board does not exist here")
        tasks = _read_inbox_tasks()
    except Exception as exc:
        return _inbox_unavailable(type(exc).__name__)
    stages: dict[str, list[dict[str, Any]]] = {
        "captured": [],
        "suggested": [],
        "accepted": [_task_view(task) for task in tasks if task.status == "done"],
    }
    for task in tasks:
        stage = _candidate_stage(task)
        if stage is not None:
            stages[stage].append(_task_view(task))
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
    projects = _project_records()
    project_lookup = {item["project_id"]: item for item in projects["items"]}
    return {
        "machine": {"board": metadata["slug"], "name": metadata["name"]},
        "projects": projects,
        "lanes": _board_lanes(board, project_lookup),
        "inbox": _inbox_snapshot(),
    }


@router.post("/tasks", status_code=201)
def create_task(payload: TaskCreate, board: str = LOCAL_BOARD) -> dict[str, Any]:
    board = _require_local_board(board)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title is required")
    project_lookup = {
        item["project_id"]: item for item in _project_records()["items"]
    }
    project_id = payload.project_id.strip()
    project = project_lookup.get(project_id)
    if project is None:
        raise HTTPException(status_code=422, detail="Canonical project is unavailable")
    category = project["category"]
    conn = kb.connect(board=board)
    try:
        task_id = kb.create_task(
            conn,
            title=title,
            body=_human_task_body(payload.body.strip(), payload.lane, project_id=project_id),
            tenant=category,
            created_by="project-kanban",
            initial_status="blocked",
            board=board,
        )
        _park_for_human(conn, task_id, reason="Human-managed Project Kanban card")
        task = kb.get_task(conn, task_id)
        if task is None:
            raise HTTPException(status_code=500, detail="Task creation failed")
        return _task_view(task, project_lookup)
    finally:
        conn.close()


@router.patch("/tasks/{task_id}")
def move_task(task_id: str, payload: TaskMove, board: str = LOCAL_BOARD) -> dict[str, Any]:
    board = _require_local_board(board)
    project_lookup = {
        item["project_id"]: item for item in _project_records()["items"]
    }
    conn = kb.connect(board=board)
    try:
        return _task_view(_move_human_lane(conn, task_id, payload.lane), project_lookup)
    finally:
        conn.close()


@router.post("/inbox/capture", status_code=201)
def capture_inbox(payload: InboxCapture) -> dict[str, Any]:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title is required")
    if not kb.board_exists(INBOX_BOARD):
        raise HTTPException(status_code=404, detail="Inbox is unavailable")
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
    project_lookup = {
        item["project_id"]: item for item in _project_records()["items"]
    }
    project_id = payload.project_id.strip()
    project = project_lookup.get(project_id)
    if project is None:
        raise HTTPException(status_code=422, detail="Canonical project is unavailable")
    if not kb.board_exists(INBOX_BOARD):
        raise HTTPException(status_code=404, detail="Inbox is unavailable")
    inbox_conn = kb.connect(board=INBOX_BOARD)
    target_conn = kb.connect(board=board)
    try:
        with kb.write_txn(inbox_conn):
            candidate = kb.get_task(inbox_conn, task_id)
            if candidate is None or _candidate_stage(candidate) is None:
                raise HTTPException(status_code=409, detail="Inbox candidate is no longer active")
            action_id = kb.create_task(
                target_conn,
                title=title,
                body=_human_task_body(
                    f"Accepted from Inbox candidate {task_id}.",
                    "next",
                    accepted_from=task_id,
                    project_id=project_id,
                ),
                tenant=project["category"],
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
                "idempotency_key = NULL WHERE id = ? AND status = ? "
                "AND claim_lock IS NULL AND worker_pid IS NULL",
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
        return {"task": _task_view(action, project_lookup), "candidate": _task_view(accepted)}
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
            candidate = kb.get_task(conn, task_id)
            if candidate is None or _candidate_stage(candidate) is None:
                raise HTTPException(status_code=409, detail="Inbox candidate is no longer active")
            # Archive only; never clear a worker's claim. The lock columns are
            # re-checked here so a worker that claimed the task between the read
            # and this write loses the race instead of the lock.
            updated = conn.execute(
                "UPDATE tasks SET status = 'archived' WHERE id = ? AND status = ? "
                "AND claim_lock IS NULL AND worker_pid IS NULL",
                (task_id, candidate.status),
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
