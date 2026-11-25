"""Fail if a file the app needs is missing from a deploy zip list.

Checks every local Python module app.py imports (directly or through other local modules)
and every file under static/ against the zip commands in deploy/azure.sh and
.github/workflows/deploy.yml.
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY_FILES = ["deploy/azure.sh", ".github/workflows/deploy.yml"]


def local_modules(entry: str = "app.py") -> set[str]:
    """Return app.py plus every .py file in the repo root it imports, followed recursively."""
    found, todo = set(), [entry]
    while todo:
        name = todo.pop()
        if name in found:
            continue
        found.add(name)
        for node in ast.walk(ast.parse((ROOT / name).read_text())):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            else:
                continue
            for mod in mods:
                path = mod.split(".")[0] + ".py"
                if (ROOT / path).is_file():
                    todo.append(path)
    return found


def zip_entries(path: str) -> set[str]:
    """Return every word in the file's zip commands, with backslash line breaks joined."""
    text = re.sub(r"\\\n", " ", (ROOT / path).read_text())
    words = set()
    for line in text.splitlines():
        if re.search(r"\bzip\s+-q", line):
            words.update(line.split())
    if not words:
        sys.exit(f"No zip command found in {path}. Update scripts/check_deploy_lists.py.")
    return words


def covered(file: str, entries: set[str]) -> bool:
    """True if the file, or a folder that holds it, is in the zip list."""
    parts = Path(file).parts
    return any("/".join(parts[:i]) in entries for i in range(1, len(parts) + 1))


def main() -> int:
    needed = sorted(local_modules())
    needed += sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "static").rglob("*") if p.is_file())
    failed = False
    for deploy in DEPLOY_FILES:
        entries = zip_entries(deploy)
        for file in needed:
            if not covered(file, entries):
                print(f"FAIL: {file} is not in the zip list in {deploy}")
                failed = True
    if not failed:
        print(f"OK: {len(needed)} app files are in both zip lists.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
