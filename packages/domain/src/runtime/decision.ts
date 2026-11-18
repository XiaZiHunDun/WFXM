/**
 * ModelDecision ADT — DESIGN §6.2 unification layer between model protocols and
 * the Application layer (DESIGN §6 Application). The model can only propose one of
 * these Decisions; the model cannot sign grants, access credentials/filesystem/channel,
 * or bypass the Policy Gate.
 *
 * Tags + field names match DESIGN §6.2 verbatim:
 *   Respond(content)
 *   CallCapability(name, arguments, callId)
 *   StartChildRun(role, objective, grants)
 *   WaitForApproval(question)            // design permits actionRequest; we use
 *                                        // the question form until LLM fills a full
 *                                        // ActionRequest (subject/capability/digest)
 *   Finish(reason)
 *
 * The decoder lives in `@butler/runtime/src/decision.ts` and parses LLM JSON shapes
 * into this ADT.
 */
export type ModelDecision =
  | { readonly _tag: "Respond"; readonly content: string }
  | {
      readonly _tag: "CallCapability"
      readonly name: string
      /** Mirrors DESIGN §6.2 field name; ESLint/false-positive tolerant for object keys. */
      readonly arguments: Readonly<Record<string, unknown>>
      readonly callId?: string
    }
  | {
      readonly _tag: "StartChildRun"
      readonly role: string
      readonly objective: string
      readonly grants?: readonly string[]
    }
  | { readonly _tag: "WaitForApproval"; readonly question: string }
  | { readonly _tag: "Finish"; readonly reason: string }

export type ModelDecisionTag = ModelDecision["_tag"]

export type DecodeResult =
  | { readonly ok: true; readonly value: ModelDecision }
  | { readonly ok: false; readonly reason: string }
