# 阶段二实施状态

更新时间：2026-07-24

| 里程碑 | 状态 | 已完成 | 后续工作 |
|---|---|---|---|
| M0 基线与设计冻结 | 完成 | 调用清单、ADR、核心 Schema、迁移顺序 | 补充真实 Provider 的成本基线 |
| M1 LLM Gateway | 完成（核心） | OpenAI-compatible、Anthropic、Ollama；统一 usage；有限重试；元数据 trace | 逐个移除遗留 Provider 构造代码 |
| M2 Context 与预算 | 完成（第一版） | 保守 Token 估算、区域预算、排序、去重、语义块截断、决策报告 | 接入精确 tokenizer 和可选 LLM 摘要 |
| M3 Skill Framework | 完成 | Registry、Runner、七个内置 Skill；`text_rewriter`、`jd_analyzer`、`interview_coach` 生产接入 | 后续新增能力统一通过 Skill 接入 |
| M4 长期记忆 | 进行中 | SQLite/WAL、Memory CRUD/导出、隐私设置、JD 去重归档、简历版本链与恢复 API | 面试自动归档、记忆提取确认 UI |
| M5 Token 优化 | 完成（核心） | L1/L2 Cache、版本化缓存键、TTL、分区 fingerprint、变更检测 | 对简历分段生成接入增量重算和 Token 报表 UI |
| M6 剩余 Skills 迁移 | 进行中 | Interview Coach 已迁移；Mock Interview 已接入 Context 预算和统一 Trace | 迁移 resume_writer、skill_matcher、career_advisor，并将 Mock Interview 模型构造切换到 Gateway |

## 当前生产接入

- 文本改写与面试准备：已经通过 `AIRuntime → ContextManager → PromptCache → LLMGateway`。
- JD Analyzer：提供 `/api/ai/jd/analyze` 和 `/api/ai/jd/history`，记录 usage、缓存、Skill Run 和去重归档。
- Mock Interview：轮次状态机保持不变，最近对话已通过 Context Manager 预算，并记录上下文压缩指标。
- 简历源内容：保存时生成完整 SQLite 快照，可通过 `/api/resume/versions` 查询和恢复。

## 下一实施批次

1. 将 Resume Writer 的分段生成迁移到 Runtime，并利用版本快照保证可回滚。
2. 将 Mock Interview 的 Provider 构造切换到 Gateway，移除临时 `TracedChatClient` 适配层。
3. 为 Skill Matcher 和 Career Advisor 增加业务 API 与前端入口。
4. 增加长期记忆候选项确认 UI 和面试弱项自动归档。
