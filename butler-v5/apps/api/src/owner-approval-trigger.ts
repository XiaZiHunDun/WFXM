import {
  buildApiRunTrigger,
  validateRunTrigger,
  type RunTrigger,
} from "@butler/domain/runtime.js"

export function buildOwnerApprovalRunTrigger(input: {
  readonly subject: string
  readonly conversationId: string
  readonly stepId: string
  readonly capability: string
}): RunTrigger {
  return buildApiRunTrigger({
    subject: input.subject,
    conversationId: input.conversationId,
    idempotencyKey: `owner-approve-${input.stepId}`,
    payload: {
      action: "approval.resume",
      stepId: input.stepId,
      capability: input.capability,
    },
  })
}

export function assertOwnerApprovalRunTrigger(
  trigger: RunTrigger,
): { readonly ok: true } | { readonly ok: false; readonly reason: string } {
  return validateRunTrigger(trigger)
}
