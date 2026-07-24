# AI Engine 自动评估

运行：

```bash
python scripts/benchmark_ai_engine.py --check --output artifacts/ai-engine-benchmark.json
```

评估不调用外部模型，覆盖：

- Context Token 降幅、关键事实保留率和 P95 延迟。
- Prompt Cache 命中率、持久化计数和 P95 读取延迟。
- SQLite 长期记忆读写正确率及 P95 延迟。
- LLM Gateway usage 标准化正确率和调用额外开销。
- 七个 Skill 的注册完整性、预算有效性和增量更新检测。
- Prompt 的事实约束、结构化输出和证据要求覆盖率。

阈值位于 `tests/fixtures/ai_engine/performance_budgets.json`。修改 Prompt、Context、缓存、记忆、Skill 或相关业务调用代码时，`.github/workflows/ai-engine-evaluation.yml` 会自动运行评估；违反阈值时 CI 失败，并上传 JSON 报告。

该评估负责确定性工程指标，不替代真实模型质量评测。真实模型的事实一致性、表达质量和成本对比应在具备测试 API 配置的受控环境中单独运行，避免 CI 产生费用或泄露凭证。
