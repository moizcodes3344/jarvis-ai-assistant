"""Run isolated pip-audit against explicit installed runtime package paths.

Only package names/versions go to public advisory services. Never resolve, fix,
install, suppress advisories, or print captured scanner error/source content.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile


def audit_paths(paths):
    command = [sys.executable, "-I", "-m", "pip_audit", "--strict", "--format=json",
               "--progress-spinner=off", "--timeout=15", "--vulnerability-service=pypi"]
    for path in paths:
        command.extend(["--path", path])
    env = {key: os.environ[key] for key in
           ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP") if key in os.environ}
    try:
        # Give Windows cache/home discovery a disposable profile, never the user's
        # real profile or .netrc. This also keeps advisory caches out of Git.
        with tempfile.TemporaryDirectory(prefix="jarvis-audit-") as cache:
            env.update(USERPROFILE=cache, LOCALAPPDATA=cache, APPDATA=cache)
            result = subprocess.run(command + ["--cache-dir", cache],
                                    capture_output=True, timeout=180, env=env)
        report = json.loads(result.stdout)
        dependencies = report["dependencies"]
        if not isinstance(dependencies, list) or not dependencies:
            raise ValueError("Missing audit inventory")
        count = 0
        for dependency in dependencies:
            if "skip_reason" in dependency or not isinstance(dependency["vulns"], list):
                raise ValueError("Incomplete audit")
            count += len(dependency["vulns"])
        if result.returncode not in (0, 1) or (result.returncode != 0 and not count):
            raise ValueError("Scanner failure")
        if count:
            print(f"Dependency audit FAILED: {count} known vulnerability finding(s). No automatic fixes applied.")
            return 1
        print(f"Dependency audit passed: {len(dependencies)} packages, no known vulnerabilities.")
        return 0
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        print("Dependency audit ERROR: scanner/service unavailable, invalid report, or incomplete inventory. Validation failed.")
        return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", required=True,
                        help="installed site-packages path to audit (repeatable)")
    return audit_paths(parser.parse_args().path)


if __name__ == "__main__":
    sys.exit(main())
