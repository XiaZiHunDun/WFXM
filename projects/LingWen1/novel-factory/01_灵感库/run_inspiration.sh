#!/bin/bash
# 小说工作室 · 灵感生成脚本 v1.0
# 用法: ./run_inspiration.sh [command] [params]

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)/.."
WORKFLOW_FILE="$PROJECT_ROOT/workflow_state.json"
INSPIRATION_DIR="$PROJECT_ROOT/01_灵感库"
TEMPLATE_DIR="$INSPIRATION_DIR/模板库"

# 灵感部门成员
INSPIRATIONS=("灵感A" "灵感B" "灵感C")

# 主编轮值顺序
CHIEF_EDITORS=("灵感A" "灵感B" "灵感C")

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

function log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
function log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
function log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
function log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
function log_inspire() { echo -e "${CYAN}[INSPIRE]${NC} $1"; }

# ==================== 帮助信息 ====================

function show_help() {
    cat << 'EOF'
灵感生成脚本 v1.0

用法: ./run_inspiration.sh [command] [params]

命令:
  generate <类型>           启动灵感部门生成
                           示例: ./run_inspiration.sh generate 玄幻
                           示例: ./run_inspiration.sh generate 都市

  integrate                主编整合灵感
                           示例: ./run_inspiration.sh integrate

  status                   查看灵感进度
                           示例: ./run_inspiration.sh status

  deliver <版本>           交付指定版本
                           示例: ./run_inspiration.sh deliver v1.0
                           示例: ./run_inspiration.sh deliver final

  list                     列出所有灵感项目
                           示例: ./run_inspiration.sh list

  template                 查看模板库
                           示例: ./run_inspiration.sh template

  chief                    查看当前主编轮值
                           示例: ./run_inspiration.sh chief

  pending                  查看待处理任务
                           示例: ./run_inspiration.sh pending

灵感项目目录规范:
  01_灵感库/{项目名}/
  ├── 立项/
  │   ├── 灵感_{项目名}_v1.0.yaml
  │   ├── 灵感_{项目名}_v2.0.yaml
  │   └── 灵感_{项目名}_final.yaml
  ├── 基础层.yaml
  └── 深度层.md
EOF
}

# ==================== 工具函数 ====================

