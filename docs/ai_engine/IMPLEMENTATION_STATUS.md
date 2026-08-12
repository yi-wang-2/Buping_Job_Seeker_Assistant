# 阶段二实施状态

更新时间：2026-08-11

## 当前里程碑

| 里程碑 | 状态 | 当前实现 | 后续工作 |
|---|---|---|---|
| M0 基线与设计冻结 | 完成 | ADR、评估基线、迁移顺序 | 持续补充真实 Provider 成本样本 |
| M1 LLM Gateway | 核心完成 | Provider 适配、usage、重试、metadata trace | 继续移除遗留 Provider 构造代码 |
| M2 Context 与预算 | 第一版完成 | 分类预算、压缩、截断、决策报告 | 增加模型上下文能力表和精确 tokenizer |
| M3 Skill Framework V2 | 完成 | Schema、Registry、Runner、版本、启停、Tool 白名单、自动观测 | 增加真正使用 Tool 的业务 Skill |
| M4 长期记忆 | 进行中 | SQLite/WAL、CRUD、隐私开关、Runtime 自动召回和写入白名单 | 增加用户确认和记忆候选 UI |
| M5 Token 优化 | 核心完成 | L1/L2 Cache、TTL、版本化键、缓存命中真实 token 语义 | 增加 `tokens_saved` 前端指标 |
| M6 业务迁移 | 进行中 | 改写、JD、面试准备、模拟面试、简历生成、状态分类已进入 Runtime | 迁移 Cover Letter、旧 JD Parser 和 `llm_manager` |

## Skill V2 契约

每个 Skill 当前可以声明：

- 名称、版本、Prompt 版本和 Schema 版本。
- Pydantic 输入/输出 Schema。
- Token Budget、temperature、timeout 和缓存 TTL。
- Context 分区权重。
- 长期记忆读写命名空间。
- Tool 白名单、标签、缓存和启停策略。

标准执行链路：

```text
输入 Schema 校验
→ Skill 业务校验
→ 长期记忆召回
→ Context 预算、压缩和截断
→ Tool 白名单检查
→ Prompt Cache
→ LLM Gateway
→ 输出 Schema 与业务证据校验
→ 长期记忆受控写入
→ Trace 和 Skill Run 自动记录
```

## 已注册 Skills

| Skill | 生产接入 | 说明 |
|---|---|---|
| `text_rewriter` | 是 | 文本改写、事实 Harness、缓存 |
| `jd_analyzer` | 是 | 结构化 JD Schema、归档和去重 |
| `interview_coach` | 是 | 面试准备报告 |
| `mock_interviewer` | 是 | 保留现有状态机，每轮模型调用进入 Runtime |
| `resume_writer` | 是 | 保留现有 Prompt、候选评分和事实 Harness，底层调用进入 Runtime；候选生成不缓存 |
| `skill_matcher` | 是 | 匹配分、证据、缺口和建议使用严格输出 Schema |
| `career_advisor` | 是 | 使用严格输出 Schema，并自动读取求职偏好等长期记忆 |
| `job_status_classifier` | 是 | 结构化输出、岗位/状态双置信度、页面原文证据校验和多岗位并行申请明细 |

可通过 `GET /api/ai/skills` 查看当前 Skill、版本、标签和启用状态。

## 可观测性语义

- `SkillResult.usage` 表示本次真实模型消耗；缓存命中时为 0。
- `SkillResult.cached_usage` 表示缓存中原始响应的 usage，可用于计算节省量。
- 每次执行自动生成 `trace_id`。
- 配置 Repository 时，每次成功、失败或缓存命中均自动写入 `skill_runs`。
- Gateway Trace 仍只记录元数据，不保存 Prompt、响应正文和密钥。

## 测试与架构门槛

- Fake LLM 覆盖 Registry、Runner、Schema、缓存、记忆、Tool 权限和状态证据校验。
- 工作流测试覆盖重复改写、JD 去重、简历版本和十轮模拟面试。
- 架构测试禁止在 Gateway 或明确遗留白名单之外新增 `ChatOpenAI`/`ChatAnthropic`。
- Prompt、Schema 或 Skill 版本进入缓存键，版本变化会使旧缓存失效。

## 下一批迁移

1. 迁移 Cover Letter、旧 JD Parser 和 `llm_manager` 中的遗留模型调用。
2. 为长期记忆写入增加用户确认 UI。
3. 给 Token 面板增加缓存节省量、失败率和 Skill 版本维度。
