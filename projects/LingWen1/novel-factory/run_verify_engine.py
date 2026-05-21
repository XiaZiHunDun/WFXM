#!/usr/bin/env python3
#===============================================================================
# 灵文 · 修复验证引擎
# 实现 AUDIT_ACCEPTANCE_CRITERIA.md 中定义的验证逻辑
#===============================================================================

import os
import sys
import json
import re
import random
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent
WORKFLOW_FILE = PROJECT_ROOT / "workflow_state.json"
CONTENT_DIR = PROJECT_ROOT / "03_内容仓库" / "04_正文"
OPINION_DIR = PROJECT_ROOT / "06_意见仓库" / "04_正文_审核"

class VerificationEngine:
    """修复验证引擎"""

    def __init__(self):
        self.state = self.load_state()
        self.issues_found = self.state.get('issues_found', {})
        self.verification_results = []

    def load_state(self):
        """加载状态文件"""
        if WORKFLOW_FILE.exists():
            with open(WORKFLOW_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_state(self):
        """保存状态文件"""
        with open(WORKFLOW_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    # -------------------------------------------------------------------------
    # 问题检测
    # -------------------------------------------------------------------------

    def check_repeat_content(self, chapter_num):
        """检查重复内容问题"""
        chapter_file = CONTENT_DIR / f"ch{chapter_num:03d}.md"
        if not chapter_file.exists():
            return None

        with open(chapter_file, 'r', encoding='utf-8') as f:
            content = f.read()

        issues = []

        # ========== 检查点1：章节开头核心句相似 ==========
        # 提取章节开头核心句（从"林夜和"开始到第一个句号）
        first_sentence = None
        if '林夜和' in content:
            start = content.find('林夜和')
            # 找到第一个完整的句子（到句号、问号或感叹号）
            for end_marker in ['。', '！', '？']:
                end = content.find(end_marker, start)
                if end > start and end - start < 200:
                    first_sentence = content[start:end+1]
                    break

        if first_sentence:
            # 与所有相邻及附近章节比较（前后5章范围内）
            for offset in range(-5, 6):
                if offset == 0:
                    continue
                neighbor_num = chapter_num + offset
                if neighbor_num < 1 or neighbor_num > 360:
                    continue

                neighbor_file = CONTENT_DIR / f"ch{neighbor_num:03d}.md"
                if not neighbor_file.exists():
                    continue

                with open(neighbor_file, 'r', encoding='utf-8') as f:
                    neighbor_content = f.read()

                # 检查邻居章节是否也有相同的核心句
                if first_sentence[:30] in neighbor_content[:500]:
                    issues.append({
                        'type': 'REPEAT_OPENING',
                        'severity': 'P0',
                        'target': f'ch{neighbor_num:03d}',
                        'repeat_content': first_sentence[:50],
                        'description': f'与ch{neighbor_num:03d}开头核心句相同'
                    })

        # ========== 检查点2：章内重复 ==========
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if len(line) < 20:
                continue
            count = content.count(line)
            if count > 1:
                issues.append({
                    'type': 'INTRA_CHAPTER_REPEAT',
                    'severity': 'P0',
                    'line_preview': line[:50],
                    'count': count,
                    'description': f'段落"{line[:30]}..."在章内重复{count}次'
                })

        return issues if issues else None

    def check_chapter_number_mismatch(self, chapter_num):
        """检查章节编号与内容不匹配"""
        chapter_file = CONTENT_DIR / f"ch{chapter_num:03d}.md"
        if not chapter_file.exists():
            return None

        with open(chapter_file, 'r', encoding='utf-8') as f:
            content = f.read()

        issues = []

        # 提取标题中的章节号
        title_match = re.search(r'第(.+?)章', content)
        if title_match:
            title_chapter_num = self.chinese_to_number(title_match.group(1))

            if title_chapter_num and title_chapter_num != chapter_num:
                issues.append({
                    'type': 'NUMBER_MISMATCH',
                    'severity': 'P0',
                    'file_number': chapter_num,
                    'title_number': title_chapter_num,
                    'description': f'文件ch{chapter_num:03d}.md但标题为"第{title_match.group(1)}章"'
                })

        # 检查文件名中的章节号是否与实际内容匹配
        # 这里假设ch295应该是"第二百九十五章"
        expected_title = self.number_to_chinese(chapter_num)

        return issues if issues else None

    def chinese_to_number(self, chinese):
        """中文数字转阿拉伯数字"""
        chinese_nums = {
            '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
            '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
            '十': 10, '百': 100, '千': 1000, '万': 10000
        }

        try:
            # 处理 "二百九十五" 格式
            total = 0
            temp = 0

            for char in chinese:
                if char == '零':
                    continue
                elif char in ['十', '百', '千', '万']:
                    if temp == 0:
                        temp = 1
                    total += temp * chinese_nums.get(char, 0)
                    temp = 0
                else:
                    temp = chinese_nums.get(char, 0)

            if temp > 0:
                total += temp

            return total if total > 0 else None
        except:
            return None

    def number_to_chinese(self, num):
        """阿拉伯数字转中文"""
        if num <= 0:
            return '零'

        chinese_units = ['', '十', '百', '千']
        chinese_nums = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九']

        result = ''
        num_str = str(num)
        length = len(num_str)

        for i, digit in enumerate(num_str):
            pos = length - i - 1
            value = int(digit)

            if value != 0:
                result += chinese_nums[value]
                if pos < len(chinese_units):
                    result += chinese_units[pos]

        # 处理十的特殊情况
        result = result.replace('一十', '十')

        return result

    def check_narrative_jump(self, chapter_num):
        """检查叙事跳跃"""
        chapter_file = CONTENT_DIR / f"ch{chapter_num:03d}.md"
        if not chapter_file.exists():
            return None

        with open(chapter_file, 'r', encoding='utf-8') as f:
            content = f.read()

        issues = []

        # 检查点1：突然的场景转换（没有过渡描写）
        # 查找 "——" 或 "..." 或 "与此同时" 等过渡标记
        has_transition = any(marker in content for marker in ['——', '与此同时', '片刻之后', '过了一会儿'])

        if not has_transition and len(content) > 5000:
            # 如果章节很长但没有过渡标记，可能是跳跃
            issues.append({
                'type': 'NARRATIVE_JUMP',
                'severity': 'P1',
                'description': '章节较长但无明显过渡标记，可能存在叙事跳跃'
            })

        return issues if issues else None

    def check_character_consistency(self, chapter_num):
        """检查角色一致性"""
        chapter_file = CONTENT_DIR / f"ch{chapter_num:03d}.md"
        if not chapter_file.exists():
            return None

        with open(chapter_file, 'r', encoding='utf-8') as f:
            content = f.read()

        issues = []

        # 检查小九形态一致性
        # 常见问题：小九一会儿是"它"，一会儿是"她"
        # 修复：正确识别"她"是指向小九还是其他角色（如苏琳）
        if '小九' in content:
            # 统计"它"的总出现次数
            xiaojiu_it = content.count('它')

            # 统计"她"的出现次数——只有当"她"确实在指代小九时才统计
            # 判断标准：只有在"小九的..."结构后出现的"她"，才认为是指代小九
            # 其他情况（如"小九在她怀里"）中的"她"是指向苏琳等其他人
            xiaojiu_she = 0

            lines = content.split('\n')
            for line in lines:
                if '小九的' in line:
                    # 查找"小九的"后面出现的所有"她"
                    idx = line.find('小九的')
                    remaining = line[idx:]
                    # 查找每个"她"
                    pos = 0
                    while True:
                        pos = remaining.find('她', pos)
                        if pos == -1:
                            break
                        # 排除以下情况：
                        # 1. "任由她"结构——由在她前面，说明她是指代苏琳等人，不是小九
                        # 2. "让她"结构
                        # 3. "她们"结构——她们是复数，不是单个"她"
                        before_she = remaining[max(0, pos-5):pos]
                        after_she = remaining[pos:pos+10]
                        # 检查是否是"任由她"或"让她"结构
                        if remaining[pos-1] == '由' or '让她' in before_she:
                            # 她是指代苏琳等人，不是小九，跳过
                            pos += 1
                            continue
                        # 如果"她"后面跟着"们"（她们），跳过
                        if len(after_she) > 1 and after_she[1:2] == '们':
                            pos += 1
                            continue
                        # 如果"她"前面有"的"（如"小九的尾巴被她..."），且"她"后面跟着动词
                        # 这表示"她"是主语在动作，不是小九的代词，跳过
                        if remaining[pos-1:pos] == '的' and len(after_she) > 1 and after_she[1:2].isalpha():
                            # "小九的...她..."结构，"她"是指代其他人
                            pos += 1
                            continue
                        # 否则这可能是问题——小九被称"她"
                        xiaojiu_she += 1
                        pos += 1

            if xiaojiu_it > 0 and xiaojiu_she > 0:
                issues.append({
                    'type': 'PRONOUN_INCONSISTENCY',
                    'severity': 'P0',
                    'character': '小九',
                    'it_count': xiaojiu_it,
                    'she_count': xiaojiu_she,
                    'description': f'小九使用"它"({xiaojiu_it}次)和"她"({xiaojiu_she}次)不一致'
                })

        return issues if issues else None

    # -------------------------------------------------------------------------
    # 验证执行
    # -------------------------------------------------------------------------

    def verify_chapter(self, chapter_num):
        """验证单章修复"""
        issues = []

        # 执行各项检查
        repeat_issues = self.check_repeat_content(chapter_num)
        if repeat_issues:
            issues.extend(repeat_issues)

        mismatch_issues = self.check_chapter_number_mismatch(chapter_num)
        if mismatch_issues:
            issues.extend(mismatch_issues)

        jump_issues = self.check_narrative_jump(chapter_num)
        if jump_issues:
            issues.extend(jump_issues)

        char_issues = self.check_character_consistency(chapter_num)
        if char_issues:
            issues.extend(char_issues)

        return {
            'chapter': f'ch{chapter_num:03d}',
            'verified_at': datetime.now().isoformat(),
            'issues_found': issues,
            'status': 'FAILED' if issues else 'PASSED'
        }

    def verify_sample(self, sample_size=36):
        """随机抽样验证"""
        random.seed()
        samples = random.sample(range(1, 361), sample_size)

        results = []
        for num in samples:
            result = self.verify_chapter(num)
            results.append(result)

        return {
            'verified_at': datetime.now().isoformat(),
            'sample_size': sample_size,
            'results': results,
            'summary': {
                'total': len(results),
                'passed': sum(1 for r in results if r['status'] == 'PASSED'),
                'failed': sum(1 for r in results if r['status'] == 'FAILED')
            }
        }

    def verify_p0_all(self):
        """100%验证所有P0问题"""
        # 从issues_found中提取所有涉及P0问题的章节
        p0_chapters = set()

        for range_key, issues_list in self.issues_found.items():
            for issue in issues_list:
                if 'P0' in str(issue):
                    # 提取章节范围
                    match = re.search(r'ch(\d+)(?:-ch(\d+))?', range_key)
                    if match:
                        start = int(match.group(1))
                        end = int(match.group(2)) if match.group(2) else start
                        for num in range(start, end + 1):
                            p0_chapters.add(num)

        results = []
        for num in sorted(p0_chapters):
            result = self.verify_chapter(num)
            results.append(result)

        return {
            'verified_at': datetime.now().isoformat(),
            'p0_chapters_count': len(p0_chapters),
            'results': results,
            'summary': {
                'total': len(results),
                'passed': sum(1 for r in results if r['status'] == 'PASSED'),
                'failed': sum(1 for r in results if r['status'] == 'FAILED')
            }
        }

    def generate_report(self, results, output_file=None):
        """生成验证报告"""
        report = []
        report.append("# 修复验证报告")
        report.append("")
        report.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        report.append(f"**验证方法**: {'随机抽样' if 'sample_size' in results else 'P0全量验证'}")
        report.append("")

        if 'summary' in results:
            s = results['summary']
            report.append("## 汇总")
            report.append("")
            report.append(f"| 指标 | 数值 |")
            report.append(f"|------|------|")
            report.append(f"| 总章节数 | {s['total']} |")
            report.append(f"| 通过 | {s['passed']} |")
            report.append(f"| 失败 | {s['failed']} |")
            report.append(f"| 通过率 | {s['passed']/s['total']*100:.1f}% |")
            report.append("")

        report.append("## 详细结果")
        report.append("")

        for result in results.get('results', []):
            report.append(f"### {result['chapter']} - {result['status']}")
            report.append("")

            if result['issues_found']:
                for issue in result['issues_found']:
                    report.append(f"- **{issue['type']}** ({issue['severity']})")
                    report.append(f"  - {issue['description']}")
                    report.append("")
            else:
                report.append("- 无问题")
                report.append("")

        report_content = '\n'.join(report)

        if output_file:
            output_path = OPINION_DIR / output_file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            print(f"报告已生成: {output_path}")

        return report_content

# -----------------------------------------------------------------------------
# 主程序
# -----------------------------------------------------------------------------

def main():
    engine = VerificationEngine()

    if len(sys.argv) < 2:
        print("用法: python3 run_verify_engine.py [sample|p0|report|check] [参数]")
        print("  sample - 随机抽样36章验证")
        print("  p0     - 验证所有P0问题章节")
        print("  check  - 验证指定章节 (如: check ch291)")
        print("  report - 生成验证报告")
        sys.exit(1)

    command = sys.argv[1]

    if command == 'sample':
        results = engine.verify_sample()
        engine.generate_report(results, '验证报告_sample.md')
        print(f"通过率: {results['summary']['passed']/results['summary']['total']*100:.1f}%")

    elif command == 'p0':
        results = engine.verify_p0_all()
        engine.generate_report(results, '验证报告_p0.md')
        print(f"P0验证: {results['summary']['passed']}/{results['summary']['total']} 通过")

    elif command == 'check':
        if len(sys.argv) < 3:
            print("请指定章节号，如: check ch291")
            sys.exit(1)

        chapter_arg = sys.argv[2]
        match = re.search(r'ch(\d+)', chapter_arg)
        if match:
            num = int(match.group(1))
            result = engine.verify_chapter(num)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("无效的章节号")

    elif command == 'report':
        results = engine.verify_sample()
        report = engine.generate_report(results)
        print(report)

    else:
        print(f"未知命令: {command}")
        sys.exit(1)

if __name__ == '__main__':
    main()