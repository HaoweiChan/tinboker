#!/usr/bin/env python3
"""
Sync Tinboker TODO.md tasks to GitHub Issues and GitHub Projects.

Design principle:
    TODO.md is the single source of truth.
    GitHub Issues and GitHub Projects are derived mirrors.

This script:
    1. Parses task sections from TODO.md.
    2. Creates GitHub Issues for tasks missing github_issue.
    3. Optionally adds issues to a GitHub Project.
    4. Optionally updates selected Project fields.
    5. Writes created issue URLs and project item IDs back into TODO.md.

Requirements:
    - Python 3.11+
    - GitHub CLI installed and authenticated.
    - `gh auth refresh -s project` if syncing GitHub Projects.
    - PyYAML installed.

Install:
    uv add --dev pyyaml
    # or
    pip install pyyaml

Environment variables:
    GITHUB_REPOSITORY       Required. Example: owner/repo
    GITHUB_PROJECT_OWNER    Optional. User/org owner for the project.
    GITHUB_PROJECT_NUMBER   Optional. Project number, not project ID.
    DRY_RUN                 Optional. "1" means print actions without writing.

Examples:
    GITHUB_REPOSITORY=willy/tinboker python scripts/sync_todo_to_github.py

    GITHUB_REPOSITORY=willy/tinboker \
    GITHUB_PROJECT_OWNER=willy \
    GITHUB_PROJECT_NUMBER=1 \
    python scripts/sync_todo_to_github.py

Notes:
    GitHub Projects v2 field editing is intentionally conservative here.
    Issue creation and project item addition are stable.
    Custom field updates can be extended after your project field names and options are fixed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: PyYAML. Install with `uv add --dev pyyaml` or `pip install pyyaml`."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
TODO_PATH = ROOT / "TODO.md"

TASK_HEADING_RE = re.compile(r"^## (?P<id>TKB-\d{3}) (?P<title>.+)$", re.MULTILINE)
YAML_BLOCK_RE = re.compile(r"```yaml\n(?P<yaml>.*?)\n```", re.DOTALL)


@dataclass
class Task:
    task_id: str
    title: str
    heading_start: int
    heading_end: int
    section_start: int
    section_end: int
    metadata_start: int
    metadata_end: int
    metadata_raw: str
    metadata: dict[str, Any]
    body: str

    @property
    def github_issue(self) -> str | None:
        value = self.metadata.get("github_issue")
        if value in (None, "null", ""):
            return None
        return str(value)

    @property
    def github_project_item(self) -> str | None:
        value = self.metadata.get("github_project_item")
        if value in (None, "null", ""):
            return None
        return str(value)


def run(cmd: list[str], *, input_text: str | None = None, dry_run: bool = False) -> str:
    print("+", " ".join(cmd))
    if dry_run:
        return ""

    result = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}\n"
            f"Command: {' '.join(cmd)}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    return result.stdout.strip()


def parse_tasks(todo_text: str) -> list[Task]:
    headings = list(TASK_HEADING_RE.finditer(todo_text))
    tasks: list[Task] = []

    for index, heading in enumerate(headings):
        section_start = heading.start()
        section_end = headings[index + 1].start() if index + 1 < len(headings) else len(todo_text)
        section = todo_text[section_start:section_end]

        yaml_match = YAML_BLOCK_RE.search(section)
        if not yaml_match:
            print(f"Warning: {heading.group('id')} has no yaml metadata block; skipping.", file=sys.stderr)
            continue

        metadata_raw = yaml_match.group("yaml")
        metadata = yaml.safe_load(metadata_raw) or {}

        task_id = heading.group("id")
        if metadata.get("id") != task_id:
            raise ValueError(f"Task heading {task_id} does not match metadata id {metadata.get('id')}.")

        metadata_start = section_start + yaml_match.start("yaml")
        metadata_end = section_start + yaml_match.end("yaml")

        tasks.append(
            Task(
                task_id=task_id,
                title=heading.group("title").strip(),
                heading_start=heading.start(),
                heading_end=heading.end(),
                section_start=section_start,
                section_end=section_end,
                metadata_start=metadata_start,
                metadata_end=metadata_end,
                metadata_raw=metadata_raw,
                metadata=metadata,
                body=section,
            )
        )

    return tasks


def issue_body(task: Task) -> str:
    body_without_yaml = YAML_BLOCK_RE.sub("", task.body, count=1).strip()

    return f"""Synced from `TODO.md`.

Task: `{task.task_id}`

Priority: `{task.metadata.get("priority")}`
Status: `{task.metadata.get("status")}`
Area: `{", ".join(task.metadata.get("area") or [])}`
Type: `{task.metadata.get("type")}`
Effort: `{task.metadata.get("effort")}`
Risk: `{task.metadata.get("risk")}`

---

{body_without_yaml}

---

