# 问题修复索引 (Troubleshooting)

来源：Notion《问题修复索引 (Troubleshooting)》  
Notion 更新时间：2026-06-20  
本地同步：2026-07-10

## 修复索引

| # | 日期 | 问题 | 修复文件 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 2026-05-28 | 简历生成包含 prompt 乱码 | `llm_generate_resume.py` | 已修复 |
| 2 | 2026-05-28 | 中文 YAML Pydantic 验证失败 | `resume.py` | 已修复 |
| 3 | 2026-05-28 | LLM 调用效率低 | `llm_generate_resume.py` | 已优化 |
| 4 | 2026-05-29 | CSS 文件读取编码错误 | `style_manager.py`, `resume_generator.py` | 已修复 |
| 5 | 2026-06-03 | 面试准备模块 401 | `interview_generator.py`, `app_ui.py` | 已修复 |
| 6 | 2026-06-07 | FastAPI 启动 ModuleNotFoundError | `resume_facade.py` | 已修复 |
| 7 | 2026-06-15 | modern gray 模板编码问题 | `style_manager.py`, `resume_generator.py` | 已修复 |
| 8 | 2026-06-15 | 面试准备 messages must not be empty | `mock_interview.py` | 已修复 |
| 9 | 2026-06-15 | Gradio Chatbot 数据格式不兼容 | `app_ui.py` | 已修复 |
| 10 | 2026-06-15 | Submit answer 时 NoneType llm | `mock_interview.py` | 已修复 |
| 11 | 2026-06-15 | KeyError `text` | `mock_interview.py` | 已修复 |
| 12 | 2026-06-15 | 401 重试导致生成超时 | `utils.py`, `resume_service.py` | 已修复 |
| 13 | 2026-06-15 | 预览不显示最新生成简历 | `ResumeGenerate.tsx`, `resume.py` | 已修复 |
| 14 | 2026-07-10 | 用户配置 API Key 被默认 token 覆盖 | `resume_service.py`, LLM modules | 已修复 |
| 15 | 2026-07-10 | PDF 分页切断模块或整块跳页 | `chrome_utils.py` | 已优化 |

## 问题 1：简历生成包含 prompt 模板乱码

根因：`StrOutputParser()` 无法正确处理 API 返回的 content block 列表。  
方案：创建 `ContentBlockParser`，只提取 `type="text"` 的内容块。

## 问题 12：401 重试导致生成超时

根因：

- `secrets.yaml` 中可能是占位符或无效 key。
- 401 被当作可重试错误。
- 指数退避导致前端等待 5 分钟或更久。

方案：

- 401/400/403/404 立即失败。
- 重试次数从 15 降到 3。
- API Key fallback：参数 -> `secrets.yaml` -> `config.py`。

## 问题 13：预览不显示最新生成简历

根因：后端只保存 PDF，前端预览走本地 YAML 渲染。  
方案：

- 生成时同时保存 HTML。
- 新增 `GET /preview-saved/{html_filename}`。
- 前端生成完成后加载最新 HTML。

## 问题 14：API Key 优先级错误

根因：部分 LLM 初始化代码使用：

```python
api_key = cfg.ANTHROPIC_AUTH_TOKEN or openai_api_key
```

这会导致 `config.py` 默认 token 覆盖用户设置页传入的 key。

方案：

```python
api_key = openai_api_key or cfg.ANTHROPIC_AUTH_TOKEN
```

同时后端生成时同步根 `config.py` 中的协议、Base URL 和 token。

## 问题 15：PDF 分页观感差

根因：最初保护整个 `section`，大模块会整体跳页；不保护时小模块会被截断。  
方案：

- 一级 `section` 允许跨页。
- 二级小模块（`.entry`、技术栈、语言与其他、列表块）尽量整体分页。
- 标题避免孤立在页底。
