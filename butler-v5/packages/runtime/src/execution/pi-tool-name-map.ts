/**
 * P4.1 eval normalization: pi-native tool names -> existing capability names.
 *
 * Only names are mapped. Argument shapes stay pi-native; assertions that depend
 * on e.g. `run_command.argv` are reported honestly rather than rewritten.
 */
export const PI_TO_BUTLER_TOOL_NAMES: Readonly<Record<string, string>> = {
  read: "read_file",
  write: "write_file",
  edit: "write_file",
  bash: "run_command",
  grep: "run_command",
  find: "run_command",
  ls: "run_command",
}

export function normalizePiToolName(name: string): string {
  return PI_TO_BUTLER_TOOL_NAMES[name] ?? name
}
