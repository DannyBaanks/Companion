import { appendFile } from "node:fs/promises"
import path from "node:path"
import type { Plugin } from "@opencode-ai/plugin"

type CompanionEvent = {
  version: "companion-event-v1"
  id: string
  agent: string
  created_at: string
  type: "say" | "state"
  value?: "working" | "waiting" | "success" | "error"
  text?: string
  ttl?: number
  priority?: number
}

function event(input: { id: string; type: CompanionEvent["type"]; value?: CompanionEvent["value"]; text?: string; priority?: number }): CompanionEvent {
  return {
    version: "companion-event-v1",
    id: `opencode-${input.id}`,
    agent: "opencode",
    created_at: new Date().toISOString(),
    type: input.type,
    value: input.value,
    text: input.text,
    ttl: input.text ? 8 : undefined,
    priority: input.priority ?? 0,
  }
}

export const CompanionPlugin: Plugin = async (input, options) => {
  const root = typeof options?.root === "string" ? options.root : process.env.COMPANION_ROOT ?? path.join(input.directory, ".companion")
  const inbox = path.join(root, "inbox.jsonl")
  const publish = (payload: Parameters<typeof event>[0]) => {
    appendFile(inbox, JSON.stringify(event(payload)) + "\n", "utf8").catch(() => {})
  }

  return {
    event: async ({ event: incoming }) => {
      if (incoming.type === "session.idle") {
        publish({ id: incoming.properties.sessionID, type: "state", value: "success" })
        publish({ id: incoming.properties.sessionID, type: "say", text: "OpenCode terminó la sesión" })
        return
      }
      if (incoming.type === "session.error") {
        publish({ id: incoming.id, type: "state", value: "error", priority: 10 })
        publish({ id: incoming.id, type: "say", text: "OpenCode encontró un error", priority: 10 })
      }
    },
  }
}

export default CompanionPlugin
