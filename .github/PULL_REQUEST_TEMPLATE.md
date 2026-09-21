## 关联

<!-- closes #XX / fixes #XX / refs #XX -->

## 变更摘要

<!-- 1-3 句话讲做了什么 -->

## 变更类型

- [ ] feat（新功能）
- [ ] fix（bug 修复）
- [ ] refactor（重构，无行为变化）
- [ ] docs（文档）
- [ ] test（测试）
- [ ] chore（杂项）
- [ ] 🔒 security（安全修复）

## 影响面

- [ ] 触及 §3 边界（domain / adapters / apps）
- [ ] 触及 KNOWN_ENTRY_POINTS（routes/inbound.ts 等）
- [ ] 触及 audit emit（actor 字段）
- [ ] 触及 owner-jargon 文案（用 safeOwnerErrorString 等 helper）
- [ ] 触及 secrets（Secret<T> 包装）

> 💡 如不确定上述某项是否适用，可问 owner。

## 测试

- [ ] `pnpm lint` 通过
- [ ] `pnpm typecheck` 通过
- [ ] `pnpm test:full` 通过（含本变更覆盖）
- [ ] `pnpm acceptance` 通过（如触及 §X 行为）
- [ ] 新增/修改测试覆盖本变更

## 自检清单

- [ ] commit message 符合 conventional commits（feat/fix/refactor/...）
- [ ] 代码遵循 [docs/architecture/](https://github.com/XiaZiHunDun/WFXM/tree/main/docs/architecture) 已记录的模式
- [ ] 无 hardcoded secrets / credentials
- [ ] 无 console.log / 调试残留
- [ ] [CHANGELOG.md](https://github.com/XiaZiHunDun/WFXM/blob/main/CHANGELOG.md)（如适用）已更新
- [ ] [AGENTS.md](https://github.com/XiaZiHunDun/WFXM/blob/main/AGENTS.md) / [STRUCTURE.md](https://github.com/XiaZiHunDun/WFXM/blob/main/STRUCTURE.md)（如有目录变更）已同步

## 截图 / 录屏

<!-- UI / owner-jargon 文案 / 错误处理可视化等 -->

## 上游同步检查

- [ ] 如触及 [butler-v5/](https://github.com/XiaZiHunDun/WFXM/tree/main/butler-v5) 子项目，确认 root 与 subproject 同步
