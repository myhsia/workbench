#!/usr/bin/env python3
"""Token-aware lint for the house `=` spacing, and nothing else.

Flags `=` used as a keyword argument, a function default, or a decorator
parameter without a space on both sides (`f(a=1)`, `@dataclass(frozen=True)`).
Alignment is *not* checked: it stays advisory.

Paths may be files or directories; directories are scanned recursively,
skipping `.git/`, `__pycache__/` and `*_legacy/`.  Strings and comments are
never touched, because the scan follows the token stream.  Prints
`file:line: source` and exits 1 on findings, 0 when clean.

    python3 style-lint.py                 # scan the current directory
    python3 style-lint.py src/ a.py       # scan a tree and one file
"""

import io
import os
import sys
import tokenize

SKIP_DIRS = {".git", "__pycache__"}
SKIP_SUFFIX = "_legacy"

FSTRING_START = getattr(tokenize, "FSTRING_START", None)
FSTRING_END = getattr(tokenize, "FSTRING_END", None)

IGNORED = {
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENCODING,
    tokenize.COMMENT,
}
if hasattr(tokenize, "FSTRING_MIDDLE"):
    IGNORED.add(tokenize.FSTRING_MIDDLE)


def python_files(paths):
    """Yield the Python files named by `paths`, expanding directories."""
    for path in paths:
        if not os.path.isdir(path):
            yield path
            continue
        for root, dirs, files in os.walk(path):
            dirs[:] = sorted(
                name for name in dirs
                if name not in SKIP_DIRS
                and not name.endswith(SKIP_SUFFIX)
            )
            for name in sorted(files):
                if name.endswith(".py"):
                    yield os.path.join(root, name)


def findings(path, text):
    """Return the `(row, source)` positions of unspaced keyword `=`."""
    lines = text.splitlines()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError) as error:
        print(f"{path}: could not tokenize ({error})", file = sys.stderr)
        return []

    found = []
    stack = []
    previous = None
    fstring = 0

    for token in tokens:
        kind, string, start, end, _ = token

        if FSTRING_START is not None and kind == FSTRING_START:
            fstring += 1
        elif FSTRING_END is not None and kind == FSTRING_END:
            fstring = max(0, fstring - 1)

        if kind in IGNORED:
            continue

        if kind == tokenize.OP and string in "([{":
            stack.append(string)
        elif kind == tokenize.OP and string in ")]}":
            if stack:
                stack.pop()
        elif (
            kind == tokenize.OP
            and string == "="
            and fstring == 0
            and stack
            and stack[-1] in "(["
            and previous is not None
            and (
                previous.type == tokenize.NAME
                or previous.string in (")", "]")
            )
        ):
            row = start[0]
            line = lines[row - 1] if row - 1 < len(lines) else ""
            spaced_left = start[1] > 0 and line[start[1] - 1] == " "
            spaced_right = end[1] < len(line) and line[end[1]] == " "
            if not (spaced_left and spaced_right):
                found.append((row, line.strip()))

        previous = token

    return found


def main(argv):
    problems = 0
    for path in python_files(argv or ["."]):
        try:
            with open(path, "r", encoding = "utf-8") as handle:
                text = handle.read()
        except OSError as error:
            print(f"{path}: {error}", file = sys.stderr)
            continue
        for row, source in findings(path, text):
            print(f"{path}:{row}: {source}")
            problems += 1

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
