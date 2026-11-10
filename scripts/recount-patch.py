#!/usr/bin/env python3
"""Recompute the line counts of every hunk in a unified diff.

Hand-editing an applied patch series (for example inserting generated code into the base XNU patch)
changes how many lines a hunk adds, while its `@@ -a,b +c,d @@` header keeps the old numbers. This
rewrites every header from the hunk body so the patch applies without fuzz.

Usage:
    recount-patch.py <patch> [<patch> ...]
"""
import re
import sys
from pathlib import Path

HEADER = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$')


def recount(patch):
    lines = patch.read_text().splitlines()
    index = 0
    changed = 0
    while index < len(lines):
        match = HEADER.match(lines[index])
        if not match:
            index += 1
            continue
        old_start = int(match.group(1))
        new_start = int(match.group(3))
        suffix = match.group(5)
        body = index + 1
        old_count = new_count = 0
        while body < len(lines):
            line = lines[body]
            if line.startswith('@@ ') or line.startswith('diff --git ') or line.startswith('--- ') and body + 1 < len(lines) and lines[body + 1].startswith('+++ '):
                break
            marker = line[:1]
            if marker == ' ' or line == '':
                old_count += 1
                new_count += 1
            elif marker == '-':
                old_count += 1
            elif marker == '+':
                new_count += 1
            elif marker == '\\':
                pass
            else:
                break
            body += 1
        header = f'@@ -{old_start},{old_count} +{new_start},{new_count} @@{suffix}'
        if header != lines[index]:
            changed += 1
        lines[index] = header
        index = body
    patch.write_text('\n'.join(lines) + '\n')
    return changed


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for name in sys.argv[1:]:
        path = Path(name)
        print(f'{path}: {recount(path)} hunk headers updated', file=sys.stderr)


if __name__ == '__main__':
    main()