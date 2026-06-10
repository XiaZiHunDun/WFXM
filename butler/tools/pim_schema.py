"""Centralized PIM data schema — enums, limits, and constants.

All PIM modules (contacts, memo, expense, habits, reminder) share this
single source of truth for categories, priorities, directions, limits, etc.
"""

from __future__ import annotations

# ── Contacts ──
CONTACT_CATEGORIES = frozenset({"personal", "work", "service", "medical", "other"})
CONTACT_CATEGORY_LABELS = {
    "personal": "个人", "work": "工作", "service": "服务",
    "medical": "医疗", "other": "其他",
}
MAX_CONTACTS = 500
MAX_PHONES = 5
MAX_EMAILS = 5
MAX_CONTACT_TAGS = 10
MAX_TAG_LEN = 30
MAX_CONTACT_NOTES = 500

# ── Memo ──
MEMO_CATEGORIES = frozenset({"general", "health", "finance", "travel", "shopping", "social", "work"})
MEMO_CATEGORY_LABELS = {
    "general": "通用", "health": "健康", "finance": "财务",
    "travel": "出行", "shopping": "购物", "social": "社交", "work": "工作",
}
MEMO_STATUSES = frozenset({"active", "done", "archived"})
MEMO_PRIORITIES = frozenset({"low", "normal", "high", "urgent"})
MEMO_PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
MAX_ACTIVE_MEMOS = 200
MAX_MEMO_CONTENT_LEN = 2000
MAX_MEMO_TAGS = 10

# ── Expense ──
EXPENSE_CATEGORIES = frozenset({
    "food", "transport", "housing", "medical", "entertainment",
    "shopping", "education", "social", "salary", "investment", "other",
})
EXPENSE_CATEGORY_LABELS = {
    "food": "餐饮", "transport": "交通", "housing": "住房",
    "medical": "医疗", "entertainment": "娱乐", "shopping": "购物",
    "education": "教育", "social": "社交", "salary": "薪资",
    "investment": "投资", "other": "其他",
}
EXPENSE_DIRECTIONS = frozenset({"income", "expense"})
EXPENSE_DIR_LABELS = {"income": "收入", "expense": "支出"}
MAX_EXPENSE_RECORDS = 5000
MAX_EXPENSE_DESC_LEN = 200

# ── Habits ──
HABIT_FREQUENCIES = frozenset({"daily", "weekly"})
HABIT_FREQ_LABELS = {"daily": "每日", "weekly": "每周"}
MAX_ACTIVE_HABITS = 30

# ── Reminder ──
REMINDER_STATUSES = frozenset({"pending", "fired"})
MAX_ACTIVE_REMINDERS = 100
MAX_REMINDER_MESSAGE_LEN = 500

# ── All PIM tool names (registered in builtin_register.py) ──
ALL_PIM_TOOLS = frozenset({
    # Contacts
    "contact_add", "contact_find", "contact_update", "contact_delete", "contact_list",
    # Memo
    "memo_add", "memo_list", "memo_search", "memo_update", "memo_delete",
    # Expense
    "expense_add", "expense_summary", "expense_list", "expense_update",
    "expense_search", "expense_delete",
    # Habits
    "habit_create", "habit_checkin", "habit_stats", "habit_list", "habit_update",
    "habit_delete",
    # Reminder
    "set_reminder", "list_reminders", "reminder_list_active", "cancel_reminder",
})