This issue is a mirror. `TODO.md` is the source of truth.
"""


def issue_labels(task: Task) -> list[str]:
    labels = [
        f"task:{task.task_id}",
        f"priority:{task.metadata.get('priority')}",
        f"status:{task.metadata.get('status')}",
        f"type:{task.metadata.get('type')}",
        f"risk:{task.metadata.get('risk')}",
    ]

    for area in task.metadata.get("area") or []:
        labels.append(f"area:{area}")

    return [label for label in labels if label and not label.endswith(":None")]


def create_issue(repo: str, task: Task, *, dry_run: bool) -> str:
    title = f"[{task.task_id}] {task.title}"
    body = issue_body(task)
    labels = issue_labels(task)

    cmd = [
        "gh",
        "issue",
        "create",
        "--repo",
        repo,
        "--title",
        title,
        "--body",
        body,
    ]

    if labels:
        cmd.extend(["--label", ",".join(labels)])

    output = run(cmd, dry_run=dry_run)

    if dry_run:
        return f"https://github.com/{repo}/issues/DRY-RUN-{task.task_id}"

    issue_url = output.strip().splitlines()[-1]
    if not issue_url.startswith("https://github.com/"):
        raise RuntimeError(f"Unexpected gh issue create output: {output}")

    return issue_url


def update_issue(repo: str, task: Task, *, dry_run: bool) -> None:
    if not task.github_issue:
        return

    issue_ref = task.github_issue
    body = issue_body(task)
    labels = issue_labels(task)

    cmd = [
        "gh",
        "issue",
        "edit",
        issue_ref,
        "--repo",
        repo,
        "--body",
        body,
        "--title",
        f"[{task.task_id}] {task.title}",
    ]

    if labels:
        cmd.extend(["--add-label", ",".join(labels)])

    run(cmd, dry_run=dry_run)


def get_project_id(owner: str, number: str, *, dry_run: bool) -> str:
    cmd = [
        "gh",
        "project",
        "view",
        number,
        "--owner",
        owner,
        "--format",
        "json",
    ]

    output = run(cmd, dry_run=dry_run)

    if dry_run:
        return "DRY_RUN_PROJECT_ID"

    data = json.loads(output)
    project_id = data.get("id")
    if not project_id:
        raise RuntimeError(f"Could not find project id from output: {output}")

    return project_id


def add_issue_to_project(owner: str, project_number: str, issue_url: str, *, dry_run: bool) -> str:
    cmd = [
        "gh",
        "project",
        "item-add",
        project_number,
        "--owner",
        owner,
        "--url",
        issue_url,
        "--format",
        "json",
    ]

    output = run(cmd, dry_run=dry_run)

    if dry_run:
        return f"DRY_RUN_PROJECT_ITEM_{issue_url.rsplit('/', 1)[-1]}"

    data = json.loads(output)
    item_id = data.get("id") or data.get("item", {}).get("id")
    if not item_id:
        raise RuntimeError(f"Could not find project item id from output: {output}")

    return item_id


def replace_metadata(todo_text: str, tasks: list[Task]) -> str:
    """
    Replace metadata blocks from the end of the file toward the beginning so offsets remain valid.
    """
    updated = todo_text

    for task in sorted(tasks, key=lambda t: t.metadata_start, reverse=True):
        new_raw = yaml.safe_dump(
            task.metadata,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ).strip()

        updated = updated[: task.metadata_start] + new_raw + updated[task.metadata_end :]

    return updated


def ensure_required_env() -> tuple[str, str | None, str | None, bool]:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise SystemExit("Missing GITHUB_REPOSITORY. Example: GITHUB_REPOSITORY=owner/repo")

    project_owner = os.environ.get("GITHUB_PROJECT_OWNER")
    project_number = os.environ.get("GITHUB_PROJECT_NUMBER")
    dry_run = os.environ.get("DRY_RUN") == "1"

    if bool(project_owner) ^ bool(project_number):
        raise SystemExit("Set both GITHUB_PROJECT_OWNER and GITHUB_PROJECT_NUMBER, or neither.")

    return repo, project_owner, project_number, dry_run


def main() -> int:
    repo, project_owner, project_number, dry_run = ensure_required_env()

    if not TODO_PATH.exists():
        raise SystemExit(f"TODO.md not found at {TODO_PATH}")

    todo_text = TODO_PATH.read_text(encoding="utf-8")
    tasks = parse_tasks(todo_text)

    if not tasks:
        raise SystemExit("No TKB tasks found in TODO.md.")

    print(f"Found {len(tasks)} tasks in TODO.md.")

    if project_owner and project_number:
        project_id = get_project_id(project_owner, project_number, dry_run=dry_run)
        print(f"Using GitHub Project id: {project_id}")

    changed = False

    for task in tasks:
        print(f"\n== {task.task_id} {task.title} ==")

        if task.github_issue:
            print(f"Issue exists: {task.github_issue}")
            update_issue(repo, task, dry_run=dry_run)
            issue_url = task.github_issue
        else:
            issue_url = create_issue(repo, task, dry_run=dry_run)
            print(f"Created issue: {issue_url}")
            task.metadata["github_issue"] = issue_url
            changed = True

        if project_owner and project_number:
            if task.github_project_item:
                print(f"Project item exists: {task.github_project_item}")
            else:
                item_id = add_issue_to_project(
                    project_owner,
                    project_number,
                    issue_url,
                    dry_run=dry_run,
                )
                print(f"Added to project: {item_id}")
                task.metadata["github_project_item"] = item_id
                changed = True

    if changed and not dry_run:
        updated_text = replace_metadata(todo_text, tasks)
        TODO_PATH.write_text(updated_text, encoding="utf-8")
        print(f"\nUpdated {TODO_PATH}")

    if dry_run:
        print("\nDRY_RUN=1, no files or GitHub data were changed.")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
