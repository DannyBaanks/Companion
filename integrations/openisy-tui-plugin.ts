import { appendFile } from "node:fs/promises"
import path from "node:path"
import type { TuiPlugin } from "@opencode-ai/plugin/tui"

type EventPayload = {
  version: "companion-event-v1"
  id: string
  agent: "openisy"
  created_at: string
  type: "say" | "state"
  value?: "working" | "waiting" | "success" | "error"
  text?: string
  ttl?: number
  priority?: number
}

export const CompanionTuiPlugin: TuiPlugin = async (api, options) => {
  const root = typeof options?.root === "string" ? options.root : process.env.COMPANION_ROOT ?? path.join(process.cwd(), ".companion")
  const inbox = path.join(root, "inbox.jsonl")
  const publish = (id: string, type: EventPayload["type"], fields: Pick<EventPayload, "value" | "text" | "priority">) => {
    const payload: EventPayload = {
      version: "companion-event-v1",
      id: `openisy-${id}`,
      agent: "openisy",
      created_at: new Date().toISOString(),
      type,
      ...fields,
      ttl: fields.text ? 8 : undefined,
    }
    appendFile(inbox, JSON.stringify(payload) + "\n", "utf8").catch(() => {})
  }

  api.event.on("session.idle", (incoming) => {
    publish(incoming.properties.sessionID, "state", { value: "success" })
    publish(incoming.properties.sessionID, "say", { text: "OpenISy terminó la sesión" })
  })
  api.event.on("session.error", (incoming) => {
    publish(incoming.id, "state", { value: "error", priority: 10 })
    publish(incoming.id, "say", { text: "OpenISy encontró un error", priority: 10 })
  })
  api.event.on("question.asked", (incoming) => {
    publish(incoming.properties.sessionID, "state", { value: "waiting" })
    publish(incoming.properties.sessionID, "say", { text: "OpenISy necesita tu atención", priority: 5 })
  })
}

export default CompanionTuiPlugin
