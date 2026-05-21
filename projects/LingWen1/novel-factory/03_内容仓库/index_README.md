# 内容仓库索引使用指南

## 概述

内容仓库采用分层索引机制，各层目录下的`index.json`文件提供快速检索能力。

## 目录结构

```
03_内容仓库/
├── 01_全文总体大纲/
│   ├── index.json      # 全卷索引
│   └── 全局大纲.md
├── 02_卷大纲/
│   ├── index.json      # 卷索引
│   └── 卷1/
│       ├── index.json  # 卷1内阶段索引
│       └── 卷1大纲.md
├── 03_阶段大纲/
│   ├── index.json      # 阶段索引
│   └── 卷1/阶段1/
│       ├── index.json  # 阶段1内章节索引
│       └── 阶段大纲.md
└── 04_正文/
    ├── index.json      # 全章节索引
    ├── ch001.md
    ├── ch002.md
    └── ...（正文章节文件）
```

## 索引更新

### 自动更新

索引脚本会在以下时机自动更新：
- 作家提交新章节时
- 审核完成时
- 主控调度时

### 手动更新

```bash
cd novel-factory/03_内容仓库

# 更新所有索引
python update_index.py --all

# 更新特定层级
python update_index.py --layer full      # 更新全文大纲索引
python update_index.py --layer volume   # 更新卷大纲索引
python update_index.py --layer stage    # 更新阶段大纲索引
python update_index.py --layer chapter  # 更新正文章节索引
```

## 查询命令

### 查询单个章节
```bash
python update_index.py --query ch001
```
输出：
```
Chapter: ch001
  Word count: 3200
  Last updated: 2026-05-14
```

### 查询章节范围
```bash
python update_index.py --range ch001 ch010
```
输出：
```
Range ch001-ch010: 10 chapters
```

## 版本管理

### 正文文件版本策略
- **原位覆盖**：同一文件直接更新，不保留历史版本
- **历史追踪**：意见仓库（06_意见仓库）记录审核历史
- **状态追踪**：workflow_state.json统一管理状态

### 回溯方式
1. 查看审核记录 → 意见仓库对应章节目录
2. 查看当前状态 → workflow_state.json
3. 不需要从文件系统回溯历史版本

## 文件命名规范

| 类型 | 格式 | 示例 |
|------|------|------|
| 正文 | `ch{编号}.md` | ch001.md |
| 卷大纲 | `卷{n}_{名称}.md` | 卷1_全局大纲.md |
| 阶段大纲 | `卷{n}_阶段{n}_{名称}.md` | 卷1_阶段1_废土星火.md |
| 阶段汇总 | `卷{n}_阶段{n}_汇总.md` | 卷1_阶段1_汇总.md |
| 卷汇总 | `卷{n}_汇总.md` | 卷1_汇总.md |

## 状态说明

章节状态由workflow_state.json管理：

| 状态 | 说明 |
|------|------|
| 草稿 | 作家创作中 |
| 已提交 | 等待审核 |
| 审核中 | 审核部门处理中 |
| 需修改 | 有意见需作家处理 |
| 定稿 | 审核通过，锁定 |

## 索引字段说明

### 正文index.json字段
```json
{
  "updated_at": "2026-05-14 18:00:00",
  "total_chapters": 357,
  "chapters": [
    {
      "chapter": "ch001",
      "filename": "ch001.md",
      "word_count": 3200,
      "char_count": 2800,
      "lines": 150,
      "last_updated": "2026-05-14"
    }
  ]
}
```

### 各层index.json字段
```json
{
  "updated_at": "2026-05-14 18:00:00",
  "total_files": 10,
  "files": [
    {
      "filename": "卷1_阶段1_废土星火.md",
      "last_updated": "2026-05-14"
    }
  ]
}
```