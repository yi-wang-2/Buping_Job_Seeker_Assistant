# AI Job Assistant Agent (Buping) - 智能求职助手

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Gradio](https://img.shields.io/badge/UI-Gradio-orange.svg)](https://www.gradio.app/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Bumps on the road forge an extraordinary life.**

AI 求职助手是一个基于大语言模型 (LLM) 的智能求职辅助工具。覆盖从简历优化、岗位匹配、面试准备到职业发展的完整求职周期。

---

## ✨ 核心功能

### 🎯 已实现功能

- **📄 简历生成引擎**
  - 普通简历生成（基于 YAML）
  - JD 定制简历生成（针对职位描述优化）
  - 单次 LLM 调用生成完整简历（~30 秒）
  - 支持 5 种专业样式模板
  - 详实量化内容，ATS 友好

- **📋 面试准备模块**
  - 基于简历和 JD 自动生成面试准备报告
  - 包含：技术问题、行为面试 (STAR)、简历深挖、准备清单
  - 支持中英文双语
  - Markdown 报告导出

- **🎭 模拟面试模块**
  - AI 扮演面试官，多轮对话模拟
  - 5 种面试官风格：友善型 / 专业型 / 压力型 / 学术型 / 闲聊型
  - 自动轮次控制：开场 → 项目 → 技术 → 行为 → 反问 → 结束
  - 结束生成多维度评估报告

- **⚙️ 配置与设置**
  - API Key / Base URL 配置面板
  - 模型类型选择（`anthropic` / `openai`）
  - 简历语言选择（中文/英文）
  - 配置会写入 `data_folder/secrets.yaml`

- **📚 历史记录**
  - 生成的简历历史列表
  - 一键下载 PDF

### 🚧 规划中功能

- 岗位匹配分析
- 申请跟踪管理
- 技能缺口分析
- 学习路径推荐

---

## 🛠️ 技术架构

| 组件 | 技术栈 |
|------|--------|
| 前端 | Gradio Web UI (端口 7860) |
| LLM 引擎 | Anthropic 兼容 API (推荐 `MiniMax-M3`) |
| PDF 生成 | Selenium + Chrome DevTools Protocol |
| 数据验证 | Pydantic v2 |
| LLM 框架 | LangChain |
| Python 版本 | 3.11+ |

---

## 📁 目录结构

```
Buping_Job_Seeker_Assistant/
├── app_ui.py                    # Gradio Web 界面入口
├── main.py                      # 主程序入口
├── config.py                    # 全局配置 (API Key 等)
├── requirements.txt             # Python 依赖
├── .gitignore                   # Git 忽略规则
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
├── src/
│   ├── __init__.py
│   ├── job.py                   # 职位数据类
│   ├── jobContext.py            # 求职上下文
│   ├── job_application_saver.py # 申请跟踪
│   ├── logging.py               # 日志模块
│   ├── resume_schemas/          # 简历 Pydantic 模型
│   │   ├── resume.py
│   │   └── job_application_profile.py
│   ├── utils/                   # 工具模块
│   │   ├── chrome_utils.py      # Chrome 浏览器工具
│   │   └── constants.py
│   └── libs/
│       ├── llm_manager.py       # LLM 管理
│       ├── resume_and_cover_builder/  # 简历与求职信生成
│       │   ├── resume_generator.py
│       │   ├── resume_facade.py
│       │   ├── style_manager.py
│       │   ├── template_base.py
│       │   ├── template_base_zh.py
│       │   ├── utils.py
│       │   ├── config.py
│       │   ├── module_loader.py
│       │   ├── llm/                  # LLM 调用层
│       │   │   ├── llm_generate_resume.py
│       │   │   ├── llm_generate_resume_from_job.py
│       │   │   ├── llm_generate_cover_letter_from_job.py
│       │   │   └── llm_job_parser.py
│       │   ├── resume_prompt/        # 简历 Prompt 模板
│       │   ├── cover_letter_prompt/  # 求职信 Prompt 模板
│       │   └── resume_style/         # CSS 样式模板
│       └── interview_prep/           # 面试模块 ⭐
│           ├── __init__.py
│           ├── interview_generator.py  # 面试准备报告生成
│           └── mock_interview.py      # 模拟面试对话
│
└── assets/                      # 静态资源
    └── resume_schema.yaml
```

---

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone git@github.com:yi-wang-2/Buping_Job_Seeker_Assistant.git
cd Buping_Job_Seeker_Assistant
```

### 2. 创建虚拟环境（推荐）

```bash
conda create -n jobagent python=3.11
conda activate jobagent
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置 API 密钥

优先通过环境变量（或在项目根目录创建 `.env`）配置 LLM（避免把密钥写入并提交 `config.py`）：

~~~bash
# Anthropic 兼容 API
ANTHROPIC_AUTH_TOKEN="your-api-key-here"
ANTHROPIC_BASE_URL="https://api.example.com/anthropic"
ANTHROPIC_MODEL="MiniMax-M3"
~~~

或编辑 `data_folder/secrets.yaml`：

```yaml
llm_api_key: "your-api-key-here"
llm_base_url: "https://api.example.com/anthropic"
llm_model_type: "anthropic"
resume_language: "zh"
system_language: "zh"
```

> **优先级**: 用户输入 → `secrets.yaml` → `config.py`

### 5. 准备简历内容

编辑 `data_folder/plain_text_resume.yaml`：

```yaml
first_name: "张"
last_name: "三"
title: "高级软件工程师"
email: "zhangsan@example.com"
phone: "+86 13800000000"
location: "北京"
summary: "5 年 Python 后端开发经验..."
# ... 更多字段
```

可参考 `data_folder_example/plain_text_resume.yaml`。

### 6. 启动应用

```bash
python app_ui.py
```

访问 http://localhost:7860 打开 Web 界面。

---

## 📖 使用说明

### Tab 1: 生成简历
1. 选择简历样式模板（5 种可选）
2. 点击「生成 AI 简历」
3. 等待 ~30 秒
4. 预览 / 下载 PDF

### 定制简历（Tab 1 内）
在 Tab 1 粘贴目标职位描述 (JD) 后生成定制简历；留空则生成普通简历。
### Tab 3: 面试准备
1. 在 Tab 1 选择简历语言（中文/英文）
2. 在本页粘贴目标职位描述 (JD)
3. 设置问题数量（3-20）
4. 点击「生成面试准备报告」
5. 下载 Markdown 报告

### Tab 4: 模拟面试
1. 配置公司、岗位、面试类型
2. 选择面试官风格（5 种）
3. 粘贴简历和 JD
4. 点击「开始面试」
5. 多轮对话，AI 面试官会追问
6. 点击「结束面试」生成评估报告

### Tab 5: 历史记录
查看之前生成的所有简历。

### Tab 6: 设置
展示数据/输出目录信息，并可直接编辑本地简历 YAML（如 `data_folder/plain_text_resume_zh.yaml`）。

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
| Gradio 文档 | https://www.gradio.app/docs/ |
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
