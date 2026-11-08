#!/usr/bin/env python3
"""Catch workflow mistakes locally before spending a macOS run."""
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/package.yml"


def check_runs(doc, errors):
    for job, spec in doc["jobs"].items():
        for step in spec.get("steps", []):
            name = step.get("name") or step.get("uses") or "?"
            run = step.get("run") or ""
            if not run:
                continue
            result = subprocess.run(["bash", "-n", "-c", run], capture_output=True, text=True)
            if result.returncode:
                tail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "syntax error"
                errors.append(f"{job}/{name}: bash -n: {tail}")


def check_env_keys(text, errors):
    seen, indent = {}, None
    for number, line in enumerate(text.split(chr(10)), start=1):
        stripped = line.strip()
        lead = len(line) - len(line.lstrip())
        if stripped == "env:" and lead == 8:
            seen, indent = {}, lead
            continue
        if indent is None:
            continue
        if stripped and lead <= indent:
            indent = None
            continue
        if ":" in stripped and lead == indent + 2:
            key = stripped.split(":", 1)[0]
            if key in seen:
                errors.append(f"line {number}: duplicate env key {key}")
            seen[key] = True


def check_flags(doc, errors):
    for job, spec in doc["jobs"].items():
        for step in spec.get("steps", []):
            run = (step.get("run") or "").replace("\\" + chr(10), " ")
            for match in re.finditer(r"python[\d.]*\s+(\S+\.py)([^;&|\n]*)", run):
                script, tail = match.group(1), match.group(2)
                path = ROOT / script.replace("device/", "")
                if not path.is_file():
                    continue
                body = path.read_text()
                for flag in re.findall(r"(?<!\w)(--[a-z0-9-]+)", tail):
                    if flag not in body:
                        errors.append(f"{script}: {flag} is not an option of that script")


def main():
    text = WORKFLOW.read_text()
    doc = yaml.safe_load(text)
    errors = []
    check_runs(doc, errors)
    check_env_keys(text, errors)
    check_flags(doc, errors)
    for error in errors:
        print(f"error: {error}")
    print(f"{len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())