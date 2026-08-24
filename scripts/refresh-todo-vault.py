#!/usr/bin/env python3
"""Refresh the todo-list Obsidian vault from GitHub and from local folders.

Metadata only: repositories are never cloned and working trees are only read.
GitHub notes are shared between machines; local scans are written under a
folder named for this machine, so two machines never overwrite each other.

Generated notes are replaced on every run. Notes you write yourself are left
alone — keep your own thinking in your own note and link to the inventory note.

A repository you have marked ``knowledge_status: active`` raises a Kanban card
when it is pushed. Nothing else does. Marking a repository active is the opt-in;
repositories you have not reviewed stay silent no matter how busy they are.

Prints a short report of what changed since the previous run. Exits non-zero
only when the vault could not be refreshed at all.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VAULT = Path(os.environ.get("TODO_VAULT", "~/Documents/WikiHub/todo-list")).expanduser()
MACHINE = os.environ.get("TODO_MACHINE", "labtop-old")
ACCOUNTS = ("yangjl", "jyanglab")
SCAN_ROOTS = {
    "Local": Path("~/Documents/projects").expanduser(),
    "Website": Path("~/Documents/website").expanduser(),
}
STATE = Path("~/.hermes/cache/todo-vault-state.json").expanduser()
BOARD = os.environ.get("TODO_INBOX_BOARD", "inbox")
CARDS_ENABLED = os.environ.get("TODO_CARDS", "1") != "0"

TODAY = datetime.date.today()
CUT_90 = (TODAY - datetime.timedelta(days=90)).isoformat()
CUT_1Y = (TODAY - datetime.timedelta(days=365)).isoformat()

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__",
    ".next", ".cache", "target", "vendor", "largedata", "cache", "data", "_site",
}
MARKERS = {
    "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "Makefile",
    "README.md", "setup.py", "requirements.txt", "environment.yml",
    "Project.toml", "DESCRIPTION", "Gemfile", "_config.yml", "config.toml",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text.replace("/", "--").replace(os.sep, "--")).strip("-")


def quote(text: str | None) -> str:
    return (text or "").replace('"', "'")


def git(path: Path | str, args: list[str], timeout: int = 15) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), *args],
            stderr=subprocess.DEVNULL, text=True, timeout=timeout,
        ).strip()
    except Exception:
        return ""


def write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def tokens() -> list[str]:
    env = Path("~/.hermes/.env").expanduser()
    found: list[str] = []
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(("GITHUB_TOKEN_", "GITHUB_TOKEN=")):
                value = line.split("=", 1)[1].strip()
                if value and value not in found:
                    found.append(value)
    return found


# --------------------------------------------------------------------------
# GitHub — metadata only
# --------------------------------------------------------------------------

def api_pages(path: str, token: str) -> list[dict]:
    out: list[dict] = []
    url: str | None = "https://api.github.com" + path
    while url:
        request = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "todo-vault-refresh",
        })
        response = urllib.request.urlopen(request, timeout=30)
        out += json.load(response)
        url = None
        for part in response.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
    return out


def collect_github() -> dict[str, dict]:
    """Every repository on the tracked accounts, keyed by ``owner/name``."""
    paths = [
        "/user/repos?per_page=100&affiliation=owner,collaborator,organization_member&sort=pushed",
        "/orgs/jyanglab/repos?per_page=100&type=all&sort=pushed",
    ]
    seen: dict[str, dict] = {}
    for token in tokens():
        for path in paths:
            try:
                for repo in api_pages(path, token):
                    if repo["owner"]["login"] in ACCOUNTS:
                        seen[repo["full_name"]] = repo
            except Exception as exc:  # one bad token must not lose the rest
                print(f"  github {path}: {exc}", file=sys.stderr)
    return {
        name: {
            "name": r["name"], "owner": r["owner"]["login"], "private": r["private"],
            "fork": r["fork"], "archived": r["archived"], "pushed_at": r["pushed_at"],
            "created_at": r["created_at"], "description": r.get("description"),
            "language": r.get("language"), "size_kb": r.get("size"),
            "default_branch": r.get("default_branch"), "html_url": r["html_url"],
        }
        for name, r in seen.items()
    }


# --------------------------------------------------------------------------
# local folders — read only
# --------------------------------------------------------------------------

def scan_root(root: Path) -> list[dict]:
    """Independent git roots, plus marker-bearing folders outside any repo."""
    if not root.is_dir():
        return []

    git_roots: list[str] = []
    for base, dirs, files in os.walk(root):
        if ".git" in dirs or ".git" in files:
            git_roots.append(base)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    git_roots = sorted(set(g for g in git_roots if Path(g) != root))

    rows: list[dict] = []
    for path in git_roots:
        log = git(path, ["log", "-1", "--format=%ct%x00%h%x00%s", "--all"])
        epoch, sha, subject = (log.split("\x00", 2) + ["", "", ""])[:3] if log else ("", "", "")
        rows.append({
            "name": Path(path).name, "path": path,
            "relative_path": os.path.relpath(path, root), "version_control": "git",
            "branch": git(path, ["branch", "--show-current"]) or "detached",
            "dirty_files": len(git(path, ["status", "--porcelain"]).splitlines()),
            "last_epoch": int(epoch) if epoch.isdigit() else 0,
            "last_commit_sha": sha, "last_commit_subject": subject,
            "remote": git(path, ["remote", "get-url", "origin"]),
        })

    def inside(p: str) -> bool:
        return any(p == g or p.startswith(g + os.sep) for g in git_roots)

    def nested(p: str) -> list[str]:
        return [g for g in git_roots if g.startswith(p + os.sep)]

    def plain(path: str, relative: str) -> dict:
        return {
            "name": Path(path).name, "path": path, "relative_path": relative,
            "version_control": "none", "branch": "", "dirty_files": None,
            "last_epoch": 0, "last_commit_sha": "", "last_commit_subject": "", "remote": "",
        }

    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or str(entry) in git_roots or entry.name.startswith("."):
            continue
        if not nested(str(entry)):
            rows.append(plain(str(entry), entry.name))
            continue
        for base, dirs, files in os.walk(entry):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            if base == str(entry) or inside(base):
                if inside(base):
                    dirs[:] = []
                continue
            relative = os.path.relpath(base, root)
            if relative.count(os.sep) + 1 > 3:
                dirs[:] = []
                continue
            if set(files) & MARKERS and not nested(base):
                rows.append(plain(base, relative))
                dirs[:] = []

    return sorted(rows, key=lambda r: r["relative_path"].lower())


def enrich(rows: list[dict], repos: dict[str, dict]) -> None:
    """Attach GitHub push dates and an unpulled-commit flag to local rows."""
    lookup = {name.lower(): meta for name, meta in repos.items()}
    ssh_env = dict(os.environ, GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=8",
                   GIT_TERMINAL_PROMPT="0")

    def behind(row: dict) -> tuple[str, bool | None]:
        if not row["remote"]:
            return row["path"], None
        try:
            listing = subprocess.check_output(
                ["git", "ls-remote", "--heads", row["remote"]],
                stderr=subprocess.DEVNULL, text=True, timeout=25, env=ssh_env)
        except Exception:
            return row["path"], None
        shas = [line.split("\t")[0] for line in listing.splitlines() if "\t" in line]
        if not shas:
            return row["path"], False
        try:
            known = subprocess.check_output(
                ["git", "-C", row["path"], "cat-file", "--batch-check"],
                input="\n".join(shas), stderr=subprocess.DEVNULL, text=True, timeout=15)
        except Exception:
            return row["path"], None
        return row["path"], any("missing" in line for line in known.splitlines())

    with ThreadPoolExecutor(max_workers=8) as pool:
        unpulled = dict(pool.map(behind, [r for r in rows if r["version_control"] == "git"]))

    for row in rows:
        match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", row["remote"] or "")
        repo = match.group(1) if match else ""
        meta = lookup.get(repo.lower(), {})
        row["github_repo"] = repo
        row["github_pushed_at"] = meta.get("pushed_at", "")
        row["github_private"] = meta.get("private")
        row["owner"] = repo.split("/")[0] if repo else ""
        row["remote_has_unpulled"] = unpulled.get(row["path"])
        dates = [d for d in (local_date(row), row["github_pushed_at"][:10]) if d and d != "—"]
        row["activity_date"] = max(dates) if dates else "—"


def local_date(row: dict) -> str:
    if not row["last_epoch"]:
        return "—"
    return datetime.datetime.fromtimestamp(row["last_epoch"]).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# Kanban — cards for repositories you marked active
# --------------------------------------------------------------------------

def active_repos() -> dict[str, Path]:
    """Repositories marked active in the vault, mapped to the note that says so.

    Marking a note active is the whole opt-in. A repository nobody has reviewed
    never raises a card, however often it is pushed.
    """
    found: dict[str, Path] = {}
    for note in (VAULT / "Projects").rglob("*.md"):
        try:
            text = note.read_text(encoding="utf-8")
        except Exception:
            continue
        status = re.search(r"^knowledge_status:\s*(\S+)\s*$", text, re.M)
        repo = re.search(r'^github_repo:\s*"([^"]+)"\s*$', text, re.M)
        if status and status.group(1) == "active" and repo and repo.group(1):
            found.setdefault(repo.group(1), note)
    return found


def create_card(repo: dict, note: Path) -> str | None:
    """One card for one month of pushes on one repository.

    The idempotency key carries the month, so a repository pushed ten times in
    January still has exactly one January card, and February gets a fresh one.
    Kanban enforces this, not us — a repeated key returns the existing id.
    """
    full = f"{repo['owner']}/{repo['name']}"
    pushed = repo["pushed_at"][:10]
    key = f"push:{full}:{pushed[:7]}"
    details = "\n".join([
        f"{full} was pushed on {pushed}.",
        "",
        f"GitHub: {repo['html_url']}",
        f"Note: {note.relative_to(VAULT)}",
        "",
        "Raised because the project note is marked active. Decide what the push",
        "means for your next action, then complete or archive this card.",
    ])
    body = json.dumps({
        "source": "github",
        "reason": "Repository push detected for an active project",
        "details": details,
    })
    try:
        result = subprocess.run(
            ["hermes", "kanban", "--board", BOARD, "create",
             f"{full} — pushed {pushed}", "--body", body,
             "--triage", "--idempotency-key", key,
             "--created-by", "vault-refresh", "--json"],
            capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)["id"]
    except Exception:
        return None


def link_card(note: Path, card_id: str, title: str) -> None:
    """Record the card id in its note, so the note names its own work."""
    text = note.read_text(encoding="utf-8")
    if card_id in text:
        return
    entry = f"- `{card_id}` — {title}"
    if "## Kanban tasks" in text:
        text = re.sub(r"(## Kanban tasks\n\n)", rf"\1{entry}\n", text, count=1)
    else:
        text = text.rstrip() + (
            f"\n\n## Kanban tasks\n\n{entry}\n\n"
            f"Board: `{BOARD}`. Inspect with "
            f"`hermes kanban --board {BOARD} show {card_id}`.\n")
    note.write_text(text, encoding="utf-8")


def raise_cards(repos: dict[str, dict], previous: dict[str, str]) -> list[str]:
    """Card the active repositories that have been pushed since the last run."""
    if not CARDS_ENABLED:
        return []
    watched = active_repos()
    raised: list[str] = []
    for full, note in sorted(watched.items()):
        repo = repos.get(full)
        if not repo:
            continue
        was = previous.get(full)
        if was is None or repo["pushed_at"] == was:
            continue
        card_id = create_card(repo, note)
        if card_id:
            title = f"pushed {repo['pushed_at'][:10]}"
            link_card(note, card_id, title)
            raised.append(f"{full} → {card_id}")
    return raised


# --------------------------------------------------------------------------
# notes
# --------------------------------------------------------------------------

def clear_generated(folder: Path) -> None:
    if folder.is_dir():
        for note in folder.glob("*.md"):
            note.unlink()


def carry_over(path: Path) -> tuple[str, str, str]:
    """Rescue the human-edited status, category, and Kanban links.

    A refresh rewrites inventory facts, but the review verdict and the Kanban
    card links are decisions — losing them on every run would make the notes
    useless as a place to record anything. Returns the previous
    ``knowledge_status``, ``project_category``, and the whole ``## Kanban tasks`` section.
    """
    if not path.exists():
        return "unreviewed", "", ""
    text = path.read_text(encoding="utf-8")
    status = re.search(r"^knowledge_status:\s*(\S+)\s*$", text, re.M)
    category = re.search(r"^project_category:\s*(\S+)\s*$", text, re.M)
    tasks = re.search(r"\n(## Kanban tasks\n.*?)(?=\n## |\Z)", text, re.S)
    return (status.group(1) if status else "unreviewed",
            category.group(1) if category else "",
            tasks.group(1).rstrip() if tasks else "")


def github_notes(repos: dict[str, dict], local_by_repo: dict[str, tuple[str, str]]) -> int:
    folder = VAULT / "Projects" / "GitHub"
    carried = {note.name: carry_over(note) for note in folder.glob("*.md")} if folder.is_dir() else {}
    clear_generated(folder)
    notable = [r for r in repos.values() if not r["fork"] and r["pushed_at"][:10] >= CUT_1Y]
    for repo in notable:
        full = f"{repo['owner']}/{repo['name']}"
        clone = local_by_repo.get(full.lower())
        note = folder / f"{slug(full)}.md"
        status, category, tasks = carried.get(note.name, ("unreviewed", "", ""))
        lines = [
            "---", f'github_repo: "{full}"', f"owner: {repo['owner']}",
            f"private: {str(repo['private']).lower()}", f"fork: {str(repo['fork']).lower()}",
            f'pushed_at: "{repo["pushed_at"][:10]}"', f'created_at: "{repo["created_at"][:10]}"',
            f'language: "{quote(repo["language"])}"', f"size_kb: {repo['size_kb']}",
            f"knowledge_status: {status}",
        ]
        if category:
            lines.append(f"project_category: {category}")
        lines += [
            "kanban_board: todos",
            f"cloned_locally: {str(bool(clone)).lower()}", "source: github-api",
            f'updated: "{TODAY.isoformat()}"', "---", "", f"# {full}", "", "## Repository", "",
            f"- URL: {repo['html_url']}",
            f"- Visibility: **{'private' if repo['private'] else 'public'}**",
            f"- Last push: {repo['pushed_at'][:10]}", f"- Created: {repo['created_at'][:10]}",
            f"- Language: {repo['language'] or '—'}",
            f"- Size: {round((repo['size_kb'] or 0) / 1024, 1)} MB",
            f"- Default branch: `{repo['default_branch']}`",
        ]
        if repo["description"]:
            lines.append(f"- Description: {repo['description']}")
        if clone:
            kind, relative = clone
            lines.append(f"- Local clone: [[Projects/{MACHINE}/{kind}/{slug(relative)}|{relative}]]")
        else:
            lines.append("- Local clone: none")
        lines += ["", "## Project summary", "",
                  "Not reviewed yet. Metadata only — this repository was not cloned.", "",
                  "## Next action", "",
                  "- [ ] Review and mark active, paused, archived, or reference.", ""]
        if tasks:
            lines += [tasks, ""]
        write(note, "\n".join(lines))
    return len(notable)


def local_notes(kind: str, rows: list[dict], root: Path) -> None:
    folder = VAULT / "Projects" / MACHINE / kind
    carried = {note.name: carry_over(note) for note in folder.glob("*.md")} if folder.is_dir() else {}
    clear_generated(folder)
    for row in rows:
        is_git = row["version_control"] == "git"
        filename = f"{slug(row['relative_path'])}.md"
        status, category, tasks = carried.get(filename, ("unreviewed", "", ""))
        lines = [
            "---", f'project: "{quote(row["name"])}"',
            f'relative_path: "{quote(row["relative_path"])}"',
            f'local_path: "{quote(row["path"])}"', f'source_root: "{root}"',
            f"machine: {MACHINE}", f"version_control: {'git' if is_git else 'none'}",
            f"knowledge_status: {status}",
        ]
        if category:
            lines.append(f"project_category: {category}")
        lines += [
            "kanban_board: todos",
            f'activity_date: "{row["activity_date"]}"', f'updated: "{TODAY.isoformat()}"',
        ]
        if is_git:
            lines += [
                f'git_branch: "{quote(row["branch"])}"', f"git_dirty_files: {row['dirty_files']}",
                f'git_remote: "{quote(row["remote"])}"',
                f'github_repo: "{quote(row["github_repo"])}"',
                f'github_pushed_at: "{row["github_pushed_at"][:10]}"',
                f"remote_has_unpulled: {str(bool(row['remote_has_unpulled'])).lower()}",
            ]
        lines += ["---", "", f"# {row['relative_path']}", "", "## Inventory", "",
                  f"- Machine: `{MACHINE}`", f"- Path: `{row['path']}`",
                  f"- Version control: **{'Git repository' if is_git else 'No Git repository'}**",
                  f"- Last activity: {row['activity_date']}"]
        if is_git:
            lines += [f"- Branch: `{row['branch']}`", f"- Dirty files: {row['dirty_files']}",
                      f"- Last local commit: `{row['last_commit_sha']}` — "
                      f"{row['last_commit_subject'] or 'no message'} ({local_date(row)})"]
            if row["github_repo"]:
                pushed = row["github_pushed_at"][:10] or "no access"
                private = " (private)" if row.get("github_private") else ""
                lines.append(f"- GitHub: `{row['github_repo']}` pushed {pushed}{private}")
            if row["remote_has_unpulled"]:
                lines.append("- **Remote has commits not pulled locally.**")
        lines += ["", "## Project summary", "",
                  "Status, goal, and next action have not been reviewed yet.", "",
                  "## Next action", "",
                  "- [ ] Review and mark active, paused, archived, or reference.", ""]
        if tasks:
            lines += [tasks, ""]
        write(folder / filename, "\n".join(lines))


# --------------------------------------------------------------------------
# indexes
# --------------------------------------------------------------------------

def github_index(repos: dict[str, dict], local_by_repo: dict[str, tuple[str, str]]) -> list[dict]:
    rows = sorted(repos.values(), key=lambda r: r["pushed_at"], reverse=True)
    owned = [r for r in rows if not r["fork"]]
    forks = [r for r in rows if r["fork"]]
    recent = [r for r in rows if r["pushed_at"][:10] >= CUT_90]
    year = [r for r in owned if CUT_1Y <= r["pushed_at"][:10] < CUT_90]

    def name(repo: dict) -> str:
        return f"{repo['owner']}/{repo['name']}"

    def link(repo: dict) -> str:
        full = name(repo)
        has_note = not repo["fork"] and repo["pushed_at"][:10] >= CUT_1Y
        return f"[[Projects/GitHub/{slug(full)}|{full}]]" if has_note else f"[{full}]({repo['html_url']})"

    def clone(repo: dict) -> str:
        found = local_by_repo.get(name(repo).lower())
        if not found:
            return "—"
        kind, relative = found
        return f"[[Projects/{MACHINE}/{kind}/{slug(relative)}|{relative}]]"

    out = ["---", "source: github-api", f"accounts: [{', '.join(ACCOUNTS)}]",
           f"repository_count: {len(rows)}", f"owned_count: {len(owned)}",
           f"fork_count: {len(forks)}",
           f"private_count: {sum(1 for r in rows if r['private'])}",
           f'updated: "{TODAY.isoformat()}"', "---", "", "# GitHub Repositories", "",
           f"Metadata only — read through the GitHub API, nothing cloned. {len(rows)} repositories "
           f"across {' and '.join(f'`{a}`' for a in ACCOUNTS)}: {len(owned)} owned, {len(forks)} forks, "
           f"{sum(1 for r in rows if r['private'])} private.", "",
           "Local-clone links point at this machine's inventory and will read as missing on another machine.", "",
           "## Pushed in the last 90 days", "",
           "| Repository | Pushed | Visibility | Local clone |", "|---|---|---|---|"]
    for repo in recent:
        kind = "private" if repo["private"] else "public"
        out.append(f"| {link(repo)} | **{repo['pushed_at'][:10]}** | {kind}"
                   f"{' · fork' if repo['fork'] else ''} | {clone(repo)} |")
    out += ["", "## Owned repositories pushed in the last year", "",
            "| Repository | Pushed | Visibility | Local clone |", "|---|---|---|---|"]
    for repo in year:
        out.append(f"| {link(repo)} | {repo['pushed_at'][:10]} | "
                   f"{'private' if repo['private'] else 'public'} | {clone(repo)} |")
    out += ["", "## All owned repositories", "",
            "| Repository | Pushed | Visibility | Language |", "|---|---|---|---|"]
    for repo in owned:
        out.append(f"| {link(repo)} | {repo['pushed_at'][:10]} | "
                   f"{'private' if repo['private'] else 'public'} | {repo['language'] or '—'} |")
    out += ["", "## Forks", "", "Forks are excluded from review unless you have changes in them.", "",
            "| Repository | Pushed |", "|---|---|"]
    for repo in forks:
        out.append(f"| [{name(repo)}]({repo['html_url']}) | {repo['pushed_at'][:10]} |")
    out += ["", "## Review flow", "", "1. Confirm which repositories are genuinely active.",
            "2. Clone only what you need to work on.", "3. Create Kanban tasks after review.", ""]
    write(VAULT / "Projects" / "GitHub Repositories.md", "\n".join(out))
    return recent


def local_index(kind: str, rows: list[dict], root: Path) -> None:
    def link(row: dict) -> str:
        return f"[[Projects/{MACHINE}/{kind}/{slug(row['relative_path'])}|{row['relative_path']}]]"

    dated = sorted([r for r in rows if r["activity_date"] != "—"],
                   key=lambda r: r["activity_date"], reverse=True)
    undated = [r for r in rows if r["activity_date"] == "—"]
    recent = [r for r in dated if r["activity_date"] >= CUT_90]
    year = [r for r in dated if CUT_1Y <= r["activity_date"] < CUT_90]
    behind = [r for r in rows if r.get("remote_has_unpulled")]

    out = ["---", f'inventory_root: "{root}"', f"machine: {MACHINE}",
           f"project_count: {len(rows)}",
           f"git_repository_count: {sum(1 for r in rows if r['version_control'] == 'git')}",
           f'updated: "{TODAY.isoformat()}"', "---", "", f"# {kind} Projects on {MACHINE}", "",
           f"Scanned `{root}`. Activity is the newer of the last local commit and the GitHub push date.", "",
           "## Active in the last 90 days", "",
           "| Project | Activity | Local | GitHub |", "|---|---|---|---|"]
    for row in recent:
        out.append(f"| {link(row)} | **{row['activity_date']}** | {local_date(row)} | "
                   f"{row['github_pushed_at'][:10] or '—'} |")
    out += ["", "## Active in the last year", "",
            "| Project | Activity | Local | GitHub |", "|---|---|---|---|"]
    for row in year:
        out.append(f"| {link(row)} | {row['activity_date']} | {local_date(row)} | "
                   f"{row['github_pushed_at'][:10] or '—'} |")
    if undated:
        out += ["", "## No date available", ""]
        for row in undated:
            reason = "no Git repository" if row["version_control"] != "git" else "empty or unreadable repository"
            out.append(f"- {link(row)} — {reason}")
    if behind:
        out += ["", "## Remote commits not pulled locally", ""]
        for row in behind:
            out.append(f"- {link(row)} — GitHub push {row['github_pushed_at'][:10] or 'unknown'}")
    out += ["", "## All projects by activity", "",
            "| Project | VC | Activity | Local | GitHub |", "|---|---|---|---|---|"]
    for row in dated + undated:
        out.append(f"| {link(row)} | {'git' if row['version_control'] == 'git' else 'none'} | "
                   f"{row['activity_date']} | {local_date(row)} | {row['github_pushed_at'][:10] or '—'} |")
    out += ["", "## Review flow", "", "1. Confirm the active list.",
            "2. Add a goal and one next action for those only.",
            "3. Create Kanban tasks after review.", ""]
    write(VAULT / "Projects" / MACHINE / f"{kind} Projects.md", "\n".join(out))


def welcome(repos: dict[str, dict], scans: dict[str, list[dict]],
            recent: list[dict], review: dict[str, int]) -> None:
    owned_recent = [r for r in recent if not r["fork"]]
    year = sorted([r for r in repos.values()
                   if not r["fork"] and CUT_1Y <= r["pushed_at"][:10] < CUT_90],
                  key=lambda r: r["pushed_at"], reverse=True)

    def link(repo: dict) -> str:
        full = f"{repo['owner']}/{repo['name']}"
        return f"[[Projects/GitHub/{slug(full)}|{full}]]"

    lines = ["# Todo List", "",
             "Shared knowledge base. Machine folders hold local scans; `Projects/GitHub/` is shared.", "",
             "## Where things live", "",
             "- **Obsidian:** project notes, decisions, and context",
             "- **Kanban:** tasks, progress, and blockers — one board per machine",
             "- **Email:** original messages; keep only summaries and links here", "",
             f"This machine: `{MACHINE}`. Board: `todos`.",
             f"Last refreshed: {TODAY.isoformat()}.", "", "## Inventories", "",
             f"- [[Projects/GitHub Repositories]] — {len(repos)} repositories "
             f"on {' and '.join(f'`{a}`' for a in ACCOUNTS)} (metadata only)"]
    for kind, rows in scans.items():
        lines.append(f"- [[Projects/{MACHINE}/{kind} Projects]] — {len(rows)} folders under "
                     f"`{SCAN_ROOTS[kind]}`")
    lines += ["", "## Review status", "",
              "Only projects marked `active` raise Kanban cards. "
              "[[Review]] lists every note and is where you change that.", ""]
    for status in STATUSES:
        if review.get(status):
            lines.append(f"- {status}: {review[status]}")
    if review.get("unreviewed"):
        lines += ["", f"{review['unreviewed']} notes are still unreviewed."]
    lines += ["", "## Active in the last 90 days", "", "GitHub push dates, forks excluded.", ""]
    for repo in owned_recent:
        lines.append(f"- {link(repo)} — {repo['pushed_at'][:10]}")
    lines += ["", "## Active in the last year", ""]
    for repo in year:
        lines.append(f"- {link(repo)} — {repo['pushed_at'][:10]}")
    lines += ["", "## Next step", "",
              "Confirm which repositories are genuinely active, then add a goal and one next "
              "action to each. Create Kanban cards only for work you have decided to do.", ""]
    write(VAULT / "Welcome.md", "\n".join(lines))


STATUSES = ("active", "paused", "reference", "archived", "unreviewed")


def review_page() -> dict[str, int]:
    """Every project note grouped by review status, newest activity first.

    Reviewing means opening this page and changing one line in the notes it
    lists. Unreviewed sits at the bottom because it is the queue, not the
    answer; active sits at the top because those are the notes that can raise
    cards.
    """
    found: dict[str, list[tuple[str, str, str, bool]]] = {s: [] for s in STATUSES}
    for note in sorted((VAULT / "Projects").rglob("*.md")):
        try:
            text = note.read_text(encoding="utf-8")
        except Exception:
            continue
        status = re.search(r"^knowledge_status:\s*(\S+)\s*$", text, re.M)
        if not status:
            continue  # a note you wrote yourself, not part of the review queue
        relative = str(note.relative_to(VAULT))[:-3]
        repo = re.search(r'^github_repo:\s*"([^"]*)"\s*$', text, re.M)
        when = re.search(r'^(?:pushed_at|activity_date):\s*"([^"]*)"\s*$', text, re.M)
        found.setdefault(status.group(1), []).append((
            relative, repo.group(1) if repo else "",
            when.group(1) if when else "", bool(re.search(r"`t_[0-9a-f]+`", text)),
        ))

    counts = {s: len(v) for s, v in found.items() if v}
    total = sum(counts.values())
    out = ["---", "generated: refresh-todo-vault.py", f"note_count: {total}",
           f'updated: "{TODAY.isoformat()}"', "---", "", "# Review", "",
           "Every project note, grouped by review status. To change one, open the note",
           "and edit `knowledge_status` in its frontmatter:", "",
           "| Status | Meaning |", "|---|---|",
           "| `active` | Being worked on. A push raises a Kanban card. |",
           "| `paused` | Real, but not now. |",
           "| `reference` | Kept for lookup; no work expected. |",
           "| `archived` | Finished or abandoned. |",
           "| `unreviewed` | Not yet decided. |", "",
           "Only `active` raises cards, so the review queue below is what controls",
           "how noisy the board gets.", ""]

    for status in STATUSES:
        entries = found.get(status) or []
        if not entries:
            continue
        entries.sort(key=lambda e: (e[2] or "", e[0]), reverse=True)
        out += ["", f"## {status.title()} — {len(entries)}", "",
                "| Note | Repository | Activity | Cards |", "|---|---|---|---|"]
        for relative, repo, when, carded in entries:
            name = relative.split("/")[-1]
            out.append(f"| [[{relative}\\|{name}]] | {repo or '—'} | "
                       f"{when or '—'} | {'yes' if carded else '—'} |")

    out += ["", "## How to review", "",
            "1. Work down the unreviewed list.",
            "2. Set `knowledge_status` on each note.",
            "3. For anything active, write a goal and one next action.", ""]
    write(VAULT / "Review.md", "\n".join(out))
    return counts


# --------------------------------------------------------------------------
# report + sync
# --------------------------------------------------------------------------

def load_state() -> dict[str, str]:
    """Push dates as of the previous run — the baseline for 'what changed'."""
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text()).get("pushed_at", {})
    except Exception:
        return {}


def report(repos: dict[str, dict], scans: dict[str, list[dict]],
           seen_before: dict[str, str], raised: list[str]) -> list[str]:
    changed, added = [], []
    for full, repo in repos.items():
        if repo["fork"]:
            continue
        was = seen_before.get(full)
        if was is None:
            if repo["pushed_at"][:10] >= CUT_90:
                added.append(f"{full} (pushed {repo['pushed_at'][:10]})")
        elif repo["pushed_at"] != was:
            changed.append(f"{full} (pushed {repo['pushed_at'][:10]})")

    dirty = [f"{kind}/{r['relative_path']} ({r['dirty_files']} dirty)"
             for kind, rows in scans.items() for r in rows
             if r["version_control"] == "git" and (r["dirty_files"] or 0) > 0]
    behind = [f"{kind}/{r['relative_path']}"
              for kind, rows in scans.items() for r in rows if r.get("remote_has_unpulled")]

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({
        "refreshed": TODAY.isoformat(), "machine": MACHINE,
        "pushed_at": {full: r["pushed_at"] for full, r in repos.items()},
    }, indent=2))

    out = [f"Vault refreshed {TODAY.isoformat()} on {MACHINE}.", ""]
    out.append(f"{len(repos)} GitHub repositories, "
               f"{sum(len(rows) for rows in scans.values())} local folders.")
    if raised:
        out += ["", f"Cards raised on `{BOARD}` ({len(raised)}):"] + [f"  {r}" for r in raised]
    if changed:
        out += ["", f"Pushed since the last refresh ({len(changed)}):"] + [f"  {c}" for c in changed[:12]]
    if added:
        out += ["", f"New and recently active ({len(added)}):"] + [f"  {a}" for a in added[:12]]
    if not changed and not added:
        out += ["", "No GitHub pushes since the last refresh."]
    if dirty:
        out += ["", f"Uncommitted local changes ({len(dirty)}):"] + [f"  {d}" for d in dirty[:8]]
    if behind:
        out += ["", f"Clones behind their remote ({len(behind)}):"] + [f"  {b}" for b in behind[:8]]
    return out


def sync() -> str:
    if not (VAULT / ".git").exists():
        return "Vault is not a Git repository; skipped sync."
    git(VAULT, ["pull", "--rebase", "--autostash"], timeout=90)
    if not git(VAULT, ["status", "--porcelain"]):
        return "No vault changes to commit."
    git(VAULT, ["add", "-A"])
    git(VAULT, ["commit", "-m", f"Refresh inventory on {MACHINE} ({TODAY.isoformat()})"], timeout=60)
    pushed = subprocess.run(
        ["git", "-C", str(VAULT), "push"],
        capture_output=True, text=True, timeout=120,
        env=dict(os.environ, GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=10"))
    return "Committed and pushed." if pushed.returncode == 0 else \
        f"Committed locally; push failed: {pushed.stderr.strip()[:120]}"


def main() -> int:
    if not VAULT.is_dir():
        print(f"Vault not found: {VAULT}", file=sys.stderr)
        return 1

    repos = collect_github()
    if not repos:
        print("No GitHub metadata returned; check the tokens in ~/.hermes/.env", file=sys.stderr)
        return 1

    scans = {kind: scan_root(root) for kind, root in SCAN_ROOTS.items()}
    for rows in scans.values():
        enrich(rows, repos)

    local_by_repo = {
        row["github_repo"].lower(): (kind, row["relative_path"])
        for kind, rows in scans.items() for row in rows if row.get("github_repo")
    }

    previous = load_state()
    github_notes(repos, local_by_repo)
    recent = github_index(repos, local_by_repo)
    for kind, rows in scans.items():
        local_notes(kind, rows, SCAN_ROOTS[kind])
        local_index(kind, rows, SCAN_ROOTS[kind])
    # After the notes exist, so a card's link lands in the fresh note.
    raised = raise_cards(repos, previous)
    # Review counts feed the Welcome page, so build that page first.
    welcome(repos, scans, recent, review_page())

    lines = report(repos, scans, previous, raised)
    lines += ["", sync()]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
