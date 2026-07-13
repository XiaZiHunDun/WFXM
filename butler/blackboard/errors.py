"""黑板自定义异常。"""


class BlackboardError(Exception):
    """黑板基础异常。"""


class SchemaError(BlackboardError):
    """Shift card / claim / backlog 不符合 schema。"""


class ShiftIdConflict(BlackboardError):
    """shift_id 已存在（应 +1 取新序号）。"""


class BlackboardNotInitialized(BlackboardError):
    """黑板目录未初始化（先跑 `butler blackboard init`）。"""