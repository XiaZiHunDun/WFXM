import type { ILinkResult } from "./ilink-protocol.js"
import { createCipheriv, createDecipheriv } from "node:crypto"

export function pkcs7Pad(data: Buffer, blockSize = 16): Buffer {
  const padLen = blockSize - (data.length % blockSize)
  return Buffer.concat([data, Buffer.alloc(padLen, padLen)])
}

export function pkcs7Unpad(padded: Buffer): Buffer {
  if (padded.length === 0) return padded
  const padLen = padded[padded.length - 1]
  if (padLen === undefined || padLen < 1 || padLen > 16) return padded
  const suffix = padded.subarray(padded.length - padLen)
  if (!suffix.every((b) => b === padLen)) return padded
  return padded.subarray(0, padded.length - padLen)
}

export function parseAesKey(aesKeyB64: string): ILinkResult<Buffer> {
  const trimmed = aesKeyB64.trim()
  if (!trimmed) return { ok: false, reason: "aes key is empty" }
  let decoded: Buffer
  try {
    decoded = Buffer.from(trimmed, "base64")
  } catch {
    return { ok: false, reason: "aes key is not valid base64" }
  }
  if (decoded.length === 16) return { ok: true, value: decoded }
  if (decoded.length === 32) {
    const text = decoded.toString("ascii")
    if (/^[0-9a-fA-F]{32}$/.test(text)) {
      return { ok: true, value: Buffer.from(text, "hex") }
    }
  }
  return { ok: false, reason: `unexpected aes_key format (${decoded.length} decoded bytes)` }
}

/** PKCS7 padded length used by iLink getuploadurl `filesize`. */
export function aesPaddedSize(byteLength: number): number {
  return Math.floor((byteLength + 16) / 16) * 16
}

/** iLink send item `aes_key`: base64(ascii hex of the 16-byte key). */
export function aesKeyForApi(aesKey: Buffer): string {
  return Buffer.from(aesKey.toString("hex"), "ascii").toString("base64")
}

export function aes128EcbEncrypt(plain: Buffer, key: Buffer): ILinkResult<Buffer> {
  if (key.length !== 16) return { ok: false, reason: "aes key must be 16 bytes" }
  try {
    const cipher = createCipheriv("aes-128-ecb", key, null)
    cipher.setAutoPadding(false)
    return { ok: true, value: Buffer.concat([cipher.update(pkcs7Pad(plain)), cipher.final()]) }
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  }
}

export function aes128EcbDecrypt(ciphertext: Buffer, key: Buffer): Buffer {
  try {
    const decipher = createDecipheriv("aes-128-ecb", key, null)
    decipher.setAutoPadding(false)
    const padded = Buffer.concat([decipher.update(ciphertext), decipher.final()])
    return pkcs7Unpad(padded)
  } catch {
    return ciphertext
  }
}
