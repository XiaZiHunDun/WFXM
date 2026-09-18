/**
 * D72 T3 (audit #18 SEC-002): opaque `Secret<T>` wrapper.
 *
 * Wraps sensitive values (bot tokens, refresh tokens, signing secrets)
 * so accidental logging / JSON serialization leaks become obvious.
 * Production: `console.log(secret)` prints `[REDACTED]` instead of the
 * cleartext value. The only legitimate consumption path is `unwrap()`,
 * which is intentionally verbose at call sites so reviewers notice
 * secret access in code review.
 *
 * The constructor is private (callers go through `Secret.create`) so a
 * future audit can grep for `Secret.create` and `Secret.unwrap` to find
 * every site that produces / consumes secrets. A type system alone
 * cannot prevent `JSON.stringify(secret)` because the `toJSON` method
 * is opt-in (default behavior returns the wrapper object).
 */
export class Secret<T extends string> {
  readonly #value: T
  readonly #brand = "Secret" as const

  private constructor(value: T) {
    this.#value = value
  }

  /**
   * Wrap a cleartext value in a `Secret<T>`. Use at the source of the
   * secret (e.g. when parsing an API response that contains a token).
   */
  static create<T extends string>(value: T): Secret<T> {
    return new Secret(value)
  }

  /**
   * Reveal the wrapped value. Use only at legitimate consumption
   * points (header construction, env file write). Every call should
   * be reviewed for: (a) is the value going to a trusted destination?
   * (b) is the call site free of logging that could leak?
   */
  unwrap(): T {
    return this.#value
  }

  /**
   * Defensive toString — prevents accidental leakage via
   * template literals / console.log / error messages. Returns
   * `[REDACTED]` instead of the cleartext value.
   */
  toString(): string {
    return "[REDACTED]"
  }

  /**
   * Defensive JSON.stringify — returns an object that signals the
   * wrapper rather than the value. Forces `unwrap()` for any code
   * path that actually needs the cleartext.
   */
  toJSON(): { readonly __secret__: true } {
    return { __secret__: true }
  }
}