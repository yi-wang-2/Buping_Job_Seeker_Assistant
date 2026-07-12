# 技术架构 (Architecture)

来源：Notion《技术架构 (Architecture)》  
Notion 更新时间：2026-06-20  
本地同步：2026-07-10

本文档描述项目整体技术架构，新人入职或贡献者可先阅读本页。

## 整体架构

```text
Browser (React 19 + Vite 6 + Tailwind)
  - Sidebar Navigation
  - Resume / InterviewPrep / MockInterview / History / Settings
        |
        | HTTP (Axios)
        v
FastAPI Backend (Uvicorn, port 8000)
  - /api/resume/*
  - /api/interview/*
  - /api/history/*
  - /api/settings/*
        |
        v
Services Layer
  - resume_service.py
  - interview_service.py
  - config_service.py
        |
        v
Core Libraries (src/libs/)
  - resume_and_cover_builder/
    - LLM 调用 (LangChain + Anthropic/OpenAI-compatible)
    - HTML 生成器
    - CSS 样式管理
    - PDF 转换 (Selenium + Chrome)
  - interview_prep/
  - document_parser.py
```

## 核心组件

| 组件 | 文件路径 | 说明 |
| --- | --- | --- |
| 前端入口 | `frontend/src/main.tsx` | React 19 + Vite 6 SPA |
| 后端入口 | `backend/app.py` | FastAPI 应用 |
| API 路由 | `backend/api/router.py` | 统一路由 |
| API 端点 | `backend/api/endpoints/` | resume / interview / history / settings |
| 业务服务 | `backend/services/` | 业务逻辑层 |
| 简历解析 | `src/libs/resume_and_cover_builder/document_parser.py` | 文件上传解析 |
| 启动脚本 | `start-dev.bat` / `start-dev.sh` | 用户级启动入口 |
| 依赖管理 | `pyproject.toml` | uv 管理 |

## 技术栈

| 层 | 技术 | 版本 |
| --- | --- | --- |
| 前端框架 | React | 19+ |
| 前端构建 | Vite | 6+ |
| UI 样式 | Tailwind CSS | 3+ |
| 后端框架 | FastAPI | 0.115+ |
| ASGI 服务器 | Uvicorn | 0.32+ |
| Python 包管理 | uv | 最新 |
| LLM 框架 | LangChain | 0.2.x |
| 数据验证 | Pydantic | v2 |

## 数据流

```text
前端 React
  -> FastAPI 后端 (async + to_thread)
  -> Services 层
  -> LLM 模块 / 简历生成器 / 文件解析器
  -> YAML 解析
  -> Resume 对象
  -> 可选 JD 分析
  -> LLM 生成 HTML
  -> 合并 HTML + CSS
  -> Chrome headless 转 PDF
  -> 保存 PDF + HTML 到 data_folder/output/
  -> 返回 filename/html_filename/path 给前端
```

## 设计原则

- YAML 是“食材”，LLM 是“厨师”：LLM 不应编造经历，但可以更好地讲述经历。
- API Key fallback：参数 -> `secrets.yaml` -> `config.py`。
- 懒加载：可选依赖按需导入，减少启动失败面。
- 异步非阻塞：FastAPI 使用 `asyncio.to_thread` 处理长任务。

## 2026-07-10 本地补充

- 简历中文技能结构调整为 `技术栈` + `语言与其他`。
- PDF 分页保护改为保护二级小模块，一级 `section` 允许跨页。
- 编辑器保存完整 HTML，以确保版式参数同步到 PDF。
