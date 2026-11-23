/**
 * Reminder time parsing / formatting. Reminders always use Asia/Shanghai
 * (UTC+8, no DST), matching the rest of the butler surface.
 */
import type { ReminderRepeat } from "@butler/persistence"

const SHANGHAI_OFFSET_MS = 8 * 60 * 60 * 1000
const DAY_MS = 24 * 60 * 60 * 1000
const WEEK_MS = 7 * DAY_MS

const WEEKDAY_LABELS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"] as const

const LOCAL_PATTERN = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/
const ISO_WITH_ZONE_PATTERN =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?(?:Z|[+-]\d{2}:\d{2})$/

export type ReminderTimeParseResult =
  { readonly ok: true; readonly fireAtMs: number } | { readonly ok: false; readonly reason: string }

interface ShanghaiParts {
  readonly year: number
  readonly month: number
  readonly day: number
  readonly hour: number
  readonly minute: number
  readonly second: number
  readonly weekday: number
}

function shanghaiParts(ms: number): ShanghaiParts {
  const shifted = new Date(ms + SHANGHAI_OFFSET_MS)
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth() + 1,
    day: shifted.getUTCDate(),
    hour: shifted.getUTCHours(),
    minute: shifted.getUTCMinutes(),
    second: shifted.getUTCSeconds(),
    weekday: shifted.getUTCDay(),
  }
}

function pad(n: number): string {
  return n.toString().padStart(2, "0")
}

/** `2026-11-24 09:30` in Asia/Shanghai. */
export function formatReminderTime(ms: number): string {
  const p = shanghaiParts(ms)
  return `${p.year}-${pad(p.month)}-${pad(p.day)} ${pad(p.hour)}:${pad(p.minute)}`
}

/** Owner-facing fire description, e.g. `每天 08:00` / `每周一 09:00`. */
export function formatReminderSchedule(ms: number, repeat: ReminderRepeat): string {
  const p = shanghaiParts(ms)
  const time = `${pad(p.hour)}:${pad(p.minute)}`
  if (repeat === "daily") return `每天 ${time}`
  if (repeat === "weekly") return `每${WEEKDAY_LABELS[p.weekday] ?? "周"} ${time}`
  return formatReminderTime(ms)
}

function parseLocalMatch(match: RegExpExecArray): ReminderTimeParseResult {
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const hour = Number(match[4])
  const minute = Number(match[5])
  const second = match[6] === undefined ? 0 : Number(match[6])
  if (month < 1 || month > 12 || day < 1 || day > 31) {
    return { ok: false, reason: "日期不合法，请给出具体时间（如 2026-11-24 09:30）" }
  }
  if (hour > 23 || minute > 59 || second > 59) {
    return { ok: false, reason: "时间不合法，请给出 24 小时制时间（如 09:30）" }
  }
  const utc = Date.UTC(year, month - 1, day, hour, minute, second)
  const check = new Date(utc)
  if (
    check.getUTCFullYear() !== year ||
    check.getUTCMonth() !== month - 1 ||
    check.getUTCDate() !== day ||
    check.getUTCHours() !== hour ||
    check.getUTCMinutes() !== minute ||
    check.getUTCSeconds() !== second
  ) {
    return { ok: false, reason: "日期不合法，请给出真实存在的日期（如 2026-11-24 09:30）" }
  }
  return { ok: true, fireAtMs: utc - SHANGHAI_OFFSET_MS }
}

/**
 * Parses owner/LLM supplied absolute time. Accepts `YYYY-MM-DD HH:mm`
 * (Asia/Shanghai) or a full ISO timestamp with an explicit offset.
 * Past times are rejected for `once` and rolled forward for daily/weekly.
 */
export function parseReminderTime(input: {
  readonly text: string
  readonly repeat: ReminderRepeat
  readonly nowMs: number
}): ReminderTimeParseResult {
  const text = input.text.trim()
  if (!text) {
    return { ok: false, reason: "请给出具体时间（如 2026-11-24 09:30）" }
  }

  let parsed: ReminderTimeParseResult
  const local = LOCAL_PATTERN.exec(text)
  if (local) {
    parsed = parseLocalMatch(local)
  } else if (ISO_WITH_ZONE_PATTERN.test(text)) {
    const ms = Date.parse(text)
    parsed = Number.isFinite(ms)
      ? { ok: true, fireAtMs: ms }
      : { ok: false, reason: "时间格式不正确，请给出具体时间（如 2026-11-24 09:30）" }
  } else {
    return { ok: false, reason: "时间格式不正确，请给出具体时间（如 2026-11-24 09:30）" }
  }
  if (!parsed.ok) return parsed

  let fireAtMs = parsed.fireAtMs
  if (fireAtMs > input.nowMs) return { ok: true, fireAtMs }

  if (input.repeat === "once") {
    return { ok: false, reason: "提醒时间已过去，请给出未来时间" }
  }
  const step = input.repeat === "daily" ? DAY_MS : WEEK_MS
  // Roll forward until strictly in the future; at most a couple of steps.
  for (let i = 0; i < 2 && fireAtMs <= input.nowMs; i += 1) {
    fireAtMs += step
  }
  if (fireAtMs <= input.nowMs) {
    return { ok: false, reason: "提醒时间已过去，请给出未来时间" }
  }
  return { ok: true, fireAtMs }
}

/** Next occurrence for recurring reminders; undefined for `once`. */
export function nextReminderFireAtMs(fireAtMs: number, repeat: ReminderRepeat): number | undefined {
  if (repeat === "daily") return fireAtMs + DAY_MS
  if (repeat === "weekly") return fireAtMs + WEEK_MS
  return undefined
}
