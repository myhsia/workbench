import { Plugin } from "@opencode/plugin"
import { execFile } from "node:child_process"
import { readFile, writeFile, rename } from "node:fs/promises"
import { homedir } from "node:os"
import { join } from "node:path"
import { promisify } from "node:util"

// Daily upkeep, done rather than remembered: refresh the Westlake model list
// once a day, and say so when the OpenCode half of `opencode-hpc-update` is
// due.  The OpenCode version check stays with the skill: a plugin cannot
// install a binary, and a wrong guess ends the session that runs it.

const run = promisify(execFile)

const configDir = join(homedir(), ".config", "opencode")
const configPath = join(configDir, "opencode.json")
const modelMarker = join(configDir, ".models-check")
const ignorePath = join(configDir, ".models-ignore")
const modelList = "https://hpc-api.westlake.edu.cn/v1/models"

// The endpoint also lists embeddings and rerankers, which are not chat models
// and would show up in the model picker.
const notChat = /embed|rerank/i

// Model ids the user has removed from the configuration on purpose.  The
// upstream list keeps reporting them, so the plugin only mentions them; the
// file is versioned, which is where that decision lives.
const ignoredModels = async () => {
  const text = await readText(ignorePath)
  if (!text) return new Set()
  return new Set(
    text
      .split("\n")
      .map((line) => line.replace(/#.*/, "").trim())
      .filter(Boolean),
  )
}

const today = () =>
  new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Shanghai" })

const readText = async (path) => {
  try {
    return await readFile(path, "utf8")
  } catch {
    return undefined
  }
}

const modelsCheckedToday = async () =>
  (await readText(modelMarker))?.trim() === today()

// Run one of the check scripts and report its exit code instead of throwing:
// 0 means DUE (update-due.sh) or STALE (guides-due.sh), and 2 means MISSING.
const runCheck = async (script: string, args: string[]) => {
  try {
    await run("bash", [join(configDir, "scripts", script), ...args], {
      timeout: 10_000,
    })
    return 0
  } catch (error) {
    const code = (error as { code?: unknown }).code
    return typeof code === "number" ? code : 1
  }
}

const upkeepDue = async () => (await runCheck("update-due.sh", [])) === 0

const guidesDue = async (dir: string) => {
  const code = await runCheck("guides-due.sh", ["--committed", dir])
  return code === 0 || code === 2
}

// The 2026-11-05 history-rewrite rollback bundles live outside the
// repositories; keep asking whether they can go until they are deleted.
const backupsPending = async () => (await runCheck("backups-pending.sh", [])) === 0

// A repository may declare one check of its own in AGENTS.md:
//     Session check: `scripts/check-extract-changes.sh`
// Only that declared path is run, with the repository as the working
// directory, so a checkout cannot get code executed by merely shipping a
// file.  Exit 0 is silence and exit 2 means "cannot run here"; anything else
// is reported, with the first lines of its output.
const sessionCheck = async (dir: string) => {
  const guide = await readText(join(dir, "AGENTS.md"))
  const path = guide?.match(/^Session check: `([^`]+)`/m)?.[1]
  if (!path || path.startsWith("/") || path.includes("..")) return undefined
  try {
    await run("bash", [path], { cwd: dir, timeout: 10_000 })
    return undefined
  } catch (error) {
    const { code, stdout } = error as { code?: unknown; stdout?: unknown }
    if (code === 2) return undefined
    const text = typeof stdout === "string" ? stdout.trim() : ""
    return (
      text.split("\n").slice(0, 3).join(" ").trim() ||
      `session check failed (exit ${String(code)})`
    )
  }
}

// The prompt hook carries the session id; the session's directory is not part
// of the documented payload.  LIMITATION: the fallback is the process working
// directory, so a session moved elsewhere without a new process (`session_move`)
// keeps reporting its original directory until the day rolls over.
const sessionDir = (event: unknown) => {
  const payload = event as {
    directory?: unknown
    session?: { directory?: unknown }
  }
  for (const candidate of [payload?.directory, payload?.session?.directory]) {
    if (typeof candidate === "string" && candidate.length > 0) return candidate
  }
  return process.cwd()
}

// Insert entries into the `"models"` object of the text, leaving every other
// byte alone: the configuration is hand-formatted, and a JSON round trip
// would reprint the permission table.  The indentation is taken from an
// existing entry, and the block keeps its own closing brace column.
const addModels = (text, entries) => {
  const key = text.indexOf('"models"')
  if (key < 0) return text
  const open = text.indexOf("{", key)
  if (open < 0) return text

  let depth = 0
  let close = -1
  let quoted = false
  for (let i = open; i < text.length; i++) {
    const c = text[i]
    if (quoted) {
      if (c === "\\") i++
      else if (c === '"') quoted = false
      continue
    }
    if (c === '"') quoted = true
    else if (c === "{") depth++
    else if (c === "}" && --depth === 0) {
      close = i
      break
    }
  }
  if (close < 0) return text

  const keyIndent = text.slice(text.lastIndexOf("\n", key) + 1, key)
  const body = text.slice(open + 1, close)
  const pad = body.match(/\n([ \t]+)"/)?.[1] ?? `${keyIndent}  `

  const added = entries.map(([id, value]) => {
    const json = JSON.stringify(value, null, "  ")
      .split("\n")
      .map((line, index) => (index === 0 ? line : pad + line))
      .join("\n")
    return `${pad}${JSON.stringify(id)}: ${json}`
  })

  const kept = body.replace(/^\s*\n/, "").replace(/\s+$/, "").replace(/,$/, "")
  const merged = kept ? `${kept},\n${added.join(",\n")}` : added.join(",\n")
  return `${text.slice(0, open + 1)}\n${merged}\n${keyIndent}${text.slice(close)}`
}

// Add the chat models the endpoint reports and the configuration does not
// have yet.  Nothing is removed: a model that disappeared upstream may still
// be the one a session is using, so it is reported instead.  A new entry
// copies the capability block of an existing one, which the user then
// reviews.
const refreshModels = async () => {
  const key = process.env.WESTLAKE_API_KEY
  if (!key) return []

  const response = await fetch(modelList, {
    headers: { Authorization: `Bearer ${key}` },
    signal: AbortSignal.timeout(20_000),
  })
  if (!response.ok) throw new Error(`model list: HTTP ${response.status}`)

  const body = await response.json()
  const online = (body.data ?? []).map((model) => model.id).filter(Boolean)
  if (online.length === 0) return []

  const before = await readText(configPath)
  if (!before) return []
  const config = JSON.parse(before)
  const provider = config.providers?.WestlakeHPC
  if (!provider) return []
  provider.models ??= {}

  const template = Object.values(provider.models)[0] ?? {}
  const ignored = await ignoredModels()
  const notes = []
  const entries = []
  for (const id of online) {
    if (provider.models[id]) continue
    if (ignored.has(id)) {
      notes.push(`ignored ${id} (listed in .models-ignore)`)
      continue
    }
    if (notChat.test(id)) {
      notes.push(`skipped ${id} (not a chat model)`)
      continue
    }
    entries.push([
      id,
      {
        name: id,
        capabilities: structuredClone(
          template.capabilities ?? {
            tools: true,
            input: ["text", "image"],
            output: ["text"],
          },
        ),
        limit: structuredClone(
          template.limit ?? { context: 1_048_576, output: 393_216 },
        ),
      },
    ])
    notes.push(`added ${id}`)
  }

  const gone = Object.keys(provider.models).filter(
    (id) => !online.includes(id),
  )
  if (gone.length > 0) notes.push(`kept ${gone.join(", ")} (not upstream)`)
  if (entries.length === 0) return notes

  const after = addModels(before, entries)
  if (after === before) return notes

  const tmp = `${configPath}.tmp`
  await writeFile(`${configPath}.bak`, before)
  await writeFile(tmp, after)
  await rename(tmp, configPath)
  return notes
}

export default Plugin.define({
  id: "upkeep",
  async setup(ctx) {
    // Re-check on the first prompt of each calendar day and whenever the
    // session's directory changes (workspace or repository switch); not once
    // per session.
    const seen = new Map<string, { day: string; dir: string }>()

    await ctx.session.hook("prompt", async (event) => {
      try {
        const session = event.sessionID
        const dir = sessionDir(event)
        const day = today()
        const previous = session ? seen.get(session) : undefined
        if (session && previous?.day === day && previous.dir === dir) return
        if (session) seen.set(session, { day, dir })

        const lines = []

        if (!(await modelsCheckedToday())) {
          const notes = await refreshModels()
          await writeFile(modelMarker, `${today()}\n`)
          if (notes.length > 0) {
            lines.push(`Westlake model list refreshed: ${notes.join("; ")}.`)
          }
        }

        if (await upkeepDue()) {
          lines.push(
            "The daily OpenCode / HPC upkeep is due: load the `opencode-hpc-update` skill, finish the OpenCode half, then stamp the day with `update-due.sh --mark`.",
          )
        }

        // Unconditional: the guides are part of every task, not a follow-up.
        lines.push(
          "If this task changes a convention, a command, a dependency, or the layout, update `AGENTS.md` and the skill in the same task; `guides-due.sh` is the gate.",
        )

        if (await guidesDue(dir)) {
          lines.push(
            `Guides STALE/MISSING in ${dir}: update AGENTS.md and the skill as part of this task (guides-due.sh --committed).`,
          )
        }

        const check = await sessionCheck(dir)
        if (check) {
          lines.push(
            `Repository session check: ${check} (declared in AGENTS.md; run it as part of this task).`,
          )
        }

        if (await backupsPending()) {
          lines.push(
            "The post-rewrite rollback bundles are still present in Dou_Group/admin/backups. Once the repositories are confirmed fine, ask the user whether to delete them; never delete without their agreement.",
          )
        }

        if (lines.length > 0 && session) {
          await ctx.session.instructions.entry.put({
            sessionID: session,
            key: "upkeep",
            value: lines.join(" "),
          })
        }
      } catch (error) {
        console.error("[upkeep]", error)
      }
    })
  },
})
