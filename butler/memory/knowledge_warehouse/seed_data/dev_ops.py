"""Seed data for dev_ops domain."""

from __future__ import annotations

from typing import Any, Dict, List

DEV_OPS_MATERIALS: List[Dict[str, Any]] = [
{
        "source_type": "text",
        "domain_hint": "dev_ops",
        "title": "CI/CD实践",
        "content": """CI/CD最佳实践：

1. 持续集成：
   - 代码提交后自动构建
   - 运行单元测试
   - 代码质量检查

2. 持续部署：
   - 自动化部署流程
   - 多环境部署
   - 蓝绿部署/金丝雀发布

3. 流水线设计：
   - 构建阶段
   - 测试阶段
   - 部署阶段
   - 验证阶段

4. 常用工具：
   - GitHub Actions
   - GitLab CI
   - Jenkins
   - CircleCI

5. 监控反馈：
   - 部署后监控
   - 自动回滚
   - 性能追踪""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "dev_ops",
        "title": "Docker最佳实践",
        "content": """Docker最佳实践：

1. Dockerfile优化：
   - 使用多阶段构建
   - 使用官方基础镜像
   - 最小化镜像大小
   - 清理构建缓存

2. 容器安全：
   - 不要以root运行
   - 使用非特权用户
   - 限制容器权限
   - 定期更新镜像

3. 网络配置：
   - 使用自定义网络
   - 限制端口暴露
   - 使用环境变量

4. 数据管理：
   - 使用Volume持久化数据
   - 分离配置和代码
   - 备份重要数据

5. 容器编排：
   - 使用Docker Compose
   - 健康检查配置
   - 自动重启策略""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "dev_ops",
        "title": "Kubernetes入门",
        "content": """Kubernetes基础：

1. 核心概念：
   - Pod：最小部署单元
   - Service：服务发现
   - Deployment：应用部署
   - StatefulSet：有状态应用
   - ConfigMap/Secret：配置管理

2. 资源管理：
   - CPU/内存限制
   - 资源请求
   - 水平自动伸缩

3. 网络：
   - Pod网络
   - Service类型(ClusterIP, NodePort, LoadBalancer)
   - Ingress

4. 存储：
   - Volume
   - PersistentVolume
   - StorageClass

5. 监控：
   - Prometheus监控
   - Grafana可视化
   - 日志收集""",
        "priority": 2,
    },]
