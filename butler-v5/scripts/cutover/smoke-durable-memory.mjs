#!/usr/bin/env node
/**
 * Smoke: Owner durable memory CRUD (loopback).
 * Injection requires BUTLER_V5_DURABLE_MEMORY=1 on the gateway process.
 */
const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) {
  api = apiEq.slice("--api=".length)
} else {
  const idx = process.argv.indexOf("--api")
  if (idx >= 0 && process.argv[idx + 1]) api = process.argv[idx + 1]
}

const base = api.replace(/\/$/, "")
const subject = "owner"
const marker = `smoke-memory-${Date.now()}`

function fail(step, detail) {
  console.error(`smoke FAIL [${step}]: ${detail}`)
  process.exit(1)
}

async function main() {
  const health = await fetch(`${base}/healthz`)
  if (!health.ok) fail("healthz", `${health.status}`)
  console.log("smoke ok [healthz]")

  const create = await fetch(`${base}/v1/owner/memories`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      subject,
      content: marker,
      sourceKind: "owner",
    }),
  })
  const createText = await create.text()
  if (!create.ok) fail("memories/create", `${create.status} ${createText}`)
  const created = JSON.parse(createText)
  const memoryId = created.item?.id
  if (!memoryId) fail("memories/create", createText)

  const list = await fetch(`${base}/v1/owner/memories?subject=${encodeURIComponent(subject)}`)
  const listText = await list.text()
  if (!list.ok) fail("memories/list", `${list.status} ${listText}`)
  const listed = JSON.parse(listText)
  const hit = (listed.items ?? []).find((m) => m.content === marker || m.content?.includes?.(marker))
  if (!hit) fail("memories/list", `marker not found in ${listText}`)

  const del = await fetch(`${base}/v1/owner/memories/${memoryId}`, { method: "DELETE" })
  if (!del.ok) fail("memories/delete", `${del.status} ${await del.text()}`)

  console.log(`smoke ok [durable-memory]: create/list/delete for subject=${subject}`)
  console.log("smoke PASS")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
