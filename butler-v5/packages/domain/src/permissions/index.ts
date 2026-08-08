// domain/permissions/index.ts
// 权限域 barrel — types.ts 提供 Permission ADT + 旧 decidePermission（string union）+ ApprovalRequest 等 ADT
// pure.ts 提供新 decidePermission（PolicyDecision ADT）
// 注：types.ts 与 pure.ts 均导出 decidePermission 但签名不同，barrel 用显式命名导出避免冲突；
//      类型只从 types.ts 暴露以避免重复；新签名 decidePermission 仅从 pure.ts 直接导入

export * from "./types.js"
export { decidePermission } from "./pure.js"