# 获取项目列表
function get_project_list() {
    local projects=()
    if [ -d "$INSPIRATION_DIR" ]; then
        for dir in "$INSPIRATION_DIR"/*/; do
            if [ -d "$dir" ]; then
                projects+=("$(basename "$dir")")
            fi
        done
    fi
    echo "${projects[@]}"
}

# 获取当前主编轮值
function get_current_chief() {
    if [ -f "$WORKFLOW_FILE" ]; then
        local chief=$(grep -o '"inspiration_chief":"[^"]*"' "$WORKFLOW_FILE" 2>/dev/null | head -1 | cut -d'"' -f4)
        if [ -z "$chief" ]; then
            echo "灵感A"
        else
            echo "$chief"
        fi
    else
        echo "灵感A"
    fi
}

# 获取下一个主编
function get_next_chief() {
    local current=$(get_current_chief)
    local next_index=0
    for i in "${!CHIEF_EDITORS[@]}"; do
        if [ "${CHIEF_EDITORS[$i]}" == "$current" ]; then
            next_index=$(( (i + 1) % ${#CHIEF_EDITORS[@]} ))
            break
        fi
    done
    echo "${CHIEF_EDITORS[$next_index]}"
}

# 更新主编轮值
function rotate_chief() {
    local next=$(get_next_chief)
    if [ -f "$WORKFLOW_FILE" ]; then
        sed -i "s/\"inspiration_chief\":\"[^\"]*\"/\"inspiration_chief\":\"$next\"/" "$WORKFLOW_FILE"
    fi
}

# 检查项目是否存在
function project_exists() {
    local project=$1
    if [ -d "$INSPIRATION_DIR/$project" ]; then
        return 0
    else
        return 1
    fi
}

# 创建项目目录结构
function create_project_dirs() {
    local project=$1
    mkdir -p "$INSPIRATION_DIR/$project/立项"
    mkdir -p "$INSPIRATION_DIR/$project/临时"
    log_info "创建项目目录: $project"
}

# 获取最新版本
function get_latest_version() {
    local project=$1
    local version_dir="$INSPIRATION_DIR/$project/立项"

    if [ ! -d "$version_dir" ]; then
        echo "v1.0"
        return
    fi

    local versions=$(ls "$version_dir"/灵感_${project}_v*.yaml 2>/dev/null | head -5)
    if [ -z "$versions" ]; then
        echo "v1.0"
        return
    fi

    # 查找最高版本
    local latest="v1.0"
    for v in v2.0 v3.0 final; do
        if ls "$version_dir"/灵感_${project}_${v}.yaml &>/dev/null; then
            latest="$v"
        fi
    done
    echo "$latest"
}

# ==================== 命令实现 ====================

# generate: 启动灵感部门生成
function cmd_generate() {
    local type=$1
    if [ -z "$type" ]; then
        log_error "请指定类型: ./run_inspiration.sh generate <类型>"
        log_info "示例: ./run_inspiration.sh generate 玄幻"
        return 1
    fi

    log_step "启动灵感生成任务"
    log_info "类型: $type"
    log_info "主编: $(get_current_chief)"

    # 创建临时项目目录
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local project="项目_${timestamp}"
    create_project_dirs "$project"

    # 生成基础层.yaml
    log_inspire "生成基础层文档..."
    cat > "$INSPIRATION_DIR/$project/基础层_${type}.yaml" << EOF
# 基础层文档 - ${type}
# 生成时间: $(date +%Y-%m-%d\ %H:%M:%S)
# 主编: $(get_current_chief)

项目名称: ${project}
版本: v1.0
类型: ${type}
主题:
核心卖点:
  - 待填充
  - 待填充
核心人物:
  - 主角: 待填充
  - 配角: 待填充
风格禁忌:
  - 待填充
目标受众: 待填充
市场定位: 待填充

## 灵感A输出（类型专家）
灵感A_输出:
  类型: ${type}
  主题: 待填充
  核心冲突: 待填充
  卖点: 待填充
  禁忌: 待填充
  受众: 待填充

## 灵感B输出（幻想专家）
灵感B_输出:
  世界观: 待填充
  力量体系: 待填充
  环境设定: 待填充
  关键物品: 待填充
  禁忌: 待填充

## 灵感C输出（结构专家）
灵感C_输出:
  时间线: 待填充
  伏笔: 待填充
  叙事结构: 待填充
  高潮节点: 待填充
  情感曲线: 待填充
EOF

    # 生成深度层.md
    log_inspire "生成深度层文档..."
    cat > "$INSPIRATION_DIR/$project/深度层_${type}.md" << EOF
# ${project} 深度层文档 v1.0

> 生成时间: $(date +%Y-%m-%d\ %H:%M:%S)
> 主编: $(get_current_chief)

## 世界观体系

### 宏观世界
待填充

### 力量体系
待填充

### 社会结构
待填充

## 时间线设计

### 主线时间轴
待填充

### 支线时间轴
待填充

## 伏笔设计

### 核心伏笔（3-5条）
待填充

### 伏笔回收节点
待填充

## 叙事结构

### 章节节奏设计
待填充

### 高潮节点分布
待填充

### 情感曲线
待填充

## 关键场景设计

### 场景1
待填充

### 场景2
待填充
EOF

    log_info "生成完成!"
    log_info "项目路径: $INSPIRATION_DIR/$project"
    log_info "请编辑以下文件进行细化:"
    log_info "  - 基础层_${type}.yaml"
    log_info "  - 深度层_${type}.md"

    return 0
}

# integrate: 主编整合灵感
function cmd_integrate() {
    local project=$1

    if [ -z "$project" ]; then
        # 列出项目让用户选择
        local projects=$(get_project_list)
        if [ -z "$projects" ]; then
            log_error "没有找到项目，请先使用 generate 命令生成"
            return 1
        fi
        log_info "可用项目: $projects"
        log_info "用法: ./run_inspiration.sh integrate <项目名>"
        return 1
    fi

    if ! project_exists "$project"; then
        log_error "项目不存在: $project"
        return 1
    fi

    log_step "主编整合灵感"
    log_info "主编: $(get_current_chief)"

    # 检查临时文件
    local temp_files=$(ls "$INSPIRATION_DIR/$project/临时/"*.yaml "$INSPIRATION_DIR/$project/临时/"*.md 2>/dev/null)

    # 获取最新版本
    local latest=$(get_latest_version "$project")
    local next_version="v1.0"
    case $latest in
        v1.0) next_version="v2.0" ;;
        v2.0) next_version="v3.0" ;;
        v3.0) next_version="final" ;;
    esac

    log_info "当前版本: $latest"
    log_info "整合版本: $next_version"

    # 查找基础层和深度层文件
    local base_file=$(ls "$INSPIRATION_DIR/$project/"基础层*.yaml 2>/dev/null | head -1)
    local deep_file=$(ls "$INSPIRATION_DIR/$project/"深度层*.md 2>/dev/null | head -1)

    if [ -z "$base_file" ] || [ -z "$deep_file" ]; then
        log_error "缺少必要文件，请先完成生成任务"
        return 1
    fi

    # 复制到立项目录
    mkdir -p "$INSPIRATION_DIR/$project/立项"
    cp "$base_file" "$INSPIRATION_DIR/$project/立项/灵感_${project}_${next_version}.yaml"
    cp "$deep_file" "$INSPIRATION_DIR/$project/立项/灵感_${project}_${next_version}.md"

    # 更新版本标记
    sed -i "s/版本: v[0-9.]*/版本: ${next_version}/" "$INSPIRATION_DIR/$project/立项/灵感_${project}_${next_version}.yaml"
    sed -i "s/v[0-9.]*/v${next_version}/" "$INSPIRATION_DIR/$project/立项/灵感_${project}_${next_version}.md"

    log_info "整合完成!"
    log_info "输出: $INSPIRATION_DIR/$project/立项/灵感_${project}_${next_version}.*"

    # 轮值主编
    rotate_chief
    log_info "主编轮值: $(get_current_chief)"

    return 0
}

