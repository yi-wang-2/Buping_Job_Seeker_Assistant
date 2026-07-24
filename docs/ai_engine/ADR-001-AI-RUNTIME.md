# ADR-001：统一 AI Runtime

状态：Accepted

## 决策

采用分层 Runtime：业务 API 调用 Skill Runner；Runner 使用 Context Manager、Memory Manager 和 LLM Gateway。Provider 实现不得依赖业务 Prompt，Skill 不得直接创建 LangChain Chat Model。

## 原因

当前相同 Provider 的初始化和错误处理存在多份实现，导致 Token 上限、协议识别、重试和 usage 解析不一致。统一 Runtime 可以在不改变现有 API 的情况下逐步替换这些实现。

## 影响

- 短期内新旧调用并存。
- 每迁移一个能力，都需要兼容性测试。
- Provider SDK 或 LangChain 版本变化只影响 Gateway 层。

