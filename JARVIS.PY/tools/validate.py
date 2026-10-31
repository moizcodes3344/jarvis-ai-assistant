"""Dependency-free syntax, formatting hygiene and publication safety checks.

Run from any directory. Only Git publication candidates are read; diagnostics
contain filenames, line numbers and categories, never source or secret values.
This complements manual review; pattern matching cannot prove absence of secrets.
"""

import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys


SECRET_PATTERNS = (
    r"AIza[A-Za-z0-9_-]{30,}",
    r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{30,}",
    r"AKIA[A-Z0-9]{16}",
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
)
PRIVATE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


def example_credential_issue(line):
    match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
    if not match or not re.search(r"(?:^|_)(?:PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|ACCESS_KEY|PRIVATE_KEY)$",
                                 match[1], flags=re.I):
        return None
    try:
        words = shlex.split(match[2], comments=True)
    except ValueError:
        return "invalid credential placeholder assignment"
    value = " ".join(words)
    if not value or re.fullmatch(
        r"(?:YOUR[_-][A-Z0-9_-]+|REPLACE[_-]ME|CHANGE[_-]?ME|PLACEHOLDER|EXAMPLE[_-](?:KEY|TOKEN|PASSWORD)|<YOUR[_-][A-Z0-9_-]+>)",
        value, flags=re.I,
    ):
        return None
    return "credential field requires an empty value or explicit placeholder"


def check_content(data, relative):
    """Validate exact bytes, including Git index blobs, without displaying them."""
    path = Path(relative)
    parts = Path(relative).parts
    issues = []
    if any(part in {".venv", ".venv312", ".venv-audit", "venv", "env", "__pycache__"}
           or (part.startswith(".env") and part != ".env.example") for part in parts):
        issues.append((relative, 1, "private or generated file"))
    if path.suffix.lower() in PRIVATE_SUFFIXES:
        issues.append((relative, 1, "private key container"))
    try:
        # UTF-8 BOM is valid in Python source and common in Windows editors.
        text = data.decode("utf-8-sig")
    except UnicodeError:
        return issues + [(relative, 1, "binary file requires manual review")]
    for number, line in enumerate(text.splitlines(), 1):
        if line != line.rstrip(" \t"):
            issues.append((relative, number, "trailing whitespace"))
        if re.match(r"^(?:<{7}|>{7})(?: |$)", line):
            issues.append((relative, number, "merge conflict marker"))
        if any(re.search(pattern, line) for pattern in SECRET_PATTERNS):
            issues.append((relative, number, "credential pattern"))
        if path.name == ".env.example":
            category = example_credential_issue(line)
            if category:
                issues.append((relative, number, category))
    if text and not text.endswith("\n"):
        issues.append((relative, len(text.splitlines()), "missing final newline"))
    if path.suffix == ".py":
        try:
            compile(text, relative, "exec")
        except SyntaxError as error:
            issues.append((relative, error.lineno or 1, "Python syntax error"))
    return issues


def check_file(path, relative):
    """Validate current working-tree bytes."""
    try:
        return check_content(path.read_bytes(), relative)
    except OSError:
        return [(relative, 1, "file unavailable for validation")]


def git_bytes(root, *args):
    return subprocess.run(
        ["git", "--no-optional-locks", *args], cwd=root,
        capture_output=True, check=True, timeout=30,
    ).stdout


def main(argv=None, root=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true",
                        help="scan exact index blobs instead of working-tree files")
    args = parser.parse_args(argv)
    root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    try:
        return scan(root, args.staged)
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        print("Publication validation failed: repository data unavailable or invalid.")
        return 1


def scan(root, staged):
    issues = []
    if staged:
        records = git_bytes(root, "ls-files", "--stage", "-z").split(b"\0")
        files = []
        for record in filter(None, records):
            metadata, raw_name = record.split(b"\t", 1)
            mode, oid, stage = metadata.decode("ascii").split()
            name = raw_name.decode("utf-8")
            files.append(name)
            if stage != "0":
                issues.append((name, 1, "unmerged index entry"))
            elif mode != "100644" and mode != "100755":
                issues.append((name, 1, "non-regular index entry requires review"))
            else:
                issues.extend(check_content(git_bytes(root, "cat-file", "blob", oid), name))
    else:
        data = git_bytes(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
        files = sorted(set(data.decode("utf-8").strip("\0").split("\0")) - {""})
        for name in files:
            path = root / name
            if path.is_symlink():
                issues.append((name, 1, "symlink requires manual review"))
            elif path.is_file():
                issues.extend(check_file(path, name))

    for name, line, category in issues:
        print(f"{json.dumps(name, ensure_ascii=True)}:{line}: {category}")
    print(f"Validated {len(files)} publication candidates; {len(issues)} issue(s).")
    return int(bool(issues))


if __name__ == "__main__":
    sys.exit(main())
