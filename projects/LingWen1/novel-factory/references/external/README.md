# 外部参考书归档（Owner 自备）

> **用途**：竞品 PDF、行业报告、平台规则等**外部**素材。  
> **版权**：仅放有权使用的文件；Butler 只读 ingest，不对外分发。

## 推荐文件名

```
external/
  竞品-<书名>-拆书笔记.pdf
  平台-<站点名>-连载规范-2026.pdf
  题材-废土修真-市场简报.pdf
```

## 入库

```bash
# 放入 PDF 后
bash scripts/butler-ingest-pilot.sh
butler memory search "竞品付费点" --scope project --project 灵文1号
```

产物：`.butler/ingest/<原名>.md`（自动 chunk 进语义索引）

## 勿放

- 未脱敏合同、身份证、私信截图
- 无授权的全本盗版 TXT/PDF
- 与《星陨纪元》正史冲突的「同人定稿」（应放 experimental 并标注）
