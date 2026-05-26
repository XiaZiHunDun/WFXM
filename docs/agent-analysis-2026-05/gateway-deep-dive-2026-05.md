# Butler Gateway 深挖报告

## 一句话结论

Butler 的 gateway 主干已经很成熟，尤其是 `message_handler`、`queue mode`、`session registry`、`reply admission`、`outbound bridge` 这一套；真正还值得继续吸收的，主要是默认安全 posture、pairing 子集、busy/pending 的产品体验，而不是把 OpenClaw 或 Hermes 的整个平台搬进来。

## Butler 当前基线

### 已有能力

- `butler/gateway/message_handler.py`  
  已具备完整 ingress 管线：io guardrail、human gate、注入审查、idempotency、queue mode、reply admission、interrupt、sessionless slash

- `butler/gateway/session_registry.py`  
  已具备 per-session loop 池、active 标记、LRU/idle eviction、reset_all 防并发

- `butler/human_gate.py`  
  已支持 workflow_step gate、injection_review gate、approved 持久化、TTL

- `butler/gateway/message_queue.py` + `queue_settings.py`  
  已支持 `followup / collect / interrupt / steer`、cap/drop/summarize、per-session override

- `butler/gateway/outbound_bridge.py` + `reply_admission.py`  
  已支持 typing、progress ack、milestone、supplementary reply、single-flight

- `butler/gateway/platforms/wechat_ilink.py` + `owner_gate.py`  
  微信 adapter 已完整；Owner/allowlist 存在

### 当前主要缺口

- 默认 DM policy 仍是 `open`
- busy 态反馈仍比参考产品更轻
- pending approval 还不像完整状态机
- adapter/runner 双层 guard 与更细的 stale self-heal 仍偏轻

## 默认安全 posture 对比

### OpenClaw

- DM 默认 pairing
- 公开 DM 需显式 `open + allowFrom=*`
- doctor 扫危险配置

### Hermes

- 默认偏 deny
- allowlist / pairing / global allow-all 多层授权
- 更像多用户 bot 平台

### Butler

- 微信 DM 默认 `open`
- group 默认 `disabled`
- Owner/allowlist 保护敏感命令

结论：Butler 微信入口比 OpenClaw 和 Hermes 都更宽松。对单主公自用这不是立即的 bug，但它确实是 gateway 线上最明显、也最容易被忽视的安全差距。

## 参考产品对照

### OpenClaw

- 强项：DM pairing / allowlist、安全审计、reply admission、bot loop protection、多 workspace route
- Butler 已有子集：reply admission、bot loop、queue modes、doctor 子集
- 最值得继续学：pairing 子集、doctor 安全扫描、busy ack、route 元数据

### Hermes

- 强项：双层 guard、SessionStore 生命周期、approval 优先级、busy mode、stream 分段
- Butler 已有子集：iLink 适配、queue/interrupt、Owner gate、outbound bridge
- 最值得继续学：stale self-heal、busy 命令分类、pending gate 优先级

### OpenCode

- 强项：session.status、pending permission、once/always/reject、attach 客户端一致性
- Butler 已有子集：workflow/human gate 的基础能力
- 最值得继续学：状态机与 pending 可见性，不需要学 HTTP serve / Effect 栈

## 优先级判断

### P0

1. 默认安全 posture 收紧  
   把微信 DM 默认从 `open` 拉到 `allowlist`，或至少在现有 preflight warn 之外补齐 CLI doctor 对 open DM、group、allowlist 的强告警。

### P1

2. 可选 pairing 子集  
   仅针对微信引入 pending code + approve，不处理陌生人正文。

3. busy 态反馈增强  
   把 queue mode、pending count、当前 tool / elapsed、是否可 steer/interrupt 呈现给用户。

4. stale lock / split-brain 自愈  
   除了 `reset_all` 卡死恢复外，再补 session active / adapter 状态不一致的自愈检测。

5. pending approval 状态机增强  
   明确 once / always / reject、列出当前 pending、支持更清晰的 gate 元数据。

### P2

6. mid-turn 命令分层  
   把 slash 命令分成控制、只读、审批、拒绝四档，而不是单一 sessionless 列表。

## 不建议引入

- OpenClaw 全通道 plugin-sdk / ingress graph / WS 控制面
- Hermes `GatewayRunner + AIAgent` 整体架构
- Docker/SSH/OpenShell sandbox 与 gateway 深绑定
- edit-message 流式输出体系
- OpenCode 的 serve / SSE / 多 attach 客户端平台化

## 最稳妥的方向

Gateway 线最值得继续学：

1. OpenClaw 的安全默认值和 pairing 子集
2. Hermes 的 stale self-heal 与命令优先级
3. OpenCode 的 pending/approval 状态机

但 Butler 仍应保持微信单网关、自建 loop、无多客户端控制面的产品边界。
