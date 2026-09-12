# 不平 - 智能求职助手

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19+-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-6+-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![uv](https://img.shields.io/badge/uv-powered-DE5FE9?logo=astral&logoColor=white)](https://docs.astral.sh/uv/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 在线体验

GPT 部署版本：[立即访问](https://buping-job-assistant.daniel26yw.chatgpt.site/)

> **人生之路总是坎坷，这也造就了我们不平凡的人生.**

AI 求职助手是一个基于大语言模型 (LLM) 的智能求职辅助工具。覆盖从简历优化、岗位匹配、面试准备到职业发展的完整求职周期。

> **English version**: [README_EN.md](README_EN.md)

---

## ✨ 核心功能

### 🎯 已实现功能

- **📄 简历生成引擎**
  - 普通简历生成（基于 YAML）
  - JD 定制简历生成（针对职位描述优化）
  - 同一输入并行生成 2–3 个候选，按黄金样例叙事结构、项目完整性与事实覆盖评分择优
  - 支持“全新生成”和“在此版本上修改”，可按模块或单段经历选择重新生成范围；未选内容与版式作为上下文保留
  - 硬事实 Harness 原位校验姓名、教育、公司、职位、项目名称等锚点，不改写模型生成的整体文案结构
  - 支持一页/两页目标排版：先调整行距和模块间距，达到安全下限后仍超页才调用 LLM 压缩正文
  - 基于真实 PDF 页数反复校准，并在内容不足、超页或压缩可能影响完整性时给出明确提示
  - 支持 5 种专业样式模板
  - 详实量化内容，ATS 友好
  - 保存简历源内容时自动写入本地版本历史，支持后续查询与恢复

- **📋 实时简历预览**
  - 基于本地 YAML 的秒级预览（不调 LLM）
  - 切换样式/语言自动刷新
  - iframe 完整样式渲染

- **✏️ WYSIWYG 编辑器（iframe + designMode）**
  - **所见即所得**：编辑时与预览样式 100% 一致（颜色/字体/布局全部保留）
  - 18 个工具栏按钮：撤销/重做、3 级标题、粗体/斜体/下划线/删除线、有序/无序列表、引用、分隔线、链接、清除格式
  - 支持版式微调：可在编辑页调整行距和模块间距，并保存到最终 HTML/PDF
  - 使用原生 `<iframe>` + `designMode="on"`，样式隔离 0 依赖
  - 每 1.5s 自动保存到 localStorage（保留 5 个版本）
  - 支持 Ctrl+Z / Ctrl+Y / Ctrl+B / Ctrl+I / Ctrl+U 标准快捷键
  - 可编辑内容后导出 HTML

- **👀 可预览 + 可编辑**
  - 实时预览：本地 YAML 渲染，秒级切换样式/语言（无需 LLM）
  - 历史预览：下拉选择任意历史简历加载到预览框
  - 一键切换：预览模式（只读 iframe）↔ 编辑模式（iframe WYSIWYG）
  - 生成完成自动加载最新内容到预览

- **📤 简历文档上传解析**
  - 支持 PDF、Word (DOCX)、HTML、Markdown、YAML、LaTeX 等格式
  - 拖拽上传或点击选择，LLM 自动结构化提取，无需手动编辑
  - YAML/JSON 直接解析（零成本），其他格式走 LLM 智能识别
  - 解析结果自动填入 YAML 编辑器，用户审核后保存

- **📂 历史简历预览**
  - 下拉式历史选择器
  - 一键加载任意历史简历到预览
  - 生成完成后自动加载最新内容到预览

- **📋 面试准备模块**
  - 基于简历和 JD 自动生成面试准备报告
  - 可选择公共或用户私有知识库，使用能力 Blueprint、全文/向量混合检索和可追溯知识引用增强问题深度
  - 公共知识库通过版本固定的 Manifest 一键安装、更新或重建索引；源文件和 SQLite 索引仅生成在用户本机，不随仓库分发
  - 支持上传 Markdown、JSON、PDF、DOCX、ZIP，或从本地 Git/资料目录增量构建跨领域面试知识库
  - 包含：岗位分析、核心能力要求、候选人匹配度量化评分、技术问题、行为面试 (STAR)、简历深挖、准备清单
  - 问题数量按技术/岗位、简历深挖、行为问题合计控制，避免每个章节重复生成过多问题
  - 支持中英文双语
  - 支持 Markdown 与 PDF 报告下载，Markdown 表格在前端可横向滚动预览

- **🎭 模拟面试模块**
  - AI 扮演面试官，多轮对话模拟
  - 会话开始时固定知识索引与候选题池，依据能力覆盖和回答深度动态追问、升降难度并避免重复题
  - 5 种面试官风格：友善型 / 专业型 / 压力型 / 学术型 / 闲聊型
  - 自动轮次控制：开场 → 项目 → 技术 → 行为 → 反问 → 结束
  - 支持文字面试与语音面试双模式，面试中可随时切换
  - 打字机效果呈现面试官问题，通过统一 Context Manager 控制上下文预算，提升长轮次追问稳定性
  - 每轮回答后实时生成下一问，并在结束时生成多维度评估报告
  - 支持浏览器语音输入转写，语音模式下可用麦克风回答
  - 支持三档 TTS 播报方案：
    - **MiniMax API（推荐）**：需要 MiniMax 语音接口，流式播放，响应快，语音质量较好
    - **Kokoro 本地（均衡）**：本地生成，比 MiniMax 稍慢，质量略低但实时体验可接受
    - **ChatTTS 本地（高质量）**：语音质量高，但生成较慢；无 GPU 时会影响实时对话体验
  - 支持音色选择、语速调节、语音缓存与重播，避免重复生成相同语音
  - 面试结束后保存问答记录、评估报告，并提供 PDF 下载

- **🧭 求职记录面板**
  - 可为每条投递连接 Moka、飞书招聘、zhiye.com 或其他投递中心，使用本地独立 Chrome Profile 保存登录会话
  - 支持立即检查和可选定时间隔（4 / 6 / 8 / 12 / 24 小时），默认每 8 小时于 04:00 / 12:00 / 20:00 检查；错过时段后启动会补做最近一次
  - 状态识别采用“本地规则优先、LLM 兜底”：陌生网站或多志愿表格由 `job_status_classifier` 理解页面语义，结论必须引用页面原文且置信度达到 85%
  - LLM 兜底仅发送限长后的必要页面文本，支持 7 天 Prompt Cache，并记录识别方式、置信度、Token 与缓存命中情况
  - 支持同一企业三条并行申请逐岗识别；状态一致时更新汇总状态，不一致时保留岗位明细并等待用户核对
  - 登录失效、需要人机验证或状态变化时，可通过 SMTP 邮件和 Server酱推送到个人微信；定时检查按同一轮次和事件类型聚合通知（例如多个登录失效合并、进入初试单独成组），通知按事件去重，发送失败不影响状态保存
  - 不保存招聘网站密码，也不绕过短信、滑块或其他人机验证
  - 记录公司、岗位、地点、状态、链接、备注与面试笔记
  - 支持内联编辑、状态统计、JSON 导入/导出
  - 记录保存到 `data_folder/job_tracker/records.json`
  - 内置常见公司图标，并通过 `/api/job-tracker/icon` 提供静态访问

- **📡 岗位雷达**
  - 新增 `/job-radar` 页面，可直接读取公开只读的腾讯智能表格岗位源
  - 对岗位进行本地 SQLite 快照、去重及新增/变更/失效检测
  - 根据本地简历、目标岗位、地点偏好和排除项计算可解释匹配分，不消耗 LLM Token
  - 展示匹配技能、推荐理由和硬性风险，支持一键加入求职记录
  - 展示行业、招聘批次标签、内推码和招聘原文，支持收藏与“不感兴趣”状态
  - 每日推荐 3 家尚未收藏、忽略或投递的高匹配企业，并支持按公司类型、匹配度和招聘类型筛选
  - 支持腾讯文档智能表格与飞书多维表格岗位源，按公司、岗位、地点跨来源合并去重
  - 岗位库分为普通招聘、央国企招聘、考公考编三个场景；飞书记录按“企业性质”自动归类，考公考编入口暂时留空
  - 可在页面填写目标岗位、地点、行业、招聘/公司类型、关键词与排除项，并自定义各评分维度权重；偏好仅保存在本地 SQLite
  - 应用运行期间每天本地时间 06:00 自动同步最近使用的腾讯文档源；设置 `BUPING_JOB_RADAR_AUTO_SYNC=0` 可关闭
  - 后台默认每 30 分钟检查本地岗位不足 3 个且存在详情链接的企业，每轮自动补齐 1 家；可用 `BUPING_JOB_RADAR_AUTO_MATCH=0` 关闭，或通过 `BUPING_JOB_RADAR_MATCH_INTERVAL_SECONDS`、`BUPING_JOB_RADAR_MATCH_BATCH` 调整
  - 腾讯智能表格采用 Canvas 渲染且可能禁止导出；直接同步会在本地 Chrome 中读取页面渲染时已获授权的只读数据，不依赖导出或系统剪贴板

- **🧠 AI Runtime / Skills / Memory**
  - 统一 AI Runtime 集中处理 Pydantic 输入/输出校验、上下文预算、Provider 调用、缓存、长期记忆和追踪
  - 内置 Resume Writer、Mock Interviewer、Interview Coach、Text Rewriter、JD Analyzer、Skill Matcher、Career Advisor 和 Job Status Classifier
  - Skill 支持独立 Prompt/Schema 版本、Token Budget、temperature、缓存 TTL、启停和 Tool/Memory 白名单
  - 缓存命中时本次真实 Token 记为 0，并单独保留缓存节省量；Skill Run 由 Runtime 自动记录
  - 新增本地 SQLite 长期记忆与 Prompt Cache，可保存偏好、JD 归档、简历版本和缓存结果
  - 设置页提供「AI 记忆与隐私」开关，可开启/关闭长期记忆和本地缓存，并支持清空长期记忆

- **📈 AI 监控面板**
  - 新增 `/ai-monitoring` 页面
  - 汇总 Token、调用次数、成功率、平均/P95 延迟、缓存命中率、上下文压缩和长期记忆数量
  - 展示面试知识源、知识单元、检索次数、候选数和检索延迟等 RAG 指标
  - 支持按时间窗口查看趋势、按 Skill/模型聚合，以及最近调用明细

- **🎨 三列布局**
  - 左侧：API 配置 + 样式选择
  - 中间：简历预览（居中突出）
  - 右侧：职位描述

- **📊 生成进度条**
  - 后端记录排队、参数校验、候选生成、评分、硬事实校验、HTML 组装、PDF 分析、版式适配和文件保存等真实里程碑
  - 前端轮询展示细粒度进度与事件历史，失败时保留准确阶段信息
  - 生成期间锁定模板、生成方式和目标页数，避免切换配置覆盖当前进度和生成状态

- **🔧 可隐藏侧边栏**
  - 一键折叠/展开
  - 状态持久化到 localStorage
  - 移动端友好

- **⚙️ 配置与设置**
  - API Key / Base URL 配置面板
  - 模型类型选择（`anthropic` / `openai`）
  - 简历语言选择（中文/英文）
  - AI 记忆与 Prompt Cache 隐私控制
  - 求职状态通知：SMTP 邮件、Server酱个人微信、测试通知与凭证状态提示
  - 配置会写入 `data_folder/secrets.yaml`

- **📚 历史记录**
  - 生成的简历历史列表
  - 一键下载 PDF
  - 预览历史简历

### 🚧 规划中功能

- 岗位匹配分析（从网络爬虫池）
- 技能缺口分析
- 学习路径推荐

---

## 🛠️ 技术架构

| 组件 | 技术栈 |
|------|--------|
| 前端 | React 19 + Vite 6 + Tailwind CSS (端口 5173) |
| 后端 | FastAPI + Uvicorn (端口 8000) |
| 富文本编辑器 | 原生 iframe + designMode（零依赖） |
| 包管理 | uv (Python) + npm (Node.js) |
| LLM 引擎 | Anthropic 兼容 API (推荐 `MiniMax-M3`) |
| AI Runtime | Skill Registry + Context Manager + LLM Gateway |
| 记忆与缓存 | SQLite/WAL + Prompt Cache |
| 观测性 | JSONL Trace + AI Metrics API |
| 求职状态通知 | SMTP Email + Server酱微信推送 + SQLite 去重日志 |
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
│   ├── services/
│   │   ├── job_radar_service.py    # 岗位同步、去重、偏好评分与每日推荐
│   │   ├── job_followup_service.py # 招聘网站会话与状态识别
│   │   └── notification_service.py # SMTP / Server酱发送与事件去重
│   └── api/
│       ├── router.py            # API 路由汇总
│       └── endpoints/
│           ├── resume.py        # 简历生成 API
│           ├── interview.py     # 面试准备 + 模拟面试 API
│           ├── settings.py      # 配置管理 API
│           ├── history.py       # 历史记录 API
│           ├── job_tracker.py   # 求职记录 API
│           ├── job_radar.py     # 岗位雷达 API
│           ├── memory.py        # AI 记忆与缓存设置 API
│           ├── ai_metrics.py    # AI 调用监控 API
│           └── ai_skills.py     # JD 分析 / 技能匹配 / 职业建议 API
│
├── data_folder/                 # 用户数据 (实际数据，已脱敏)
│   ├── plain_text_resume.yaml   # 简历内容 (英文)
│   ├── plain_text_resume_zh.yaml # 简历内容 (中文)
│   ├── work_preferences.yaml    # 工作偏好
│   ├── work_preferences_zh.yaml
│   ├── job_tracker/             # 求职记录、公司图标与通知去重日志
│   ├── browser_profiles/        # 招聘网站本地 Chrome 登录会话
│   ├── job_radar.sqlite3        # 岗位快照、偏好和用户操作
│   ├── ai_memory.sqlite3        # 本地 AI 记忆 / 缓存 / 简历版本库
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
│       └── pages/               # 简历 / 面试 / 求职记录 / AI 监控 / 设置等页面
│
├── src/                         # 核心业务逻辑与 AI Runtime
│   └── libs/ai_engine/          # Context / Skills / Memory / Cache / Gateway
├── docs/ai_engine/              # AI 工程化设计与实施记录
├── scripts/benchmark_ai_engine.py # AI Runtime 性能基准脚本
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
uv sync --extra dev

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
minimax_tts_api_key: "your-minimax-tts-key"  # 可选；不填时复用 llm_api_key
resume_language: "zh"
system_language: "zh"
```

> **优先级**: 前端设置 → `secrets.yaml` → `config.py`

> **语音面试说明**：推荐使用 MiniMax TTS 流式播报，需要有效的 MiniMax API Key。
> 若未单独配置 `minimax_tts_api_key`，系统会尝试复用 `llm_api_key`。
> 本地 TTS 可选择 Kokoro 或 ChatTTS，其中 ChatTTS 更依赖 GPU。

### 配置邮件与个人微信通知

进入「设置 → 求职状态通知」配置两个渠道。个人微信通知使用 [Server酱](https://sct.ftqq.com/)，支持 `SCT...` 与新版 `sctp...` SendKey；系统不会登录或控制个人微信客户端。

邮件以 QQ 邮箱为例：SMTP 主机填写 `smtp.qq.com`，端口 `465`，加密选择 `SSL`，密码填写邮箱生成的 SMTP 授权码而不是登录密码。保存后点击「发送测试通知」验证两个渠道。

> 通知凭证仅保存在本地 `data_folder/secrets.yaml`，接口不会将授权码或 SendKey 返回前端，通知日志也不记录凭证明文。该配置文件本身为本地明文文件，请勿提交到 Git。

> 每日同步与自动跟进依赖后端进程运行；电脑关机或休眠时无法准时检查，应用恢复运行后会按调度逻辑补做当日检查。

---

### 📥 导入基本信息（两种方式）

在使用本工具前，需要先准备你的简历数据。提供 **手动填写** 和 **上传文档自动解析** 两种方式：

#### 方式一：手动填写 YAML 文件

直接编辑 `data_folder/plain_text_resume.yaml`（中文简历用 `plain_text_resume_zh.yaml`）：

```yaml
professional_summary: ""  # 可选：职业概述
personal_information:
  full_name: "Your Name"  # 推荐：简历展示时逐字使用，不由 AI 重排
  name: "Your"
  surname: "Name"
  email: "you@example.com"
  phone: "+1-555-123-4567"
  city: "San Francisco"
  country: "USA"
education_details:
  - education_level: "Bachelor's Degree"
    institution: "Stanford University"
    field_of_study: "Computer Science"
    research_direction: ""  # 可选：必须按事实填写，留空时不会显示
    research_topics: []      # 可选：仅填写真实研究课题
    year_of_completion: "2023"
    additional_info:
      college: "School of Engineering"
      study_mode: "Full-time"
      honors: ""
      relevant_courses: ""
    exam: {}  # 课程成绩统一放在教育经历下，不放在 additional_info 中
experience_details:
  - position: "Senior Engineer"
    company: "Google"
    employment_period: "2020 - Present"
    key_responsibilities:
      - responsibility: "Led team of 5 engineers"
projects:
  - name: "Open Source Project"
    description: "Description of the project"
```

完整字段说明见 [`assets/resume_schema.yaml`](assets/resume_schema.yaml)。

当前统一格式为 **Resume YAML v2**。上传文档、上传旧版 YAML/JSON 以及在设置页保存内容时都会自动标准化为 v2；旧字段 `degree/university/gpa/graduation_year` 和旧位置 `additional_info.exam` 会自动迁移，不会丢失原有数据。

#### 方式二：上传文档自动解析（推荐）

进入「设置」页面 → 「上传简历文档」区域，**拖拽或点击上传**任意格式的简历文件：

| 支持格式 | 解析方式 |
|---------|---------|
| `.yaml` / `.yml` / `.json` | 直接结构化解析（零成本） |
| `.pdf` / `.docx` / `.html` / `.md` / `.txt` | 提取纯文本 → LLM 结构化提取 |
| `.tex` / `.latex` | 智能去除 LaTeX 命令 |

**流程**：
1. 上传文件（最大 5MB）
2. 系统自动解析（2-30 秒，PDF/Word 需调用 LLM）
3. 解析结果自动填入下方 YAML 编辑器
4. 检查修改 → 点击「保存简历内容」
5. 简历数据写入 `data_folder/plain_text_resume*.yaml`

> **小贴士**：上传前请在设置页面填写 API Key（解析 PDF/DOCX 时需要 LLM 调用）；
> YAML/JSON/TXT 文件无需 API Key 即可直接解析。

---

## 📖 使用说明

### 📄 生成简历
1. 在左侧导航点击「生成简历」
2. 配置 API Key、模型类型、简历语言
3. 选择简历样式模板（5 种可选）
4. 可选：粘贴职位描述生成定制简历
5. 点击「生成简历」，等待 ~30 秒
6. 下载 PDF
7. 保存过的简历源内容会进入本地版本历史，可通过 `/api/resume/versions` 查询并恢复

### 👀 实时预览 + ✏️ 在线编辑

简历生成后支持**完整所见即所得**的二次编辑流程：

1. **实时预览**：左侧切换样式/语言时，预览自动刷新（不调 LLM，秒级响应）
2. **生成后自动预览**：简历生成完毕，自动加载到预览框，无需手动操作
3. **历史预览**：右上角下拉选择任意历史简历加载到预览
4. **切换编辑模式**：点击「编辑模式」按钮，预览框变为 WYSIWYG 编辑器
5. **所见即所得编辑**：在 iframe 中直接修改文字、格式、列表、链接——所见即所得
6. **版式微调**：工具栏提供「行距」和「模块」滑块，可调整整体信息密度
7. **自动保存**：修改后 1.5s 自动保存到 localStorage
8. **保存/重置**：底部「保存」按钮提交修改，「重置」按钮放弃所有修改
9. **快捷键**：支持 Ctrl+Z/Y（撤销/重做）、Ctrl+B/I/U（粗体/斜体/下划线）

> **技术说明**：编辑器使用原生 `<iframe>` + `document.designMode = "on"` 实现，
> 与 WordPress 古腾堡、Notion 早期编辑器同源。样式 100% 保真，
> 删除了原 TipTap 依赖，bundle 体积减少 113KB。编辑后的内容会以完整 HTML 文档保存，
> 因此版式参数会同步影响后端 PDF 生成。

### 📋 面试准备
1. 点击「面试准备」
2. 粘贴目标职位描述 (JD)
3. 展开「面试知识库」，可一键安装版本固定的公共知识库，也可上传自己的 Markdown、JSON、PDF、DOCX、ZIP 资料
4. 选择面试类型、设置问题数量
5. 点击「生成面试准备报告」
6. 查看岗位分析、候选人匹配度评分、提升计划、面试题及知识引用
7. 下载 Markdown 或 PDF 报告

### 🤖 模拟面试
1. 点击「模拟面试」
2. 配置公司、岗位、面试类型、面试官风格
3. 粘贴简历和 JD
4. 选择用于本场面试的知识源，并选择「开始文字面试」或「开始语音面试」
5. 多轮对话中，AI 面试官会结合上下文追问；顶部可随时在「文字 / 语音」之间切换
6. 语音模式下可选择 TTS 方案：
   - **MiniMax API（推荐）**：需要 MiniMax 接口，流式播报，速度快且语音质量不错
   - **Kokoro 本地（均衡）**：本地生成，速度和质量较均衡
   - **ChatTTS 本地（高质量）**：语音质量更高，但生成较慢，建议配合 GPU 使用
7. 可调节 MiniMax 音色和语速；重播会优先使用缓存，不重复生成
8. 可使用浏览器语音输入转写回答，也可以直接键盘输入
9. 点击「结束面试」生成评估报告，并可下载 PDF

### 🧭 求职记录
1. 点击「求职记录」
2. 录入公司、岗位、地点、状态、链接和备注
3. 在表格中直接编辑状态、链接或笔记
4. 点击盾牌按钮连接招聘网站；在普通 Chrome 中自行完成登录和验证后关闭窗口并确认
5. 可在页面顶部选择 4 / 6 / 8 / 12 / 24 小时检查间隔；默认 8 小时，对应 04:00、12:00、20:00
6. 可为每条记录启用定时自动跟进，以及“本地规则失败时使用 AI 兜底”
7. 检查结果会显示网站原文、识别方式、LLM 置信度和本次 Token；多志愿页面自动交给 LLM 解析申请级状态
8. 在「设置 → 求职状态通知」配置邮件和个人微信后，登录失效、人机验证或状态变化会自动提醒
9. 使用 JSON 导入/导出备份记录；数据保存在 `data_folder/job_tracker/records.json`

### 📡 岗位雷达

1. 点击「岗位雷达」，填写腾讯智能表格链接并同步岗位
2. 在“我的求职偏好”中配置目标岗位、地点、行业、招聘类型、关键词和评分权重
3. 查看每天 3 家高匹配企业，并按公司类型、匹配度和招聘类型筛选
4. 可收藏、不感兴趣或确认信息后加入求职记录；已操作或已投递岗位不会持续占用每日推荐
5. 应用运行期间每天 06:00 自动同步最近使用的数据源，并通过本地 SQLite 去重

### 📈 AI 监控
1. 点击「AI 监控」
2. 查看最近 1 / 7 / 30 / 90 天的 Token、调用、延迟、缓存和记忆指标
3. 通过 Skill、模型和最近调用明细定位成本或性能异常

### 📚 历史记录
查看并下载之前生成的所有简历和报告。

### ⚙️ 设置
配置 API Key、模型、语言等，并可直接编辑简历 YAML 内容。也可以在「AI 记忆与隐私」中开启/关闭长期记忆和 Prompt Cache，或清空本地长期记忆。

---

## 🎨 样式模板

| 模板名称 | 风格 |
|---------|------|
| `cloyola` | 简洁专业 |
| `josylad_blue` | 蓝色商务，已压缩行距和模块间距以提升信息密度 |
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
A: 优先检查设置页或 `data_folder/secrets.yaml` 中的 API Key、Base URL、协议是否匹配。
系统会优先使用用户配置，其次才回退到 `config.py` 中的默认配置。

**Q: PDF 生成失败？**
A: 确保 Chrome 已安装且支持 headless 模式。Windows 上需要 Chrome 90+。

**Q: CSS 文件读取错误 (GBK)？**
A: 已在最新版修复，确保使用 `encoding="utf-8"`。

**Q: 模拟面试无响应？**
A: 检查 API Key 是否有效，查看终端日志。

**Q: 编辑器看不到样式（颜色/字体/布局）？**
A: 2026-06-19 起已改用 iframe + designMode 实现，编辑时样式 100% 与预览一致。
   请确保 `frontend/src/components/editor/EditableResumePreview.tsx` 已更新到最新版本。

**Q: PDF 在模块中间分页，或模块整体跳到下一页？**
A: 当前 PDF 生成会保护二级小模块（如 `.entry`、技术栈、语言与其他、列表块）不被拆开；
一级 `section` 允许跨页，避免整个大模块跳页造成大面积空白。若单个小模块超过一页，Chrome 仍会强制分页。

**Q: Modern Blue 超过两页？**
A: Modern Blue 已压缩默认行距、模块间距、标题间距和打印样式。仍超页时，可在编辑模式用「行距」和「模块」滑块进一步压缩。

**Q: 编辑时中文显示为乱码？**
A: 旧版使用 PowerShell 写入时可能触发 GBK 编码，请用 UTF-8 (无 BOM) 重新写入文件：
   ```powershell
   [System.IO.File]::WriteAllText(
     "path/to/file.tsx",
       $content,
       [System.Text.UTF8Encoding]::new($false)
   )
   ```

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
