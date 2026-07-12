# 已完成功能 (Features)

来源：Notion《已完成功能 (Features)》  
Notion 更新时间：2026-06-20  
本地同步：2026-07-10

## 核心功能

- [x] 简历生成引擎：支持普通简历和基于 JD 的定制简历。
- [x] 配置面板：API Key、模型、Base URL、协议配置。
- [x] 历史记录：展示生成的简历列表。
- [x] PDF 下载。
- [x] 多语言支持：中文/英文简历和系统语言。
- [x] 根据是否提供职位描述自动切换生成模式。
- [x] 面试准备模块：基于简历和 JD 生成面试准备报告。
- [x] 模拟面试模块：AI 扮演面试官，多轮对话，支持 5 种风格。
- [x] UI 架构重构：Gradio 升级到 Vite + React + FastAPI。
- [x] uv + pyproject.toml 依赖管理。
- [x] 品牌重塑：不平 / Buping。
- [x] 简历实时预览：基于本地 YAML 秒级预览。
- [x] iframe WYSIWYG 编辑器：编辑态样式保真。
- [x] 自动保存到 localStorage。
- [x] 历史简历预览。
- [x] 侧边栏折叠和状态持久化。
- [x] 简历文档上传解析：PDF/DOCX/HTML/MD/YAML/LaTeX。

## UI 优化

- [x] 样式选择控件修复。
- [x] 简历内容 max_tokens 提升。
- [x] React 19 + Tailwind CSS 现代化 UI。
- [x] 侧边栏导航。
- [x] 自定义 Logo。
- [x] 简历预览居中。
- [x] iframe WYSIWYG 替代 TipTap，减少 bundle。
- [x] 编辑页新增行距和模块间距滑块。
- [x] Cloyola Grey 去阴影。
- [x] Modern Blue 提升信息密度。

## 技术改进

- [x] ContentBlockParser 过滤 thinking 块。
- [x] 中文 YAML 兼容性增强。
- [x] LLM 调用从 7-8 次合并为 1-2 次。
- [x] FastAPI 后端 RESTful 化。
- [x] 可选依赖懒加载。
- [x] FastAPI 异步路由 + `to_thread`。
- [x] 401/400/403/404 错误快速失败。
- [x] API Key fallback：参数 -> `secrets.yaml` -> `config.py`。
- [x] Chrome 启动优先使用本地缓存。
- [x] HTML 持久化，用于历史预览。
- [x] 文档解析器支持多格式输入。
- [x] PDF 分页保护改为二级小模块保护。
