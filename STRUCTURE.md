# 仓库目录结构

> Butler v4：**仅微信**消息网关（`butler gateway`）。`vendor/hermes-agent/` 为冻结对照，产品不接入。  
> **`reference/` 为只读对照，请勿移动或修改。**

```
WFXM/
├── butler/                 # ★ Butler v4 产品
│   ├── gateway/platforms/  #   微信 iLink（wechat_ilink.py）
│   └── main.py             #   `butler` 入口
├── vendor/hermes-agent/    # 冻结 Hermes 快照（非产品路径，不安装）
├── docs/  tests/  projects/
└── pyproject.toml          # 仅打包 butler-system
```

## 常用命令

```bash
pip install -e ".[wechat]"
butler chat
butler gateway              # 仅微信 iLink
```

文档：[`docs/README.md`](docs/README.md) · 架构：[`docs/architecture/v4-architecture.md`](docs/architecture/v4-architecture.md)
