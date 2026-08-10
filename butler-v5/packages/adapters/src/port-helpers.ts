import { Effect } from "effect"

/**
 * Helper for implementing a port's Live layer.
 *
 * Usage:
 *   const liveImpl = makeLiveLayer(LLMService, ({ config }) => ({
 *     complete: (msgs) => Effect.tryPromise(...),
 *     stream:   (msgs) => Stream.fromEffect(...),
 *   }))
 *   export const LLMServiceLive = Layer.effect(LLMService, liveImpl)
 */
export function makeLiveLayer<Tag extends { readonly [k: string]: unknown }, Shape>(
  _tag: Tag,
  factory: (deps: unknown) => Shape,
): (deps: unknown) => Shape {
  return factory
}

/**
 * Wrap a Promise-returning fn so the underlying exception is captured
 * into a tagged failure (no throw).
 */
export function tryPromise<A, E>(
  f: () => Promise<A>,
  onError: (err: unknown) => E,
): Effect.Effect<A, E> {
  return Effect.tryPromise({
    try: f,
    catch: (err) => onError(err),
  })
}
