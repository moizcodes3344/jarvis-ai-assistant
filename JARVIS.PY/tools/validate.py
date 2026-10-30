"""Dependency-free syntax, formatting hygiene and publication safety checks.

Run from any directory. Only Git publication candidates are read; diagnostics
contain filenames, line numbers and categories, never source or secret values.
This complements manual review; pattern matching cannot prove absence of secrets.
"""

from pathlib import Path
import re
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


def check_file(path, relative):
    """Return only redacted issue descriptions for a candidate file."""
    parts = Path(relative).parts
    issues = []
    if any(part in {".venv", ".venv312", "venv", "env", "__pycache__"}
           or (part.startswith(".env") and part != ".env.example") for part in parts):
        issues.append((relative, 1, "private or generated file"))
    if path.suffix.lower() in PRIVATE_SUFFIXES:
        issues.append((relative, 1, "private key container"))
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError:
        return issues + [(relative, 1, "binary file requires manual review")]
    for number, line in enumerate(text.splitlines(), 1):
        if line != line.rstrip(" \t"):
            issues.append((relative, number, "trailing whitespace"))
        if re.match(r"^(?:<{7}|>{7})(?: |$)", line):
            issues.append((relative, number, "merge conflict marker"))
        if any(re.search(pattern, line) for pattern in SECRET_PATTERNS):
            issues.append((relative, number, "credential pattern"))
    if text and not text.endswith("\n"):
        issues.append((relative, len(text.splitlines()), "missing final newline"))
    if path.suffix == ".py":
        try:
            compile(text, relative, "exec")
        except SyntaxError as error:
            issues.append((relative, error.lineno or 1, "Python syntax error"))
    return issues


def main():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "--no-optional-locks", "ls-files", "--cached", "--others",
         "--exclude-standard", "-z"], cwd=root, capture_output=True, check=True,
    )
    files = sorted(set(result.stdout.decode("utf-8").strip("\0").split("\0")) - {""})
    issues = []
    for name in files:
        path = root / name
        if path.is_symlink():
            issues.append((name, 1, "symlink requires manual review"))
        elif path.is_file():
            issues.extend(check_file(path, name))
    for name, line, category in issues:
        print(f"{name}:{line}: {category}")
    print(f"Validated {len(files)} publication candidates; {len(issues)} issue(s).")
    return int(bool(issues))


if __name__ == "__main__":
    sys.exit(main())
