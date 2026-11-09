import { Plugin } from "@opencode/plugin"
import { appendFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { violation, roots } from "./guard.js"

// Plan and Explore may run commands, but their writes belong in the temporary
// tree: the edit tool is path-scoped, the shell is not, so this hook rejects a
// command that would write into a project.  A heuristic, deliberately: it
// understands the common write forms (`>`, `tee`, `sed -i`, `rm/mv/cp`,
// `git add|commit|push|…`, `l3build`, a Python write) and lets everything else
// through.
const TEMP = join(tmpdir(), "opencode")
const ROOTS = roots(TEMP)
const DEBUG = join(TEMP, "shell-guard.log")

const note = async (line: string) => {
  try {
    await appendFile(DEBUG, `${new Date().toISOString()} ${line}\n`)
  } catch {}
}

const commandOf = (event: any) =>
  event?.args?.command ?? event?.input?.command ?? event?.command ?? ""

export default Plugin.define({
  id: "shell-guard",
  async setup(ctx) {
    const session = (ctx as any).session
    await note(`setup: session.get=${typeof session?.get} tool=${typeof (ctx as any).tool}`)

    await (ctx as any).tool.hook("execute.before", async (event: any) => {
      try {
        const tool = event?.tool
        const command = commandOf(event)
        const sessionID = event?.sessionID ?? event?.session?.id ?? event?.id

        await note(
          `call: keys=${Object.keys(event ?? {}).join(",")} tool=${tool} ` +
            `id=${sessionID} cmd=${JSON.stringify(command).slice(0, 120)}`,
        )

        if (tool !== "shell" && tool !== "bash") return
        if (!command) return

        const id = sessionID
        const info = id && typeof session?.get === "function" ? await session.get({ sessionID: id }) : undefined
        const agent = info?.agent ?? info?.info?.agent
        const directory = info?.directory ?? info?.info?.directory ?? process.cwd()
        if (agent !== "plan" && agent !== "explore") return

        const reason = violation(command, directory, ROOTS)
        if (!reason) return
        throw new Error(
          `${agent} may not modify files in ${directory}: ${reason}. ` +
            `Run it against a copy under ${TEMP} (or ${tmpdir()}), or switch to build.`,
        )
      } catch (error) {
        if (error instanceof Error && error.message.includes("may not modify files")) throw error
        await note(`error: ${String(error)}`)
      }
    })
  },
})