# status: 查看灵感进度
function cmd_status() {
    log_step "灵感部门状态"

    echo ""
    echo "=========================================="
    echo "           灵感部门工作状态"
    echo "=========================================="
    echo ""
    echo "当前主编: $(get_current_chief)"
    echo "主编轮值: ${CHIEF_EDITORS[*]}"
    echo ""
    echo "------------------------------------------"
    echo "           灵感部门成员"
    echo "------------------------------------------"
    printf "  %-10s %-15s %-10s\n" "成员" "专项" "状态"
    printf "  %-10s %-15s %-10s\n" "灵感A" "类型专家" "待命"
    printf "  %-10s %-15s %-10s\n" "灵感B" "幻想专家" "待命"
    printf "  %-10s %-15s %-10s\n" "灵感C" "结构专家" "待命"
    echo ""

    local projects=$(get_project_list)
    if [ -z "$projects" ]; then
        echo "------------------------------------------"
        echo "           项目列表 (空)"
        echo "------------------------------------------"
        echo ""
        log_info "没有进行中的项目"
        log_info "使用 ./run_inspiration.sh generate <类型> 启动新项目"
    else
        echo "------------------------------------------"
        echo "           项目列表"
        echo "------------------------------------------"
        printf "  %-30s %-15s\n" "项目名" "最新版本"
        echo "------------------------------------------"
        for p in $projects; do
            local latest=$(get_latest_version "$p")
            printf "  %-30s %-15s\n" "$p" "$latest"
        done
        echo ""
    fi

    return 0
}

# deliver: 交付指定版本
function cmd_deliver() {
    local version=$1
    local project=$2

    if [ -z "$version" ]; then
        log_error "请指定版本: ./run_inspiration.sh deliver <版本> [项目名]"
        log_info "示例: ./run_inspiration.sh deliver v1.0"
        log_info "示例: ./run_inspiration.sh deliver final"
        return 1
    fi

    # 如果没指定项目，列出项目列表
    if [ -z "$project" ]; then
        local projects=$(get_project_list)
        if [ -z "$projects" ]; then
            log_error "没有找到项目"
            return 1
        fi
        log_info "可用项目: $projects"
        log_info "用法: ./run_inspiration.sh deliver $version <项目名>"
        return 1
    fi

    if ! project_exists "$project"; then
        log_error "项目不存在: $project"
        return 1
    fi

    log_step "交付版本: $version"
    log_info "项目: $project"

    # 检查版本文件
    local version_file="$INSPIRATION_DIR/$project/立项/灵感_${project}_${version}.yaml"
    if [ ! -f "$version_file" ]; then
        log_error "版本文件不存在: $version_file"
        log_info "可用版本:"
        ls "$INSPIRATION_DIR/$project/立项/" 2>/dev/null
        return 1
    fi

    # 执行交付
    log_info "=== 交付清单 ==="
    echo ""
    echo "项目: $project"
    echo "版本: $version"
    echo ""
    echo "交付文件:"
    echo "  - 基础层: $INSPIRATION_DIR/$project/立项/灵感_${project}_${version}.yaml"
    echo "  - 深度层: $INSPIRATION_DIR/$project/立项/灵感_${project}_${version}.md"
    echo ""

    # 验证文件完整性
    log_step "验证交付文件..."
    local base_size=$(stat -f%z "$version_file" 2>/dev/null || stat -c%s "$version_file" 2>/dev/null)
    local deep_file="$INSPIRATION_DIR/$project/立项/灵感_${project}_${version}.md"
    local deep_size=$(stat -f%z "$deep_file" 2>/dev/null || stat -c%s "$deep_file" 2>/dev/null)

    if [ "$base_size" -lt 100 ] || [ "$deep_size" -lt 100 ]; then
        log_warn "警告: 文件可能未完成填充"
        log_warn "  基础层: $base_size bytes"
        log_warn "  深度层: $deep_size bytes"
    else
        log_info "文件验证通过"
    fi

    if [ "$version" == "final" ]; then
        log_step "最终版本交付完成"
        # 轮值主编
        rotate_chief
    fi

    return 0
}

