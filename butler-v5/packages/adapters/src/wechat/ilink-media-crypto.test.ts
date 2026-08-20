import { createCipheriv } from "node:crypto"
import { describe, expect, it } from "vitest"
import { aes128EcbDecrypt, aes128EcbEncrypt, parseAesKey, pkcs7Pad } from "./ilink-media-crypto.js"

function encryptEcb(plain: Buffer, key: Buffer): Buffer {
  const cipher = createCipheriv("aes-128-ecb", key, null)
  cipher.setAutoPadding(false)
  return Buffer.concat([cipher.update(pkcs7Pad(plain)), cipher.final()])
}

describe("ilink media AES-128-ECB", () => {
  it("decrypts PKCS7-padded ciphertext", () => {
    const key = Buffer.from("0123456789abcdef")
    const plain = Buffer.from("cdn-media-plain")
    const cipher = encryptEcb(plain, key)
    expect(aes128EcbDecrypt(cipher, key).toString("utf8")).toBe("cdn-media-plain")
  })

  it("parses 16-byte base64 keys and hex aeskey via base64(hex-bytes)", () => {
    const raw = Buffer.from("0123456789abcdef")
    expect(parseAesKey(raw.toString("base64")).ok).toBe(true)
    const hexWrapped = Buffer.from(raw.toString("hex"), "utf8").toString("base64")
    const parsed = parseAesKey(hexWrapped)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    expect(parsed.value.equals(raw)).toBe(true)
  })

  it("rejects empty keys without throwing", () => {
    const parsed = parseAesKey("")
    expect(parsed.ok).toBe(false)
  })

  it("encrypts PKCS7 then decrypts back to plaintext", () => {
    const key = Buffer.from("0123456789abcdef")
    const plain = Buffer.from("cdn-media-plain")
    const encrypted = aes128EcbEncrypt(plain, key)
    expect(encrypted.ok).toBe(true)
    if (!encrypted.ok) return
    expect(aes128EcbDecrypt(encrypted.value, key).toString("utf8")).toBe("cdn-media-plain")
    expect(encrypted.value.equals(encryptEcb(plain, key))).toBe(true)
  })

  it("rejects a non-16-byte key without throwing", () => {
    const encrypted = aes128EcbEncrypt(Buffer.from("x"), Buffer.from("short"))
    expect(encrypted.ok).toBe(false)
  })
})
