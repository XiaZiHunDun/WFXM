# v5 跟进立项（2026-08-20）

> 裁决见 [`v5-followons-2026-08-20.md`](../decisions/v5-followons-2026-08-20.md)。  
> 建议顺序：**~~R8.x.22~~（done） → ~~R8.x.21~~（done） → ~~R8.x.20~~（done）。

---

## R8.x.22 — 入站语音转写（**done 2026-08-20**）

有 `voice_item.text` 则 inbound 用该转写、不下载体。无 text 时下载 silk 后走可注入的 `transcribeVoice`；默认 DashScope 拒绝 silk（未捆绑解码器），失败保留「已保存到 path」。

---

## R8.x.21 — 出站发图 / 发文件（**done 2026-08-20**）

**问题**：管家回复只有 `sendmessage` 文本。手机上看不到本机缓存路径，也无法把生成的图发回微信。

工具 `send_wechat_file`：仅工作区内路径；getuploadurl + AES-128-ECB + CDN POST（host 白名单）+ `item_list` type=2/4。mock fetch 测 jpeg/txt；越界拒绝。不进 `ALLOWED_CAPABILITIES`（子代理不能发）。上传超时 120s。

**不做**：出站视频、朋友圈、群发。

---

## R8.x.20 — `run_command` 具名扩容（**done 2026-08-20**）

白名单追加 `rg`/`grep`、`python3`、`pnpm`、`node`。仍无 shell：argv[0] 精确匹配；参数不得以 `/` 开头、不得含 `..`。`bash`/`rm`/`curl` 等仍拒绝。原 8 个命令保留。

---

## 不立项

嵌套 `tests/architecture/r{2,3,4,5,6}-end-to-end.test.ts`：已排除出默认 vitest，关闭。
