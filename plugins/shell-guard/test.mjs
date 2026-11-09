// Unit tests for guard.js.  Paths come from the running machine, so nothing
// here carries a machine-specific id: run `node test.mjs`.
import { homedir, tmpdir } from "node:os"
import { join } from "node:path"
import { violation, roots } from "./guard.js"

const TMP = join(tmpdir(), "opencode")
const R = roots(TMP)
const REPO = join(homedir(), "GitHub", "LuaCJK")
const OTHER = join(homedir(), "GitHub", "docext")
const PRIVATE_TMP = TMP.startsWith("/private") ? TMP : "/private" + TMP

const cases = [
  ["git -C " + REPO + " status --short", REPO, null],
  ["echo x > " + join(REPO, "t.txt"), REPO, "block"],
  ["cd " + join(tmpdir(), "probe") + " && sed -i 's/a/b/' f.tex", REPO, null],
  ["cd " + REPO + " && sed -i 's/a/b/' f.tex", REPO, "block"],
  ["git -C " + REPO + " commit -m x", REPO, "block"],
  ["cp " + join(REPO, "a") + " " + join(tmpdir(), "b"), REPO, null],
  ["cp " + join(tmpdir(), "a") + " " + join(REPO, "b"), REPO, "block"],
  ["python3 -c \"open('" + join(REPO, "x") + "','w')\"", REPO, "block"],
  // The write forms a heuristic misses unless it enumerates them (added after
  // the first audit found all eight passing).
  ["dd if=/dev/zero of=" + join(REPO, "x") + " bs=1 count=1", REPO, "block"],
  ["cd " + TMP + " && dd if=/dev/zero of=x bs=1 count=1", REPO, null],
  ["truncate -s 0 " + join(REPO, "x"), REPO, "block"],
  ["cd " + TMP + " && truncate -s 0 x", REPO, null],
  ["find " + REPO + " -delete", REPO, "block"],
  ["cd " + TMP + " && find . -delete", REPO, null],
  ["install -m 644 a " + join(REPO, "x"), REPO, "block"],
  ["cd " + TMP + " && install -m 644 a x", REPO, null],
  ["perl -i -pe s/a/b/ " + join(REPO, "f.tex"), REPO, "block"],
  ["cd " + TMP + " && perl -i -pe s/a/b/ f.tex", REPO, null],
  ["curl -o " + join(REPO, "x") + " http://example.invalid", REPO, "block"],
  ["cd " + TMP + " && curl -o x http://example.invalid", REPO, null],
  ["cd " + TMP + " && tar -xf p.tgz", REPO, null],
  ["cd " + REPO + " && tar -xf p.tgz", REPO, "block"],
  ["cd " + TMP + " && unzip p.zip", REPO, null],
  ["git am p.mbox", REPO, "block"],
  ["git worktree add ../w", REPO, "block"],
  ["python3 -c \"import os;os.remove('" + join(REPO, "x") + "')\"", REPO, "block"],
  ["python3 -c \"import shutil;shutil.rmtree('" + join(REPO, "d") + "')\"", REPO, "block"],
  // Read-only commands whose *arguments* are write verbs must stay allowed;
  // this is why the word rules are anchored to command position.
  ["grep -rn install .", REPO, null],
  ["grep -rn truncate .", REPO, null],
  ["grep -n 'perl -i' notes.txt", REPO, null],
  ["grep -n 'find . -delete' notes.txt", REPO, null],
  ["rg --files-with-matches cp", REPO, null],
  ["git status --short", REPO, null],
  ["git log --oneline -5", REPO, null],
  ["ls -la", REPO, null],
  ["mkdir -p " + join(tmpdir(), "x"), REPO, null],
  ["rm -rf " + join(tmpdir(), "x"), REPO, null],
  ["rm -rf build", REPO, "block"],
  ["grep -n foo file > " + join(tmpdir(), "out"), REPO, null],
  ["grep -n foo file > out.txt", REPO, "block"],
  ["cd " + TMP + " && l3build check > log 2>&1", REPO, null],
  ["cd " + REPO + " && l3build check", REPO, "block"],
  ["echo hi", REPO, null],
  ["tlmgr info ctex", REPO, null],
  ["git -C " + join(tmpdir(), "clone") + " commit -m x", REPO, null],
  ["cd " + TMP + " && mkdir -p probe && cp -r " + REPO + "/* probe/", REPO, null],
  ['echo "a > ' + join(REPO, "x") + '"', REPO, null],
  ["grep -n '>' file", REPO, null],
  ['echo x > "' + join(REPO, "x.txt") + '"', REPO, "block"],
  ['echo x > "' + join(TMP, "ok.txt") + '"', REPO, null],
  ["echo x > " + join(PRIVATE_TMP, "ok.txt"), REPO, null],
  ["echo x > " + join(OTHER, "x.txt"), REPO, "block"],
]

let bad = 0
for (const [cmd, base, want] of cases) {
  const got = violation(cmd, base, R)
  const norm = got ? "block" : null
  if (norm !== want) {
    bad++
    console.log("FAIL", JSON.stringify(cmd.slice(0, 70)), "want", want, "got", got)
  }
}
console.log(bad === 0 ? `all pass (${cases.length} cases)` : bad + " failed")
