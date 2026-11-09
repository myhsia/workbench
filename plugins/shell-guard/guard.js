// Decide whether a shell command would write outside the temporary roots.
// Pure logic, no plugin imports, so it can be tested with plain node.

import { homedir, tmpdir } from "node:os"
import { resolve, join } from "node:path"

const expand = (p) => {
  let out = p
  out = out.replace(/\$\{?TMPDIR\}?/g, tmpdir())
  out = out.replace(/\$\{?HOME\}?/g, homedir())
  if (out.startsWith("~/")) out = join(homedir(), out.slice(2))
  out = out.replace(/^["']|["']$/g, "")
  return out
}

export function roots(tmpdirRoot) {
  return [tmpdirRoot, tmpdir(), "/tmp", "/private/tmp", "/var/folders"]
    .filter(Boolean)
    .map((p) => resolve(p))
}

export function inside(path, base, allowed) {
  const abs = resolve(base, expand(path))
  return allowed.some((r) => abs === r || abs.startsWith(r + "/"))
}

function baseDir(command, sessionDir) {
  const re = /(?:^|[;&|]\s*|\s)cd\s+("[^"]+"|'[^']+'|[^\s;&|]+)/g
  let base = sessionDir
  let m
  while ((m = re.exec(command))) {
    base = resolve(base, expand(m[1]))
  }
  return base
}

function gitDir(command, base) {
  const m = command.match(/\bgit\s+-C\s+("[^"]+"|'[^']+'|\S+)/)
  return m ? resolve(base, expand(m[1])) : base
}

function absolutePaths(command) {
  const out = []
  const re = /(?:^|[\s"'=(])((?:~|\/)[^\s"'`;|&)>]*)/g
  let m
  while ((m = re.exec(command))) out.push(m[1])
  return out
}

function argsAfter(command, word) {
  const re = new RegExp(`\\b${word}\\b([^;&|\\n]*)`, "g")
  const out = []
  let m
  while ((m = re.exec(command))) {
    for (const tok of m[1].trim().split(/\s+/)) {
      if (!tok || tok.startsWith("-")) continue
      out.push(tok)
    }
  }
  return out
}

const GIT_WRITE =
  /\bgit\b(?:(?:\s+-C\s+\S+)|(?:\s+--?[\w-]+(?:=\S+)?))*\s+(add|commit|push|reset|checkout|switch|apply|mv|rm|stash|clean|update-ref|filter-branch|merge|rebase|cherry-pick|restore|tag|branch\s+-[dfm])\b/
const BUILD_WRITE =
  /\b(l3build\s+(check|doc|unpack|install|upload|clean|bundle|ctan)|tlmgr\s+(install|remove|update)|latexmk\b|bibtex\b|makeindex\b|mktexlsr\b)/
const PY_WRITE = /(\bwrite_text\b|\.write\(|\bopen\([^)]*,\s*['"][wa])/

// Shell syntax outside quotes: a `>` inside a quoted string is data, not a
// redirect (`echo "a > b"`, `grep '>' file`).
function quotedMask(command) {
  const mask = new Array(command.length).fill(true)
  let q = null
  for (let i = 0; i < command.length; i++) {
    const c = command[i]
    if (q) {
      mask[i] = false
      if (c === "\\" && q === '"' && i + 1 < command.length) {
        mask[++i] = false
      } else if (c === q) {
        q = null
      }
      continue
    }
    if (c === "'" || c === '"') {
      mask[i] = false
      q = c
    }
  }
  return mask
}

function unquoted(command) {
  const mask = quotedMask(command)
  return command
    .split("")
    .filter((_, i) => mask[i])
    .join("")
}

// Targets of real (unquoted) `>`/`>>` operators, read from the raw command so a
// quoted path survives.
function redirectTargets(command) {
  const mask = quotedMask(command)
  const out = []
  for (let i = 0; i < command.length; i++) {
    if (command[i] !== ">" || !mask[i]) continue
    if (command[i - 1] === "<") continue
    let j = i + 1
    if (command[j] === ">") j++
    while (j < command.length && /\s/.test(command[j])) j++
    let token = ""
    if (command[j] === '"' || command[j] === "'") {
      const q = command[j++]
      while (j < command.length && command[j] !== q) token += command[j++]
    } else {
      while (j < command.length && !/[\s;&|]/.test(command[j])) token += command[j++]
    }
    if (token && !token.startsWith("&")) out.push(token)
  }
  return out
}

export function violation(command, sessionDir, allowed) {
  if (!command) return null
  const base = baseDir(command, sessionDir)
  const bare = unquoted(command)
  const paths = absolutePaths(command)
  const outsideAbs = paths.filter((p) => !inside(p, base, allowed))

  if (GIT_WRITE.test(bare) && !inside(gitDir(command, base), base, allowed)) {
    return "a git command that changes history or the worktree"
  }

  if (BUILD_WRITE.test(bare) && !inside(base, base, allowed)) {
    return "a build/install command that writes in its working directory"
  }

  for (const t of redirectTargets(command)) {
    if (t !== "/dev/null" && !inside(t, base, allowed)) return `a redirect into ${t}`
  }

  if (/\btee\b/.test(bare)) {
    for (const t of argsAfter(command, "tee")) {
      if (t.startsWith("/dev/")) continue
      if (!inside(t, base, allowed)) return `tee into ${t}`
    }
  }

  if (/\bsed\s+(-[a-zA-Z]*i[a-zA-Z-]*)\b/.test(bare)) {
    if (!inside(base, base, allowed)) return "an in-place sed outside the temp dir"
    if (outsideAbs.length > 0) return `an in-place sed touching ${outsideAbs[0]}`
  }

  for (const word of ["rm", "mkdir", "touch", "chmod", "ln", "mv"]) {
    if (!new RegExp(`\\b${word}\\b`).test(bare)) continue
    for (const t of argsAfter(command, word)) {
      if (t.startsWith("/dev/")) continue
      if (!inside(t, base, allowed)) return `${word} on ${t}`
    }
  }

  for (const word of ["cp", "rsync"]) {
    if (!new RegExp(`\\b${word}\\b`).test(bare)) continue
    const args = argsAfter(command, word)
    const dest = args[args.length - 1]
    if (!dest) continue
    if (!inside(dest, base, allowed)) return `${word} into ${dest}`
  }

  if (PY_WRITE.test(command)) {
    if (!inside(base, base, allowed)) return "a script that writes outside the temp dir"
    if (outsideAbs.length > 0) return `a script writing into ${outsideAbs[0]}`
  }

  return null
}
