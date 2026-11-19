/**
 * 消息契约测试共享常量（只放数据，不放断言/逻辑）。
 *
 * 锚点：入站「数据形态」与出站「可发送性」的边界输入。
 * 这些值描述用户/渠道可能发来的真实形态，不代表生产实现的常量。
 */

/** 固定时钟：让 turnId / 幂等键可重复验证（不依赖真实时间）。 */
export const FIXED_NOW_MS = 1_700_000_000_000

/** 超长文本：远大于任何入站/出站上限，用于验证「不崩溃 + 截断/不截断」契约。 */
export const LONG_TEXT_200K = "字".repeat(200_000)

/** emoji + 中英混合：多字节字符边界。 */
export const MIXED_TEXT = "请修复 login 超时 🚀 bug：Timeout after 30s 😀，谢谢！"

/** 控制字符：NUL / BEL / ANSI 转义 / DEL，规范化不应抛错或意外改写。 */
export const CONTROL_CHARS = "\u0000\u0007\u001b[31m\u007f"

/** 合法的客户端会话 id（符合 [A-Za-z0-9_.:-]，用于预订阅场景）。 */
export const VALID_CONVERSATION_ID = "c.custom:42"

/** 与 conversation-id.ts 对齐的上限（契约值，测试独立声明）。 */
export const CONVERSATION_ID_MAX_LEN = 128
