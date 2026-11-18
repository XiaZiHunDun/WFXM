#!/usr/bin/env node
/**
 * Smoke: Owner document ingest CRUD + promote-memory (loopback).
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
const marker = `smoke-doc-${Date.now()}`
const title = `Smoke ${marker}`

function fail(step, detail) {
  console.error(`smoke FAIL [${step}]: ${detail}`)
  process.exit(1)
}

async function main() {
  const health = await fetch(`${base}/healthz`)
  if (!health.ok) fail("healthz", `${health.status}`)
  console.log("smoke ok [healthz]")

  const create = await fetch(`${base}/v1/owner/documents`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      subject,
      title,
      format: "markdown",
      text: `# ${marker}\n\nkeyword-for-recall: ${marker}`,
    }),
  })
  const createText = await create.text()
  if (!create.ok) fail("documents/create", `${create.status} ${createText}`)
  const created = JSON.parse(createText)
  const documentId = created.item?.id
  if (!documentId) fail("documents/create", createText)

  const list = await fetch(`${base}/v1/owner/documents?subject=${encodeURIComponent(subject)}`)
  const listText = await list.text()
  if (!list.ok) fail("documents/list", `${list.status} ${listText}`)
  const listed = JSON.parse(listText)
  const hit = (listed.items ?? []).find((d) => d.title === title || d.id === documentId)
  if (!hit) fail("documents/list", `document not found in ${listText}`)

  const get = await fetch(`${base}/v1/owner/documents/${documentId}`)
  const getText = await get.text()
  if (!get.ok) fail("documents/get", `${get.status} ${getText}`)
  const got = JSON.parse(getText)
  if (!got.item?.extractedText?.includes(marker)) {
    fail("documents/get", `marker missing in extractedText`)
  }

  const promote = await fetch(`${base}/v1/owner/documents/${documentId}/promote-memory`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ status: "confirmed" }),
  })
  const promoteText = await promote.text()
  if (!promote.ok) fail("documents/promote-memory", `${promote.status} ${promoteText}`)
  const promoted = JSON.parse(promoteText)
  if (!promoted.item?.id) fail("documents/promote-memory", promoteText)

  const delMem = await fetch(`${base}/v1/owner/memories/${promoted.item.id}`, {
    method: "DELETE",
  })
  if (!delMem.ok) fail("memories/delete", `${delMem.status} ${await delMem.text()}`)

  const del = await fetch(`${base}/v1/owner/documents/${documentId}`, { method: "DELETE" })
  if (!del.ok) fail("documents/delete", `${del.status} ${await del.text()}`)

  console.log(`smoke ok [document-ingest]: create/list/get/promote/delete for subject=${subject}`)
  console.log("smoke PASS")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
