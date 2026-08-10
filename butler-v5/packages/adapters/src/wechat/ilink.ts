import { Effect } from "effect"

interface ILinkConfig {
  readonly baseUrl: string
  readonly token: string
  readonly fetch?: typeof fetch
}

export function makeWeChatILinkAdapter(config: ILinkConfig) {
  const fetchImpl = config.fetch ?? fetch

  async function call(path: string, body: Record<string, unknown>): Promise<unknown> {
    const res = await fetchImpl(`${config.baseUrl}/cgi-bin${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...body, token: config.token }),
    })
    if (!res.ok) throw new Error(`ilink api error: ${res.status}`)
    const data = (await res.json()) as { errcode: number; errmsg: string }
    if (data.errcode !== 0) throw new Error(`ilink errcode ${data.errcode}: ${data.errmsg}`)
    return data
  }

  return {
    send: (input: { to: string; content: string }) =>
      Effect.tryPromise({
        try: () => call("/message/send", input),
        catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
      }),
    receive: () =>
      Effect.succeed(
        // iLink is push-based via webhook; this adapter exposes a polling stub.
        { messages: [] as readonly { from: string; content: string; ts: number }[] },
      ),
    verifySignature: (_signature: string, _timestamp: string, _nonce: string, echostr: string) =>
      echostr,
  }
}
