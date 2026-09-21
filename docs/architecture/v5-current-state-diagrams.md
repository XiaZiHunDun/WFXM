# v5 当前状态 — 视觉架构图（D78 新增）

> **生成日期**: 2026-09-21 | **cycle**: D78 T2 | **关系**:
> - 文字版 → [`v5-production-architecture-2026-08.md`](v5-production-architecture-2026-08.md)（权威源）
> - 目标架构 → [`../../butler-v5/DESIGN.md`](../../butler-v5/DESIGN.md)
> - D-series 路线 → [`../ROADMAP.md`](../ROADMAP.md)

本文件仅补**视觉化**层（3 张 Mermaid 图），不复制文字内容。

---

## 图 1: D-series 架构边界（六边形 + D-series §）

```mermaid
graph TB
  subgraph Domain["§5 Domain（纯规则）"]
    D1[Run 状态机]
    D2[Policy 规则]
  end
  subgraph Application["§6 Application（编排）"]
    A1[RunEngine]
    A2[Decision 边界]
  end
  subgraph Ports["§7 Ports（依赖向内）"]
    P1[Persistence Port]
    P2[Model Port]
    P3[Channel Port]
  end
  subgraph Adapter["§7 Adapter（driving/driven）"]
    AD1[Intake Gateway<br/>apps/api]
    AD2[PGlite Adapter<br/>packages/persistence]
    AD3[Channel Adapter<br/>wechat/slack/telegram]
  end
  subgraph Governance["§10 Governance"]
    G1[PolicyGate]
    G2[ScopedGrant]
    G3[Audit Emit]
  end
  subgraph Data["§11 混合数据 + §13 Persistence + §17 Event Sourcing"]
    DT1[Current State<br/>PGlite]
    DT2[Append-only<br/>Event Store]
  end
  subgraph Actor["§18 Cross-actor"]
    AC1[owner-direct]
    AC2[fatigue-agent]
  end
  subgraph EP["§20 KNOWN_ENTRY_POINTS"]
    EP1[LLM Tier]
    EP2[Non-LLM Tier<br/>/health etc]
  end
  Domain --> Application --> Ports --> Adapter
  Application --> Governance
  Adapter --> Data
  Governance --> Actor
  Adapter --> EP
```

**图 1 说明**：D-series §3-§20 段落映射到六边形分层；§20 KNOWN_ENTRY_POINTS 分 LLM/Non-LLM 2-tier（D77 T5 lesson）。

---

## 图 2: butler-v5 数据流（sequenceDiagram）

```mermaid
sequenceDiagram
  autonumber
  participant O as Owner
  participant C as Channel<br/>(Wechat/Slack/Telegram)
  participant I as Intake Gateway<br/>apps/api
  participant R as RunEngine<br/>packages/runtime
  participant P as PolicyGate
  participant G as ScopedGrant
  participant PB as Provider Boundary
  participant A as Audit Emit
  participant DB as Event Store<br/>PGlite
  O->>C: 微信消息 / /命令 / /审批
  C->>I: HTTP POST (apiVersion)
  I->>R: runButlerLoop(conversationId, entry)
  R->>P: 检查副作用策略
  P-->>R: Allow / Ask / Deny
  alt Ask
    R->>A: emit waiting_approval
    A->>DB: append event
    R-->>I: reply「确认？」
    I-->>C: 回复 Owner
    O->>C: 「确认」/「取消」
    C->>I: HTTP POST (decision)
    I->>R: resumeRun(runId, decision)
    R->>G: 申请 ScopedGrant
    G-->>R: granted / denied
  end
  R->>PB: invoke provider
  PB-->>R: result
  R->>A: emit run.completed
  A->>DB: append event
  R-->>I: final reply
  I-->>C: 回复 Owner
  C-->>O: 微信消息
```

**图 2 说明**：真实运行链路（acceptance harness 验证：4 files / 11 pass）；approval 路径走 `ActiveMainRunConflict` 降级（D49 multi-tool chain undo closure）。

---

## 图 3: Owner↔Butler↔Channel 三角

```mermaid
graph LR
  subgraph Owner
    O1[微信 / CLI / API]
  end
  subgraph Butler["Butler v5<br/>(packages/runtime + adapters)"]
    B1[owner-jargon 转换<br/>FAIL-CLOSED]
    B2[RunEngine]
    B3[Audit Emit<br/>actor=owner-direct]
  end
  subgraph Channel
    C1[Wechat]
    C2[Slack]
    C3[Telegram]
  end
  O1 <-->|微信消息 / 审批| C1
  O1 <-->|Slack 消息| C2
  O1 <-->|Telegram 消息| C3
  C1 -->|HTTP POST| B2
  C2 -->|HTTP POST| B2
  C3 -->|HTTP POST| B2
  B2 --> B1
  B1 -->|owner-jargon 文案| O1
  B2 --> B3
  B3 -->|PGlite event_store| DB[(event_store)]
```

**图 3 说明**：三角关系；channel 错误 → FAIL-CLOSED（D63 T4 + D71 T3 Telegram/Slack allowlist）；owner-jargon 文案 → owner（D70/D73 持续治理）。

---

## 图 4: D-series cycle 节奏（bar）

```mermaid
graph LR
  D22[D22<br/>10 ship] --> D38[D38<br/>40 ship]
  D38 --> D54[D54<br/>60 ship]
  D54 --> D68[D68<br/>90 ship]
  D68 --> D75[D75<br/>100 ship]
  D75 --> D77[D77<br/>117 ship]
  D77 --> D78[D78<br/>122 ship<br/>📍]
```

**图 4 说明**：cycle 17→24 累计 100→122 ship；每 cycle 平均 5-7 ship（D77 首次 7-ship；D78 5-ship）。

---

## 跨文件指针

| 主题 | 读这里 |
|------|--------|
| 文字生产架构 | [`v5-production-architecture-2026-08.md`](v5-production-architecture-2026-08.md) |
| 目标架构 §1-§20 | [`../../butler-v5/DESIGN.md`](../../butler-v5/DESIGN.md) |
| §20 KNOWN_ENTRY_POINTS | [`../../butler-v5/DESIGN.md` §20](../../butler-v5/DESIGN.md) |
| D-series 累计 | [`../ROADMAP.md`](../ROADMAP.md) |
| Owner FAQ | [`../FAQ.md`](../FAQ.md) |

---

**End of diagrams** | D78 T2 | 3 + 1 张图（架构边界 + 数据流 + 三角 + cycle 节奏）