# list: 列出所有项目
function cmd_list() {
    local projects=$(get_project_list)

    echo ""
    echo "=========================================="
    echo "           灵感项目列表"
    echo "=========================================="
    echo ""

    if [ -z "$projects" ]; then
        log_info "没有项目"
    else
        printf "  %-30s %-15s %-20s\n" "项目名" "版本" "状态"
        echo "------------------------------------------"
        for p in $projects; do
            local latest=$(get_latest_version "$p")
            printf "  %-30s %-15s\n" "$p" "$latest"
        done
    fi
    echo ""

    return 0
}

# template: 查看模板库
function cmd_template() {
    echo ""
    echo "=========================================="
    echo "           灵感模板库"
    echo "=========================================="
    echo ""

    local templates=$(ls "$TEMPLATE_DIR"/*.yaml "$TEMPLATE_DIR"/*.md 2>/dev/null)

    if [ -z "$templates" ]; then
        log_info "模板库为空"
    else
        printf "  %-40s %-15s\n" "模板名" "类型"
        echo "------------------------------------------"
        for t in $templates; do
            local name=$(basename "$t")
            printf "  %-40s\n" "$name"
        done
    fi

    echo ""
    log_info "模板目录: $TEMPLATE_DIR"
    log_info "使用说明:"
    echo "  1. 复制模板到项目目录"
    echo "  2. 根据项目特点调整内容"
    echo "  3. 使用 integrate 命令整合"

    return 0
}

# chief: 查看当前主编
function cmd_chief() {
    local current=$(get_current_chief)
    local next=$(get_next_chief)

    echo ""
    echo "=========================================="
    echo "           主编轮值"
    echo "=========================================="
    echo ""
    echo "  当前主编: $current"
    echo "  下一位:   $next"
    echo ""
    echo "  轮值顺序: ${CHIEF_EDITORS[*]}"
    echo ""

    return 0
}

# pending: 查看待处理任务
function cmd_pending() {
    echo ""
    echo "=========================================="
    echo "           灵感部门待处理任务"
    echo "=========================================="
    echo ""

    local projects=$(get_project_list)
    local has_pending=false

    for p in $projects; do
        local latest=$(get_latest_version "$p")

        # 检查是否有未完成的临时文件
        local temp_count=$(ls "$INSPIRATION_DIR/$p/临时/"*.yaml "$INSPIRATION_DIR/$p/临时/"*.md 2>/dev/null | wc -l | tr -d ' ')

        if [ "$temp_count" -gt 0 ]; then
            has_pending=true
            echo "  项目: $p"
            echo "    当前版本: $latest"
            echo "    待处理文件: $temp_count"
            echo ""
        fi
    done

    if [ "$has_pending" = false ]; then
        log_info "没有待处理任务"
    fi

    echo ""
    log_info "使用 ./run_inspiration.sh status 查看完整状态"

    return 0
}

# ==================== 主入口 ====================

COMMAND=$1
shift || true

case $COMMAND in
    generate)
        cmd_generate "$@"
        ;;
    integrate)
        cmd_integrate "$@"
        ;;
    status)
        cmd_status "$@"
        ;;
    deliver)
        cmd_deliver "$@"
        ;;
    list)
        cmd_list "$@"
        ;;
    template)
        cmd_template "$@"
        ;;
    chief)
        cmd_chief "$@"
        ;;
    pending)
        cmd_pending "$@"
        ;;
    -h|--help|help)
        show_help
        ;;
    *)
        if [ -z "$COMMAND" ]; then
            show_help
        else
            log_error "未知命令: $COMMAND"
            show_help
        fi
        exit 1
        ;;
esac

exit $?
