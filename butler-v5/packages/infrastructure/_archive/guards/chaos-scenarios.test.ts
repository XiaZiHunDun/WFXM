import { describe, it, expect } from "vitest"
import { chaosScenarios, runChaosDrill } from "./chaos-scenarios.js"

describe("infrastructure/guards/chaos-scenarios", () => {
  it("has 5 scenarios", () => {
    expect(chaosScenarios).toHaveLength(5)
  })

  it("fake-completion scenario is detected by G-1", () => {
    const scenario = chaosScenarios[0]
    if (!scenario) throw new Error("chaosScenarios[0] should be defined")
    expect(scenario.name).toBe("fake-completion")
    const result = runChaosDrill(scenario)
    expect(result.passed).toBe(true)
    expect(result.guard).toBe("G-1")
  })

  it("owner-offline-write scenario is detected by G-3", () => {
    const scenario = chaosScenarios[1]
    if (!scenario) throw new Error("chaosScenarios[1] should be defined")
    expect(scenario.expectedGuard).toBe("G-3")
    const result = runChaosDrill(scenario)
    expect(result.passed).toBe(true)
  })

  it("load-bearing-delete scenario is detected by G-2", () => {
    const scenario = chaosScenarios[2]
    if (!scenario) throw new Error("chaosScenarios[2] should be defined")
    expect(scenario.expectedGuard).toBe("G-2")
    const result = runChaosDrill(scenario)
    expect(result.passed).toBe(true)
  })

  it("role-conflict scenario is detected by G-7", () => {
    const scenario = chaosScenarios[3]
    if (!scenario) throw new Error("chaosScenarios[3] should be defined")
    expect(scenario.expectedGuard).toBe("G-7")
    const result = runChaosDrill(scenario)
    expect(result.passed).toBe(true)
  })

  it("chain-incomplete scenario is detected by G-5", () => {
    const scenario = chaosScenarios[4]
    if (!scenario) throw new Error("chaosScenarios[4] should be defined")
    expect(scenario.expectedGuard).toBe("G-5")
    const result = runChaosDrill(scenario)
    expect(result.passed).toBe(true)
  })
})
