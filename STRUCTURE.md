# 仓库目录结构

> Butler v4：**仅微信**消息网关。Hermes 对照源码在本地 `reference/hermes-agent/`（gitignore，不进仓库）。  
> **`reference/` 为只读对照，请勿移动或修改。**

```
WFXM/
├── butler/                 # ★ Butler v4 产品
│   ├── gateway/platforms/  #   微信 iLink（wechat_ilink.py）
│   └── main.py             #   `butler` 入口
├── docs/  tests/  projects/
└── pyproject.toml          # 仅 butler-system
```

## 常用命令

```bash
pip install -e ".[wechat]"
butler chat
butler gateway              # 仅微信 iLink
```

文档：[`docs/README.md`](docs/README.md) · 架构：[`docs/architecture/v4-architecture.md`](docs/architecture/v4-architecture.md)
