# 进度验证规则

> **目的**：确保workflow_state.json与实际情况一致，防止虚假进度

---

## 一、核心原则

> **状态文件是唯一真相来源，但必须可验证**

```python
# 验证公式
真实完成 = 有审核报告文件 AND 问题已修复（如需要）
```

---

## 二、验证检查点

### 2.1 审核报告存在性检查

```bash
# 检查批次的审核报告是否存在
for batch in ["ch001-ch010", "ch011-ch020", ...]:
    report_file = f"06_意见仓库/04_正文_审核/{batch}_审核.md"
    if not exists(report_file):
        raise Error(f"批次{batch}标记为完成但无审核报告")
```

### 2.2 问题修复验证

对于状态为"需修改"的批次：

```bash
# 伪代码
for issue in report.issues:
    if issue.status == "需修改":
        source_file = f"03_内容仓库/04_正文/{issue.chapter}.md"
        # 读取源文件，验证问题已修复
        content = read(source_file)
        if issue.type == "重复内容":
            # 验证重复段落已删除/精简
        elif issue.type == "逻辑矛盾":
            # 验证矛盾已解决
```

---

## 三、异常处理

### 3.1 发现虚假进度

```
情况：state文件标记完成但无审核报告

处理：
1. 降级该批次至pending
2. 记录问题：虚假进度
3. 启动正式审核
```

### 3.2 发现未修复问题

```
情况：批次状态为"通过"但审核报告中有P0问题未修复

处理：
1. 重新标记为"待修复"
2. 启动修复流程
3. 完成后重新审核
```

---

## 四、进度更新流程

### 正确流程

```
1. 完成审核批次
   └── 生成审核报告

2. 验收报告文件
   └── 确认文件存在且内容有效

3. 处理问题（如有）
   └── 修复 → 验证 → 更新issues_found

4. 更新state文件
   └── 添加至completed列表
   └── 更新issues_found
```

### 禁止流程

```
❌ 直接更新state文件，不生成审核报告
❌ 标记批次完成，不验证修复
❌ 批量"无问题通过"，不生成报告
```

---

## 五、自动化验证脚本

可执行脚本：[`../scripts/validate_progress.py`](../scripts/validate_progress.py)

```bash
cd projects/LingWen1/novel-factory
python3 scripts/validate_progress.py
```

检查项：

1. `workflow_state.json` 的 `review_queue.completed` 与审核报告目录是否一致（抽样匹配章节范围）
2. `06_意见仓库/04_正文_审核/*_审核.md` 是否含未闭合 **P0** / **待修复** 标记（启发式，需人工复核边界案例）

---

## 六、会话交接验证

每次会话结束时，执行以下检查：

```bash
#!/bin/bash
# 验证脚本

REVIEW_DIR="/path/to/06_意见仓库/04_正文_审核"
STATE_FILE="/path/to/workflow_state.json"

echo "=== 进度验证 ==="

# 1. 检查审核报告数量
report_count=$(ls ${REVIEW_DIR}/*_审核.md 2>/dev/null | wc -l)
echo "审核报告数量: $report_count"

# 2. 抽样验证修复（随机抽取10%）
echo "抽样验证修复..."

# 3. 检查state文件一致性
echo "检查state文件..."

echo "=== 验证完成 ==="
```

---

**版本**：v1.0
**创建日期**：2026-05-14
