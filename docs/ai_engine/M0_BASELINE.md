# AI Engine M0 基线与设计冻结

## 调用基线

当前直接模型调用集中在以下区域：

| 区域 | 能力 | 当前问题 | 迁移目标 |
|---|---|---|---|
| `src/libs/llm_manager.py` | 自动申请问答、摘要、分类 | Provider 与日志强耦合，异常重试无上限 | `LLMGateway` |
| `resume_and_cover_builder/llm` | 简历、求职信、JD 解析 | 重复创建模型，固定 4096 输出 Token | `resume_writer`、`jd_analyzer` |
| `backend/services/resume_service.py` | 文本改写 | Service 内直接组 Prompt 和调用模型 | `text_rewriter` |
| `interview_prep/interview_generator.py` | 面试准备 | 独立 Provider 适配和预算 | `interview_coach` |
| `interview_prep/mock_interview.py` | 模拟面试 | 会话上下文自行拼接 | `mock_interviewer` |
| `document_parser.py` | 文档提取 | 独立 OpenAI-compatible 调用 | Gateway 工具调用 |

## 冻结决策

1. 新 AI 能力必须通过 `src.libs.ai_engine.AIRuntime` 或 `LLMGateway`。
2. 现有 API 路径和响应结构在迁移期间保持兼容。
3. Provider 密钥只存在于运行时配置，不写入 trace、usage、cache key 或数据库。
4. 所有重试必须有上限；默认最多 2 次重试。
5. Token 预算先使用保守估算器，允许后续按模型替换精确 tokenizer。
6. SQLite 是唯一持久化实现；业务层不得直接执行 SQL。
7. 模型调用测试使用注入的 Fake Client，CI 不访问外部 API。
8. 长期记忆默认开启本地存储，但敏感字段、完整 Prompt 和完整响应默认不写入观测日志。

## 核心 Schema

- `LLMRequest` / `LLMResponse`：统一模型请求和响应。
- `TokenUsage`：标准化输入、输出和总 Token。
- `ContextItem` / `ContextBundle`：上下文候选项和最终上下文。
- `TokenBudget` / `BudgetAllocation`：上下文窗口和区域预算。
- `SkillMetadata` / `SkillResult`：Skill 描述和统一结果。
- `MemoryItem` / `SkillRun`：持久化记忆和执行记录。

## 基准数据与指标

第一批离线基准数据位于 `tests/fixtures/ai_engine/`，覆盖中英文短文本、长 JD、简历片段和多轮对话。M1～M6 每阶段记录：

- 输入、输出和总 Token。
- 上下文压缩前后估算 Token。
- 缓存命中率。
- 调用延迟与重试次数。
- Schema 校验成功率。
- 简历事实保留率。

真实 Provider 的成本和延迟基线需要有效 API 配置，因此不作为 CI 前置条件。

## 迁移清单

1. 建立 Gateway、Context、Skill、Memory、Optimization 基础包。
2. 迁移 `rewrite_text`，验证 Runtime 全链路。
3. 迁移 JD 分析和面试准备。
4. 将模拟面试历史交给 Context Manager。
5. 迁移简历生成的分段调用。
6. 迁移遗留 `llm_manager` 调用并移除无限重试。

