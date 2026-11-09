import { violation, roots } from "./guard.js"
const TMP = "/private/var/folders/x6/j5n4d2x16kvfbpw_fg2d6wn00000gn/T/opencode"
const R = roots(TMP)
const B = "/Users/myhsia/GitHub/LuaCJK"
const cases = [
  ["git -C /Users/myhsia/GitHub/LuaCJK status --short", B, null],
  ["echo x > /Users/myhsia/GitHub/LuaCJK/t.txt", B, "block"],
  ["cd /tmp/probe && sed -i 's/a/b/' f.tex", B, null],
  ["cd /Users/myhsia/GitHub/LuaCJK && sed -i 's/a/b/' f.tex", B, "block"],
  ["git -C /Users/myhsia/GitHub/LuaCJK commit -m x", B, "block"],
  ["cp /Users/myhsia/GitHub/LuaCJK/a /tmp/b", B, null],
  ["cp /tmp/a /Users/myhsia/GitHub/LuaCJK/b", B, "block"],
  ["python3 - <<'PY'\nfrom pathlib import Path\nPath('/Users/myhsia/GitHub/x.txt').write_text('a')\nPY", B, "block"],
  ["mkdir -p /tmp/x", B, null],
  ["rm -rf /tmp/x", B, null],
  ["rm -rf build", B, "block"],
  ["grep -n foo file > /tmp/out", B, null],
  ["grep -n foo file > out.txt", B, "block"],
  ["cd $TMPDIR && l3build check > log 2>&1", B, null],
  ["cd /Users/myhsia/GitHub/LuaCJK && l3build check", B, "block"],
  ["echo hi", B, null],
  ["tlmgr info ctex", B, null],
  ["git -C /tmp/clone commit -m x", B, null],
  ["cd " + TMP + " && mkdir -p probe && cp -r ~/GitHub/LuaCJK/* probe/", B, null],
  ["echo \"a > /Users/myhsia/GitHub/x\"", B, null],
  ["grep -n '>' file", B, null],
  ["echo x > \"/Users/myhsia/GitHub/x.txt\"", B, "block"],
  ["echo x > \"${TMPDIR}ok.txt\"", B, null],
  ["python3 -c \"open('/Users/myhsia/GitHub/x','w')\"", B, "block"],
]
let bad = 0
for (const [cmd, base, want] of cases) {
  const got = violation(cmd, base, R)
  const norm = got ? "block" : null
  if (norm !== want) { bad++; console.log("FAIL", JSON.stringify(cmd.slice(0,60)), "want", want, "got", got) }
}
console.log(bad === 0 ? "all pass" : bad + " failed")
