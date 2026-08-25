#!/usr/bin/env python3
"""Publish safe local project observations for Project Kanban.

The script reads canonical project ids from Obsidian and local Git metadata.
It writes and path-scopes one JSON file for this device. It never creates
project notes or Kanban cards and never stages unrelated vault changes.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path


def local_setting(name: str, env: Path | None = None) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    env = env or Path("~/.hermes/.env").expanduser()
    try:
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


VAULT = Path(os.environ.get("TODO_VAULT", "~/Documents/WikiHub/todo-list")).expanduser()
MACHINE = local_setting("TODO_MACHINE")
PROJECT_MAP = Path(os.environ.get("TODO_PROJECT_MAP", "~/.hermes/project-map.json")).expanduser()
ACCOUNTS = ("yangjl", "jyanglab")
SCAN_ROOTS = (
    Path("~/Documents/projects").expanduser(),
    Path("~/Documents/website").expanduser(),
)
SKIP_DIRS = {
    ".git", ".cache", ".next", ".venv", "__pycache__", "build", "data",
    "dist", "node_modules", "target", "vendor", "venv",
}


def git(path: Path | str, args: list[str], timeout: int = 15) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), *args],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
        ).strip()
    except Exception:
        return ""


def tokens(env: Path | None = None) -> list[str]:
    env = env or Path("~/.hermes/.env").expanduser()
    found: list[str] = []
    try:
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith(("GITHUB_TOKEN_", "GITHUB_TOKEN=")):
                value = line.split("=", 1)[1].strip()
                if value and value not in found:
                    found.append(value)
    except OSError:
        pass
    if found:
        return found
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=15,
        )
        value = result.stdout.strip() if result.returncode == 0 else ""
        return [value] if value else []
    except Exception:
        return []


def _api_pages(path: str, token: str) -> list[dict]:
    rows: list[dict] = []
    url: str | None = "https://api.github.com" + path
    while url:
        request = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "project-kanban-observations",
        })
        response = urllib.request.urlopen(request, timeout=30)
        rows += json.load(response)
        url = None
        for part in response.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
    return rows


def collect_github() -> dict[str, str]:
    """Latest push timestamps keyed by normalized owner/repository."""
    found: dict[str, str] = {}
    paths = (
        "/user/repos?per_page=100&affiliation=owner,collaborator,organization_member&sort=pushed",
        "/orgs/jyanglab/repos?per_page=100&type=all&sort=pushed",
    )
    for token in tokens():
        for path in paths:
            try:
                for repo in _api_pages(path, token):
                    full = str(repo.get("full_name", "")).lower()
                    owner = str(repo.get("owner", {}).get("login", ""))
                    if full and owner in ACCOUNTS:
                        found[full] = str(repo.get("pushed_at", ""))
            except Exception as exc:
                print(f"GitHub metadata unavailable: {type(exc).__name__}", file=sys.stderr)
    return found


def normalize_github_remote(remote: str) -> str:
    value = remote.strip()
    match = re.match(
        r"^(?:(?:https|ssh)://(?:git@)?github\.com/|git@github\.com:)([^/]+/[^/]+?)(?:\.git)?/?$",
        value,
        re.I,
    )
    return match.group(1).lower() if match else ""


def _tracking_counts(path: Path) -> tuple[int, int]:
    value = git(path, ["rev-list", "--left-right", "--count", "@{upstream}...HEAD"])
    try:
        behind, ahead = (int(part) for part in value.split())
        return ahead, behind
    except (TypeError, ValueError):
        return 0, 0


def scan_root(root: Path) -> list[dict]:
    """Read Git roots and top-level non-Git folders under one configured root."""
    if not root.is_dir():
        return []
    git_roots: list[Path] = []
    for base, dirs, files in os.walk(root):
        if ".git" in dirs or ".git" in files:
            git_roots.append(Path(base))
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
    git_roots = sorted(set(path for path in git_roots if path != root))
    rows: list[dict] = []
    for path in git_roots:
        epoch = git(path, ["log", "-1", "--format=%ct", "--all"])
        head = git(path, ["rev-parse", "--short", "HEAD"])
        ahead, behind = _tracking_counts(path)
        rows.append({
            "name": path.name,
            "path": str(path),
            "version_control": "git",
            "remote": git(path, ["remote", "get-url", "origin"]),
            "last_epoch": int(epoch) if epoch.isdigit() else 0,
            "last_commit_sha": head,
            "dirty_files": len(git(path, ["status", "--porcelain"]).splitlines()),
            "ahead": ahead,
            "behind": behind,
        })
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith(".") or entry in git_roots:
            continue
        if any(str(path).startswith(str(entry) + os.sep) for path in git_roots):
            continue
        rows.append({
            "name": entry.name,
            "path": str(entry),
            "version_control": "none",
            "remote": "",
            "last_epoch": 0,
            "last_commit_sha": "",
            "dirty_files": None,
            "ahead": 0,
            "behind": 0,
        })
    return sorted(rows, key=lambda row: (str(row["name"]).lower(), str(row["path"])))


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


def _canonical_maps(vault: Path) -> tuple[dict[str, str], set[str]]:
    candidates: list[tuple[str, str]] = []
    id_counts: dict[str, int] = {}
    projects = vault / "Projects"
    if not projects.is_dir():
        return {}, set()
    for note in sorted(projects.rglob("*.md")):
        metadata = _frontmatter(note)
        project_id = metadata.get("project_id", "")
        if metadata.get("knowledge_status", "").lower() != "active" or not re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*", project_id,
        ):
            continue
        repo = str(metadata.get("github_repo", "")).lower().removesuffix(".git").strip("/")
        if repo and not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", repo):
            repo = ""
        candidates.append((project_id, repo))
        id_counts[project_id] = id_counts.get(project_id, 0) + 1
    ids = {project_id for project_id, count in id_counts.items() if count == 1}
    repo_claims: dict[str, set[str]] = {}
    for project_id, repo in candidates:
        if project_id in ids and repo:
            repo_claims.setdefault(repo, set()).add(project_id)
    by_repo = {
        repo: next(iter(project_ids))
        for repo, project_ids in repo_claims.items()
        if len(project_ids) == 1
    }
    return by_repo, ids


def _local_map(path: Path, valid_ids: set[str]) -> dict[str, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {
        str(Path(local).expanduser().resolve()): project_id
        for local, project_id in value.items()
        if isinstance(local, str) and isinstance(project_id, str) and project_id in valid_ids
    }


def _activity_at(epoch: object) -> str:
    if not isinstance(epoch, int) or epoch <= 0:
        return ""
    return datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc).isoformat()


def project_observation_snapshot(
    rows: list[dict],
    *,
    machine: str = MACHINE,
    observed_at: str | None = None,
    mapping_path: Path = PROJECT_MAP,
    github_activity: dict[str, str] | None = None,
) -> dict:
    by_repo, valid_ids = _canonical_maps(VAULT)
    by_path = _local_map(mapping_path, valid_ids)
    github_activity = github_activity or {}
    matched: dict[str, dict] = {}
    unmatched: list[dict] = []
    for row in rows:
        repo = normalize_github_remote(str(row.get("remote", "")))
        local_path = str(Path(str(row.get("path", ""))).expanduser().resolve())
        local_project = by_path.get(local_path, "") if row.get("version_control") != "git" else ""
        project_id = by_repo.get(repo) or local_project
        evidence = {
            "project_id": project_id,
            "github_repo": repo,
            "activity_at": _activity_at(row.get("last_epoch")),
            "github_pushed_at": github_activity.get(repo, ""),
            "head": str(row.get("last_commit_sha", "")),
            "dirty_count": int(row.get("dirty_files") or 0),
            "ahead": int(row.get("ahead") or 0),
            "behind": int(row.get("behind") or 0),
        }
        if project_id:
            prior = matched.get(project_id)
            if prior is None or (evidence["activity_at"], evidence["github_repo"]) > (
                prior["activity_at"], prior["github_repo"],
            ):
                matched[project_id] = evidence
            continue
        source = repo or f"local-{hashlib.sha256(local_path.encode()).hexdigest()[:12]}"
        unmatched.append({
            "source": source,
            "kind": "github" if repo else "local-folder",
            "activity_at": evidence["activity_at"],
            "dirty_count": evidence["dirty_count"],
            "ahead": evidence["ahead"],
            "behind": evidence["behind"],
        })
    return {
        "schema_version": 1,
        "device": machine,
        "observed_at": observed_at or datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "projects": sorted(matched.values(), key=lambda row: row["project_id"]),
        "unmatched": sorted(unmatched, key=lambda row: (row["source"], row["kind"])),
    }


def write_observation_snapshot(snapshot: dict, *, vault: Path = VAULT) -> Path:
    device = str(snapshot.get("device", "")).strip()
    if not device:
        raise RuntimeError("TODO_MACHINE is required before publishing observations")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", device) or set(device) <= {"."}:
        raise ValueError("TODO_MACHINE must contain only letters, numbers, dot, underscore, or hyphen")
    stored = dict(snapshot)
    stored["projects"] = sorted(snapshot.get("projects", []), key=lambda row: row.get("project_id", ""))
    stored["unmatched"] = sorted(snapshot.get("unmatched", []), key=lambda row: (row.get("source", ""), row.get("kind", "")))
    target = vault / "Observations" / "devices" / f"{device}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(stored, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def _valid_timestamp(value: object, *, optional: bool = False) -> bool:
    if value == "" and optional:
        return True
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _valid_count(value: object) -> bool:
    return type(value) is int and value >= 0


def _valid_observation_snapshot(value: object, device: str) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "device", "observed_at", "projects", "unmatched",
    }:
        return False
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or not isinstance(value["device"], str)
        or value["device"] != device
        or not _valid_timestamp(value["observed_at"])
        or not isinstance(value["projects"], list)
        or not isinstance(value["unmatched"], list)
    ):
        return False
    project_keys = {
        "project_id", "github_repo", "activity_at", "github_pushed_at", "head",
        "dirty_count", "ahead", "behind",
    }
    projects = value["projects"]
    for row in projects:
        if not isinstance(row, dict) or set(row) != project_keys:
            return False
        if not isinstance(row["project_id"], str) or not re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*", row["project_id"]
        ):
            return False
        if not isinstance(row["github_repo"], str) or (
            row["github_repo"]
            and not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", row["github_repo"])
        ):
            return False
        if not _valid_timestamp(row["activity_at"], optional=True) or not _valid_timestamp(
            row["github_pushed_at"], optional=True
        ):
            return False
        if not isinstance(row["head"], str) or (
            row["head"] and not re.fullmatch(r"[0-9a-f]{4,40}", row["head"])
        ):
            return False
        if not all(_valid_count(row[key]) for key in ("dirty_count", "ahead", "behind")):
            return False
    if projects != sorted(projects, key=lambda row: row["project_id"]) or len({
        row["project_id"] for row in projects
    }) != len(projects):
        return False
    unmatched_keys = {"source", "kind", "activity_at", "dirty_count", "ahead", "behind"}
    unmatched = value["unmatched"]
    for row in unmatched:
        if not isinstance(row, dict) or set(row) != unmatched_keys:
            return False
        source = row["source"]
        kind = row["kind"]
        if not isinstance(kind, str):
            return False
        if kind == "github":
            if not isinstance(source, str) or not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", source):
                return False
        elif kind == "local-folder":
            if not isinstance(source, str) or not re.fullmatch(r"local-[0-9a-f]{12}", source):
                return False
        else:
            return False
        if not _valid_timestamp(row["activity_at"], optional=True) or not all(
            _valid_count(row[key]) for key in ("dirty_count", "ahead", "behind")
        ):
            return False
    return unmatched == sorted(unmatched, key=lambda row: (row["source"], row["kind"]))


def _validate_observation_commit(base: list[str], commit: str, relative: str) -> None:
    expected_subject = f"chore: observe projects from {Path(relative).stem}"
    subject = subprocess.run(
        [*base, "show", "-s", "--format=%s", commit], capture_output=True, text=True
    )
    paths = subprocess.run(
        [*base, "diff-tree", "--no-commit-id", "--name-only", "-r", commit],
        capture_output=True,
        text=True,
    )
    if (
        subject.returncode != 0
        or paths.returncode != 0
        or (subject.stdout or "").strip() != expected_subject
        or (paths.stdout or "").splitlines() != [relative]
    ):
        raise RuntimeError(
            "Vault has unrelated local commits; publish or reconcile them separately. No files were staged"
        )
    blob = subprocess.run(
        [*base, "show", f"{commit}:{relative}"], capture_output=True, text=True
    )
    try:
        snapshot = json.loads(blob.stdout or "")
    except (TypeError, ValueError):
        snapshot = None
    if blob.returncode != 0 or not _valid_observation_snapshot(snapshot, Path(relative).stem):
        raise RuntimeError("Vault has an unsafe observation snapshot in local history; nothing was pushed")


def _publication_state(vault: Path, relative: str) -> dict[str, object]:
    base = ["git", "-C", str(vault)]
    fetched = subprocess.run([*base, "fetch", "--quiet"], capture_output=True, text=True)
    if fetched.returncode != 0:
        raise RuntimeError("Could not fetch the vault upstream; no files were staged")
    state = subprocess.run(
        [*base, "rev-list", "--left-right", "--count", "@{upstream}...HEAD"],
        capture_output=True,
        text=True,
    )
    try:
        behind, ahead = (int(part) for part in state.stdout.split())
    except (AttributeError, TypeError, ValueError):
        raise RuntimeError("Could not determine vault divergence; no files were staged") from None
    if state.returncode != 0:
        raise RuntimeError("Could not determine vault divergence; no files were staged")
    if behind:
        raise RuntimeError(
            "Vault is behind its upstream; reconcile with git pull --rebase, then rerun. No files were staged"
        )
    head = subprocess.run([*base, "rev-parse", "HEAD"], capture_output=True, text=True)
    upstream = subprocess.run(
        [*base, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        capture_output=True,
        text=True,
    )
    upstream_name = upstream.stdout.strip()
    if head.returncode != 0 or upstream.returncode != 0 or "/" not in upstream_name:
        raise RuntimeError("Could not determine the vault upstream; no files were staged")
    remote, branch = upstream_name.split("/", 1)
    if ahead:
        commits = subprocess.run(
            [*base, "rev-list", "--reverse", "@{upstream}..HEAD"],
            capture_output=True,
            text=True,
        )
        if commits.returncode != 0:
            raise RuntimeError("Could not validate local vault commits; no files were staged")
        for commit in commits.stdout.split():
            _validate_observation_commit(base, commit, relative)
    return {"ahead": ahead, "head": head.stdout.strip(), "remote": remote, "branch": branch}


def _push_snapshot(base: list[str], state: dict[str, object], commit: str) -> None:
    try:
        subprocess.run(
            [*base, "push", str(state["remote"]), f"{commit}:refs/heads/{state['branch']}"],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Observation commit remains local; reconcile the vault remote, then rerun to retry the push"
        ) from exc


def publish_snapshot(
    target: Path,
    *,
    vault: Path = VAULT,
    publication_state: dict[str, object] | None = None,
) -> None:
    relative = str(target.relative_to(vault))
    base = ["git", "-C", str(vault)]
    state = _publication_state(vault, relative) if publication_state is None else publication_state
    subprocess.run([*base, "add", "--", relative], check=True)
    current_head = subprocess.run([*base, "rev-parse", "HEAD"], capture_output=True, text=True)
    if current_head.returncode != 0 or current_head.stdout.strip() != state["head"]:
        raise RuntimeError("Vault HEAD changed during observation publication; no commit was created")
    changed = subprocess.run(
        [*base, "diff", "--cached", "--quiet", "--", relative],
        check=False,
    )
    if changed.returncode == 0:
        if state["ahead"]:
            _push_snapshot(base, state, str(state["head"]))
        return
    if changed.returncode != 1:
        raise subprocess.CalledProcessError(changed.returncode, changed.args)
    subprocess.run([
        *base,
        "commit",
        "-m",
        f"chore: observe projects from {target.stem}",
        "--",
        relative,
    ], check=True)
    committed = subprocess.run([*base, "rev-parse", "HEAD"], capture_output=True, text=True)
    parent = subprocess.run([*base, "rev-parse", "HEAD^"], capture_output=True, text=True)
    if (
        committed.returncode != 0
        or parent.returncode != 0
        or parent.stdout.strip() != state["head"]
    ):
        raise RuntimeError("Vault HEAD changed during observation commit; the commit was not pushed")
    _validate_observation_commit(base, committed.stdout.strip(), relative)
    _push_snapshot(base, state, committed.stdout.strip())


def publish_observations() -> Path:
    if not MACHINE:
        raise RuntimeError("TODO_MACHINE is required before publishing observations")
    relative = f"Observations/devices/{MACHINE}.json"
    publication_state = _publication_state(VAULT, relative)
    rows = [row for root in SCAN_ROOTS for row in scan_root(root)]
    snapshot = project_observation_snapshot(rows, machine=MACHINE, github_activity=collect_github())
    target = write_observation_snapshot(snapshot, vault=VAULT)
    publish_snapshot(target, vault=VAULT, publication_state=publication_state)
    return target


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments != ["--publish-observations"]:
        print("Usage: refresh-todo-vault.py --publish-observations", file=sys.stderr)
        return 2
    if not VAULT.is_dir():
        print(f"Vault not found: {VAULT}", file=sys.stderr)
        return 1
    target = publish_observations()
    print(f"Wrote {target.relative_to(VAULT)} for {MACHINE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())