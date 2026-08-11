#!/usr/bin/env node
import { Command } from "commander"
import { serve } from "@hono/node-server"

const program = new Command()

program.name("butler").description("Butler v5 CLI").version("0.0.1")

program
  .command("start")
  .description("Start the v5 wiring (server)")
  .action(async () => {
    const { default: app } = await import("@butler/api")
    const port = Number(process.env["PORT"] ?? 3000)
    const server = serve({ fetch: app.fetch, port }, () => {
      console.log(`v5 wiring listening on :${port}`)
    })
    process.on("SIGINT", () => server.close(() => process.exit(0)))
    process.on("SIGTERM", () => server.close(() => process.exit(0)))
  })

program
  .command("verify")
  .description("Verify v5 wiring (placeholder)")
  .action(() => {
    console.log("v5 verify: stub (R7.3)")
  })

program.parseAsync(process.argv).catch((err) => {
  console.error(err)
  process.exit(1)
})
