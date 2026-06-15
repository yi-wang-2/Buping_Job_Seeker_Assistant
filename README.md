# 不平 - 智能求职助手

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19+-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-6+-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![uv](https://img.shields.io/badge/uv-powered-DE5FE9?logo=astral&logoColor=white)](https://docs.astral.sh/uv/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **人生之路总是坎坷，这也造就了我们不平凡的人生.**

AI 求职助手是一个基于大语言模型 (LLM) 的智能求职辅助工具。覆盖从简历优化、岗位匹配、面试准备到职业发展的完整求职周期。

> **English version**: [README_EN.md](README_EN.md)

---

## ✨ 核心功能

### 🎯 已实现功能

- **📄 简历生成引擎**
  - 普通简历生成（基于 YAML）
  - JD 定制简历生成（针对职位描述优化）
  - 单次 LLM 调用生成完整简历（~30 秒）
  - 支持 5 种专业样式模板
  - 详实量化内容，ATS 友好

- **�️ 实时简历预览**
  - 基于本地 YAML 的秒级预览（不调 LLM）
  - 切换样式/语言自动刷新
  - iframe 完整样式渲染

- **✏️ 富文本编辑器（TipTap）**
  - WYSIWYG 编辑生成内容
  - 20+ 工具栏按钮：粗体/斜体/下划线、标题、列表、链接、代码等
  - 50 步撤销/重做历史
  - 每 1.5s 自动保存到 localStorage（保留 5 个版本）
  - 导出编辑版 HTML

- **📂 历史简历预览**
  - 下拉式历史选择器
  - 一键加载任意历史简历到预览
  - 生成完成后自动加载最新内容到预览

- **�📋 面试准备模块**
  - 基于简历和 JD 自动生成面试准备报告
  - 包含：技术问题、行为面试 (STAR)、简历深挖、准备清单
  - 支持中英文双语
  - Markdown 报告导出

- **🎭 模拟面试模块**
  - AI 扮演面试官，多轮对话模拟
  - 5 种面试官风格：友善型 / 专业型 / 压力型 / 学术型 / 闲聊型
  - 自动轮次控制：开场 → 项目 → 技术 → 行为 → 反问 → 结束
  - 结束生成多维度评估报告

- **🎨 三列布局**
  - 左侧：API 配置 + 样式选择
  - 中间：简历预览（居中突出）
  - 右侧：职位描述

- **📊 生成进度条**
  - 5 阶段可视化进度（解析 → LLM → CSS → Chrome → 保存）
  - 30-60s 生成期间实时反馈
  - 比单纯 spinner 体验更好

- **🔧 可隐藏侧边栏**
  - 一键折叠/展开
  - 状态持久化到 localStorage
  - 移动端友好

- **⚙️ 配置与设置**
  - API Key / Base URL 配置面板
  - 模型类型选择（`anthropic` / `openai`）
  - 简历语言选择（中文/英文）
  - 配置会写入 `data_folder/secrets.yaml`

- **📚 历史记录**
  - 生成的简历历史列表
  - 一键下载 PDF
  - 预览历史简历

### 🚧 规划中功能

- 岗位匹配分析（从网络爬虫池）
- 申请跟踪管理
- 技能缺口分析
- 学习路径推荐

---

## 🛠️ 技术架构

| 组件 | 技术栈 |
|------|--------|
| 前端 | React 19 + Vite 6 + Tailwind CSS (端口 5173) |
| 后端 | FastAPI + Uvicorn (端口 8000) |
| 富文本编辑器 | TipTap 3.26 + ProseMirror |
| 包管理 | uv (Python) + npm (Node.js) |
| LLM 引擎 | Anthropic 兼容 API (推荐 `MiniMax-M3`) |
| PDF 生成 | Selenium + Chrome DevTools Protocol |
| 数据验证 | Pydantic v2 |
| LLM 框架 | LangChain |
| Python 版本 | 3.11+ |

---

## 📁 目录结构

```
Buping_Job_Seeker_Assistant/
├── pyproject.toml               # uv 项目配置 (替代 requirements.txt)
├── start-dev.bat                # Windows 一键启动
├── start-dev.sh                 # Linux/Mac 一键启动
├── main.py                      # CLI 入口 (保留)
├── config.py                    # 全局配置 (API Key 等)
│
├── backend/                     # FastAPI 后端
│   ├── app.py                   # FastAPI 入口
│   ├── dev_launcher.py          # 开发启动器 (同时启前后端)
│   └── api/
│       ├── router.py            # API 路由汇总
│       └── endpoints/
│           ├── resume.py        # 简历生成 API
│           ├── interview.py     # 面试准备 + 模拟面试 API
│           ├── settings.py      # 配置管理 API
│           └── history.py       # 历史记录 API
│
├── data_folder/                 # 用户数据 (实际数据，已脱敏)
│   ├── plain_text_resume.yaml   # 简历内容 (英文)
│   ├── plain_text_resume_zh.yaml # 简历内容 (中文)
│   ├── work_preferences.yaml    # 工作偏好
│   ├── work_preferences_zh.yaml
│   └── secrets.yaml             # API 密钥 (模板)
│
├── data_folder_example/         # 用户数据示例
│   ├── plain_text_resume.yaml   # 简历示例 (英文)
│   ├── resume_liam_murphy.txt
│   ├── work_preferences.yaml
│   └── secrets.yaml
│
├── frontend/                    # React + Vite 前端
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/client.ts        # API 调用封装
│       ├── i18n/index.ts        # 中英文国际化
│       ├── components/          # 通用组件
│       └── pages/               # 页面 (5 个)
│
├── src/                         # 业务逻辑 (保持不动)
├── data_folder/                 # 用户数据
└── assets/                      # 静态资源
```

---

## 🚀 快速开始

### 环境要求

| 依赖 | 版本 |
|:-----|:-----|
| 🐍 Python | 3.11+ |
| 📦 [uv](https://docs.astral.sh/uv/) | latest |
| 🟢 Node.js | 18+ |

### 一键启动

```bash
# 克隆仓库
git clone git@github.com:yi-wang-2/Buping_Job_Seeker_Assistant.git
cd Buping_Job_Seeker_Assistant

# 一键启动（自动安装依赖 + 启动前后端）
# Windows
.\start-dev.bat
# Linux/Mac
sh start-dev.sh
```

启动后访问：前端 [http://127.0.0.1:5173](http://127.0.0.1:5173) · 后端 [http://127.0.0.1:8000](http://127.0.0.1:8000)

<details>
<summary>📎 手动启动</summary>

```bash
# 安装 Python 依赖
uv sync

# 安装前端依赖
cd frontend && npm install && cd ..

# 后端
uv run python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend

# 前端 (另一个终端)
cd frontend && npm run dev
```

</details>

### 配置 API 密钥

启动后在前端「设置」页面配置 API Key，或编辑 `data_folder/secrets.yaml`：

```yaml
llm_api_key: "your-api-key-here"
llm_base_url: "https://api.example.com/anthropic"
llm_model_type: "anthropic"
resume_language: "zh"
system_language: "zh"
```

> **优先级**: 前端设置 → `secrets.yaml` → `config.py`

---

## 📖 使用说明

### 📄 生成简历
1. 在左侧导航点击「生成简历」
2. 配置 API Key、模型类型、简历语言
3. 选择简历样式模板（5 种可选）
4. 可选：粘贴职位描述生成定制简历
5. 点击「生成简历」，等待 ~30 秒
6. 下载 PDF

### 📋 面试准备
1. 点击「面试准备」
2. 粘贴目标职位描述 (JD)
3. 选择面试类型、设置问题数量
4. 点击「生成面试准备报告」
5. 查看 Markdown 报告并下载

### 🤖 模拟面试
1. 点击「模拟面试」
2. 配置公司、岗位、面试类型、面试官风格
3. 粘贴简历和 JD
4. 点击「开始面试」
5. 多轮对话，AI 面试官会追问
6. 点击「结束面试」生成评估报告

### 📚 历史记录
查看并下载之前生成的所有简历和报告。

### ⚙️ 设置
配置 API Key、模型、语言等，并可直接编辑简历 YAML 内容。

---

## 🎨 样式模板

| 模板名称 | 风格 |
|---------|------|
| `cloyola` | 简洁专业 |
| `josylad_blue` | 蓝色商务 |
| `josylad_grey` | 灰色简约 |
| `krishnavalliappan` | 现代技术 |
| `samodum_bold` | 醒目粗体 |

---

## 📊 性能指标

| 指标 | 数值 |
|------|------|
| 普通简历生成 | ~30 秒 (1 次 LLM 调用) |
| 定制简历生成 | ~30 秒 (2 次 LLM 调用) |
| 面试准备报告 | ~15-20 秒 |
| 模拟面试响应 | ~3-5 秒/轮 |
| 简历 PDF 生成 | ~5 秒 |

---

## 🔧 问题排查

**Q: 生成的简历内容太简单？**
A: 在设置中增加 `max_tokens` 值（推荐 4096 或更高）。

**Q: 401 认证错误？**
A: 确认 `config.py` 中 `ANTHROPIC_AUTH_TOKEN` 已正确填写。

**Q: PDF 生成失败？**
A: 确保 Chrome 已安装且支持 headless 模式。Windows 上需要 Chrome 90+。

**Q: CSS 文件读取错误 (GBK)？**
A: 已在最新版修复，确保使用 `encoding="utf-8"`。

**Q: 模拟面试无响应？**
A: 检查 API Key 是否有效，查看终端日志。

---

## 🤝 贡献指南

欢迎贡献！请遵循以下流程：

1. Fork 仓库
2. 创建功能分支 (`git checkout -b feat/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feat/amazing-feature`)
5. 创建 Pull Request

提交信息规范：
- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `style:` 代码格式
- `refactor:` 重构
- `test:` 测试
- `chore:` 构建/工具

---

## 📜 License

[MIT License](LICENSE)

---

## 🔗 相关链接

| 资源 | 链接 |
|------|------|
| GitHub 仓库 | https://github.com/yi-wang-2/Buping_Job_Seeker_Assistant |
| 参考项目 (paper-ppt-agent) | https://github.com/CRui5in/paper-ppt-agent |
| FastAPI | https://fastapi.tiangolo.com/ |
| React | https://react.dev/ |
| Vite | https://vitejs.dev/ |
| LangChain | https://python.langchain.com/ |
| Pydantic | https://docs.pydantic.dev/ |
| Anthropic API | https://docs.anthropic.com/ |

---

## 🙏 致谢

本项目基于开源项目 [Jobs_Applier_AI_Agent_AIHawk](https://github.com/feder-cr/Jobs_Applier_AI_Agent_AIHawk) 开发，感谢原作者 [feder-cr](https://github.com/feder-cr) 的开源贡献。

在此基础上扩展了：
- 中文简历支持
- 模拟面试模块
- 面试准备模块
- API Key Fallback 机制
- 性能优化（LLM 调用合并）

---

**Made with ❤️ by yi-wang-2**
