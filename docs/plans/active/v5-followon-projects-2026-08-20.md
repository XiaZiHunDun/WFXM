# v5 跟进立项（2026-08-20）

> 裁决见 [`v5-followons-2026-08-20.md`](../decisions/v5-followons-2026-08-20.md)。  
> 建议顺序：**~~R8.x.22~~（done） → R8.x.21 → R8.x.20**。

---

## R8.x.22 — 入站语音转写（**done 2026-08-20**）

有 `voice_item.text` 则 inbound 用该转写、不下载体。无 text 时下载 silk 后走可注入的 `transcribeVoice`；默认 DashScope 拒绝 silk（未捆绑解码器），失败保留「已保存到 path」。

---

## R8.x.21 — 出站发图 / 发文件

**问题**：管家回复只有 `sendmessage` 文本。手机上看不到本机缓存路径，也无法把生成的图发回微信。

**范围**

1. 对照 v4 `send_phases`：申请 upload URL、AES-128-ECB 加密、CDN PUT、`item_list` type=2/4。
2. 工具或 loop 约定：仅发送 `workspaceRoot` 内文件，大小上限与入站同级。
3. mock CDN + mock iLink，禁止默认打真实上传。

**不做**：出站视频、朋友圈、群发。

**验收**：给定工作区内 jpeg，mock 上传后 `sendmessage` 带 image item；路径越界拒绝。

---

## R8.x.20 — `run_command` 具名扩容

**问题**：白名单过窄，微信里无法跑仓库探查/测试。

**允许加入（仍无 shell，argv[0] 必须精确匹配，参数不得以 `/` 开头、不得含 `..`）**

- `rg`（若无则 `grep`）
- `python3`
- `pnpm`
- `node`

**明确禁止**：`bash`、`sh`、`zsh`、`rm`、`sudo`、`curl`、`wget`、`chmod`、管道与 `shell: true`。

**验收**：新命令在工作区根内可跑；禁名单与越界路径仍 `{ ok: false }`；现有 8 个命令回归。

---

## 不立项

嵌套 `tests/architecture/r{2,3,4,5,6}-end-to-end.test.ts`：已排除出默认 vitest，关闭。
