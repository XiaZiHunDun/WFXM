import { execFileSync } from "node:child_process"

export interface P2dPreflightCheck {
  readonly name: string
  readonly ok: boolean
  readonly detail: string
}

export interface P2dPreflightResult {
  readonly ok: boolean
  readonly readyForSpike: boolean
  readonly checks: readonly P2dPreflightCheck[]
  readonly note: string
}

function commandExists(name: string, args: readonly string[] = ["--version"]): P2dPreflightCheck {
  try {
    const out = execFileSync(name, [...args], {
      encoding: "utf8",
      timeout: 5000,
      env: { PATH: process.env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin" },
    })
    const detail = out.trim().split("\n")[0]?.trim() || "ok"
    return { name, ok: true, detail }
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err)
    return { name, ok: false, detail }
  }
}

function hasCapNetAdmin(): P2dPreflightCheck {
  try {
    const out = execFileSync("capsh", ["--print"], { encoding: "utf8", timeout: 3000 })
    const ok = out.includes("cap_net_admin")
    return {
      name: "cap_net_admin",
      ok,
      detail: ok ? "present in bounding set" : "missing (P2d iptables may need root or file caps)",
    }
  } catch {
    return {
      name: "cap_net_admin",
      ok: process.getuid?.() === 0,
      detail: process.getuid?.() === 0 ? "running as root" : "capsh unavailable; not root",
    }
  }
}

/** Host readiness for P2d slirp+iptables spike (does not configure netns). */
export function preflightP2dSlirpEgress(): P2dPreflightResult {
  const checks: P2dPreflightCheck[] = [
    commandExists("bwrap", ["--version"]),
    commandExists("slirp4netns", ["--version"]),
    commandExists("unshare", ["--version"]),
    commandExists("iptables", ["--version"]),
    hasCapNetAdmin(),
  ]
  const ok = checks.every((c) => c.ok)
  const readyForSpike = checks.filter((c) => c.name !== "cap_net_admin").every((c) => c.ok)
  return {
    ok,
    readyForSpike,
    checks,
    note: ok
      ? "Host has P2d tooling; proceed with isolated netns + slirp spike."
      : readyForSpike
        ? "Binaries present; cap_net_admin may require file caps on node or dedicated operator step."
        : "Install slirp4netns/bwrap/iptables before P2d implementation.",
  }
}
