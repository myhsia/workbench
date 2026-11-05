#!/usr/bin/env python3
"""Fix the house spacing rule: spaces around `=` in keyword arguments and
decorator parameters (f(a = 1), @dataclass(frozen = True), def f(a: int = 3)).

Token-aware: only the raw text of a line is edited, and only at `=` token
positions that sit inside brackets after a name or a closing bracket. Strings,
comments, f-strings, `:=`, `==`, `**kwargs` and plain assignments are untouched.
Alignment is NOT applied.

Usage: style-fix.py PATH [PATH ...]     (files or directories, recursive)
Exit 0 always; prints the files it changed.
"""
import io
import os
import sys
import tokenize

SKIP_DIRS = {".git", "__pycache__", "build", ".tox", ".mypy_cache", ".pytest_cache"}


def targets(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith("_legacy")]
                for f in files:
                    if f.endswith(".py"):
                        yield os.path.join(root, f)
        elif p.endswith(".py"):
            yield p


def fix_file(path):
    with open(path, "rb") as fh:
        src = fh.read()
    try:
        toks = list(tokenize.tokenize(io.BytesIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return False

    lines = src.decode("utf-8").split("\n")
    # bracket depth per token index
    depth = 0
    edits = {}  # row -> list of (col, insert_or_shift)
    last_sig = None
    for tok in toks:
        t = tok.type
        if t == tokenize.OP:
            if tok.string in "([{":
                depth += 1
            elif tok.string in ")]}":
                depth = max(0, depth - 1)
            elif tok.string == "=" and depth > 0 and last_sig is not None:
                if last_sig.type in (tokenize.NAME, tokenize.NUMBER, tokenize.STRING) or \
                        (last_sig.type == tokenize.OP and last_sig.string in ")]}"):
                    row, col = tok.start
                    line = lines[row - 1]
                    before = line[col - 1] if col > 0 else ""
                    after = line[col + 1] if col + 1 < len(line) else ""
                    need_left = before not in (" ", "\t", "")
                    need_right = after not in (" ", "\t", "")
                    if need_left or need_right:
                        edits.setdefault(row, []).append((col, need_left, need_right))
        if t not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                     tokenize.COMMENT, tokenize.ENCODING, tokenize.ENDMARKER):
            last_sig = tok

    if not edits:
        return False
    changed = False
    for row, items in edits.items():
        line = lines[row - 1]
        for col, need_left, need_right in sorted(items, key=lambda x: -x[0]):
            if need_right:
                line = line[:col + 1] + " " + line[col + 1:]
                changed = True
            if need_left:
                line = line[:col] + " " + line[col:]
                changed = True
        lines[row - 1] = line
    if not changed:
        return False
    out = "\n".join(lines)
    if out != src.decode("utf-8"):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(out)
        return True
    return False


def main():
    changed = []
    for p in targets(sys.argv[1:]):
        try:
            if fix_file(p):
                changed.append(p)
        except Exception as e:  # never fail a tree filter
            print(f"skip {p}: {e}", file=sys.stderr)
    for c in changed:
        print(c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
