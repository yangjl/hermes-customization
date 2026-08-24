"""Capture an explicit Telegram, Slack, or Email message as an inbox card.

A random idea is worth writing down in the five seconds you have it, which
means the capture path has to be shorter than a conversation. This hook writes
the message straight to a Kanban board and gets out of the way: no model call,
no interpretation, no reply.

Capture-only by design. The card holds what you said, verbatim, and deciding
what it means is a separate act you perform later against the board. A hook
that tried to be clever here would turn a five-second note into a negotiation.

Cards land in ``triage`` so they remain reviewable Inbox candidates. The hook
does not assign a category or promote the message into active work.

Scope is deliberately narrow:

* An allowlist, because a bot token is a public endpoint.
* A prefix, so an ordinary conversation with the bot is not swallowed.

Configuration, all optional except the allowlist:

    <PLATFORM>_CAPTURE_USERS comma-separated user ids or senders allowed to
                             capture (TELEGRAM, SLACK, or EMAIL).
    INBOX_CAPTURE_BOARD      Kanban board slug. Default: inbox
    <PLATFORM>_CAPTURE_PREFIX comma-separated triggers. Default: idea:,todo:,note:
                             Set to ``*`` to capture every message.

The board is created on first use.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re

logger = logging.getLogger("hooks.telegram-idea-capture")

BOARD = os.getenv("INBOX_CAPTURE_BOARD", os.getenv("TELEGRAM_CAPTURE_BOARD", "inbox"))
DEFAULT_PREFIXES = "idea:,todo:,note:"
TITLE_MAX = 70


def _strip_prefix(message: str, prefixes: list[str]) -> str | None:
    """The message with its trigger removed, or None when nothing triggers.

    Returning None rather than the original message is what keeps an ordinary
    chat with the bot from silently becoming a card.
    """
    if prefixes == ["*"]:
        return message.strip() or None
    lowered = message.lstrip().lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return message.lstrip()[len(prefix):].strip() or None
    return None


def _split(text: str) -> tuple[str, str]:
    """A short title plus the rest as the body.

    A captured thought is often one long line, so the split is on the first
    sentence or clause rather than on a newline that may never come. The full
    text always survives in the body — the title is only a handle.
    """
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= TITLE_MAX:
        return collapsed, ""
    head = re.split(r"(?<=[.!?])\s|[;\n]", collapsed, maxsplit=1)[0].strip()
    if not head or len(head) > TITLE_MAX:
        cut = collapsed[:TITLE_MAX].rsplit(" ", 1)[0] or collapsed[:TITLE_MAX]
        head = cut.rstrip(",;:") + "…"
    return head, text.strip()


def _capture(text: str, context: dict) -> str | None:
    """Write the card. Returns the task id, or None when the write failed."""
    from hermes_cli import kanban_db

    if not kanban_db.board_exists(BOARD):
        kanban_db.create_board(
            BOARD, name="Inbox",
            description="Ideas captured from chat, before they are real work.")

    kanban_db.init_db(board=BOARD)
    conn = kanban_db.connect(board=BOARD)
    try:
        title, body = _split(text)
        detail = [body] if body else []
        platform = str(context.get("platform", "telegram")).lower()
        detail += ["", f"Captured from {platform.title()}."]
        chat = context.get("chat_id")
        if chat:
            detail.append(f"Chat: {chat}")
        metadata = json.dumps({
            "source": platform,
            "reason": f"Explicit {platform.title()} capture prefix",
            "details": "\n".join(detail).strip(),
        })
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]
        return kanban_db.create_task(
            conn, title=title, body=metadata, triage=True,
            idempotency_key=f"{platform}:{chat or 'direct'}:{digest}",
            created_by=f"{platform}-capture", board=BOARD)
    finally:
        conn.close()


async def handle(event_type: str, context: dict) -> None:
    platform = str(context.get("platform", "")).lower()
    if platform not in {"telegram", "slack", "email"}:
        return

    allowed_raw = os.getenv(f"{platform.upper()}_CAPTURE_USERS", "")
    allowed = {user.strip() for user in allowed_raw.split(",") if user.strip()}
    if not allowed:
        return  # capture is off until someone is named
    if str(context.get("user_id", "")) not in allowed:
        return

    prefix_raw = os.getenv(f"{platform.upper()}_CAPTURE_PREFIX", DEFAULT_PREFIXES).strip()
    prefixes = ["*"] if prefix_raw == "*" else [item.strip().lower() for item in prefix_raw.split(",") if item.strip()]
    text = _strip_prefix(context.get("message", "") or "", prefixes)
    if not text:
        return

    try:
        task_id = _capture(text, context)
    except Exception as exc:  # a failed capture must never break the turn
        logger.error("telegram capture failed: %s", exc)
        return

    if task_id:
        logger.info("captured %s to board %s", task_id, BOARD)


if __name__ == "__main__":
    # Enough of a check to catch the parsing mistakes that would quietly
    # capture the wrong thing, or nothing at all.
    assert _strip_prefix("idea: try X", ["idea:"]) == "try X"
    assert _strip_prefix("IDEA:  spaced  ", ["idea:"]) == "spaced"
    assert _strip_prefix("what is X?", ["idea:"]) is None
    assert _strip_prefix("no trigger", ["*"]) == "no trigger"
    assert _strip_prefix("idea:", ["idea:"]) is None

    short, rest = _split("try X")
    assert (short, rest) == ("try X", "")

    long_text = ("Rewrite the phenotype pipeline so it can run per-environment. "
                 "That would let us compare Kansas and Nebraska directly.")
    title, body = _split(long_text)
    assert title == "Rewrite the phenotype pipeline so it can run per-environment."
    assert body == long_text

    runon = "a" * 200
    title, body = _split(runon)
    assert len(title) <= TITLE_MAX + 1 and title.endswith("…")
    assert body == runon

    print("ok")
