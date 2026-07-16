# 知识导入目录

## 概述

本目录用于存放你收集的知识文件。系统会自动扫描、分类和消化这些知识，将其转化为结构化的经验。

## 目录结构

```
knowledge_import/
├── user_uploads/          # 用户收集的知识文件（统一投放区）
│   ├── file1.md           # 直接放入即可，系统自动分类
│   ├── file2.txt
│   └── file3.py
├── ai_collected/          # AI收集的知识文件（按领域分类）
│   ├── agent_dev/         # Agent开发
│   ├── database/          # 数据库
│   └── ...
├── processed/             # 已消化的文件（自动归档，请勿手动修改）
│   ├── agent_dev/
│   ├── database/
│   └── unclassified/
└── README.md
```

## 核心特性

### 1. 用户知识统一投放

**你只需将文件放入 `user_uploads/` 目录即可**，系统会：
- 自动识别文件内容所属领域
- 自动分类到对应的领域
- 消化完成后移动到 `processed/` 目录

### 2. 自动领域识别

支持的领域：
- `agent_dev` - Agent开发
- `database` - 数据库
- `llm_usage` - 大模型使用
- `dev_ops` - 开发运维
- `security` - 安全防护
- `code_engineering` - 代码工程
- `project_mgmt` - 项目管理
- `data_science` - 数据科学
- `troubleshooting` - 故障定位
- `daily_life` - 日常生活
- `math_reasoning` - 数学推导
- `network_info` - 网络信息
- `system_admin` - 系统管理

### 3. 知识来源标记

- **user_collected**：你收集的知识
- **ai_collected**：AI收集的知识

系统会在元数据中记录知识来源，便于追溯和管理。

### 4. 已消化/未消化区分

- **user_uploads/**：未消化的用户文件
- **processed/**：已消化的文件（按领域归档）

## 支持的文件格式

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| Markdown | `.md` | 推荐格式，支持标题、列表、代码块 |
| 纯文本 | `.txt` | 普通文本文件 |
| Python代码 | `.py` | Python代码文件 |
| JSON | `.json` | 结构化知识数据 |
| CSV | `.csv` | 表格数据 |
| YAML | `.yml`, `.yaml` | 配置文件 |
| HTML | `.html` | 网页内容 |

## 使用方法

### 导入知识

```bash
cd /home/ailearn/projects/WFXM
python -m butler.memory.knowledge_warehouse.rebuild_all
```

### 仅导入用户上传的文件

```bash
cd /home/ailearn/projects/WFXM
python -c "
from butler.memory.knowledge_warehouse.ingestor import MaterialIngestor
from butler.memory.knowledge_warehouse.digestion import DigestionPipeline

ingestor = MaterialIngestor()
ingestor.batch_import_directory('knowledge_import/user_uploads/', source='user_collected')

pipeline = DigestionPipeline()
pipeline.process_all()
"
```

### 添加知识文件

**简单方式**：
```bash
# 直接复制文件到 user_uploads 目录
cp /path/to/your/knowledge.md /home/ailearn/projects/WFXM/knowledge_import/user_uploads/
```

## 文件命名建议

- 使用英文或中文文件名
- 不要使用特殊字符（如 `*`, `?`, `:`）
- 文件名不要超过100字符
- 每个文件专注一个主题
- 文件大小建议不超过5MB

## 示例

### 添加一篇关于Docker的文章

```bash
# 1. 将文件放入 user_uploads
cp docker-best-practices.md knowledge_import/user_uploads/

# 2. 运行导入
python -m butler.memory.knowledge_warehouse.rebuild_all
```

### 添加一段代码示例

```bash
# 1. 将代码文件放入 user_uploads
cp my_algorithm.py knowledge_import/user_uploads/

# 2. 运行导入
python -m butler.memory.knowledge_warehouse.rebuild_all
```

## 工作流程

```
用户放入文件 → user_uploads/ → 系统扫描 → 自动领域识别 → 入库排队
                                                               ↓
                                                          消化处理
                                                               ↓
                                                      processed/{domain}/
```

## 注意事项

1. **不要手动修改 `processed/` 目录**，这是系统自动归档的
2. 如果文件已经存在，系统会自动跳过（去重）
3. 如果领域识别不准确，可以在文件名中包含领域关键词
4. 支持子目录，系统会递归扫描

## 查看统计信息

```bash
python -c "
from butler.memory.knowledge_warehouse.warehouse import KnowledgeWarehouse

warehouse = KnowledgeWarehouse()
stats = warehouse.get_stats()
print('总材料数:', stats['total_materials'])
print('状态分布:', stats['status_counts'])
print('领域分布:', stats['domain_counts'])
"
```