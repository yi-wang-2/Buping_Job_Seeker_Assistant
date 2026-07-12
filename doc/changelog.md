# 更新记录 (Changelog)

来源：Notion《更新记录 (Changelog)》  
Notion 更新时间：2026-06-20  
本地同步：2026-07-10

## 2026-07-10 本地新增记录

### 简历排版与模板体验优化

- 中文简历技能结构从“其他技能”调整为“技术栈”和“语言与其他”。
- PDF 分页策略从保护整个 `section` 改为保护二级小模块。
- Cloyola Grey 去掉 `header` 和 `.entry` 阴影。
- Modern Blue 压缩行距、标题间距、模块间距和打印样式。
- 编辑页新增“行距”和“模块”滑块，可直接调整信息密度。
- 编辑器保存完整 HTML 文档，保证预览与后端 PDF 生成使用同一份样式。
- 修复 LLM API Key 优先级，用户设置优先于 `config.py` 默认 token。

验证：

```bash
pytest -q
npm.cmd run build
```

## 2026-06-19

### feat: 简历文档上传解析

用户可上传 PDF、Word、HTML、Markdown、YAML、LaTeX 等格式，系统自动解析为简历 YAML。

使用流程：

1. 进入“设置”页面。
2. 上传或拖拽简历文档。
3. 系统自动解析，生成 YAML 草稿。
4. 用户检查修改。
5. 点击“保存简历内容”。

新增后端端点：

| 端点 | 方法 | 功能 |
| --- | --- | --- |
| `/api/settings/upload-resume` | POST | 文件上传、格式解析、返回 YAML |

支持格式：

| 格式 | 解析方式 |
| --- | --- |
| `.yaml` / `.yml` | `yaml.safe_load` |
| `.json` | `yaml.safe_load` |
| `.txt` / `.md` | 直接解码文本 |
| `.pdf` | PyMuPDF 提取文本 |
| `.docx` | python-docx 提取段落 |
| `.html` / `.htm` | BeautifulSoup 去标签 |
| `.tex` / `.latex` | 去除 LaTeX 命令并保留正文 |

解析策略：

- Tier 1：YAML / JSON 直接解析，零成本。
- Tier 2：其他格式提取纯文本后用 LLM 结构化为 YAML。
- Tier 3：无 API Key 时启发式提取邮箱、电话、URL。

### refactor(editor): WYSIWYG 改用 iframe + designMode

动机：TipTap 编辑态无法完整保留预览页 CSS。  
方案：使用原生 `<iframe>` + `document.designMode = "on"`。

收益：

- 原始 HTML/CSS 原样加载。
- iframe sandbox 自动隔离样式。
- 删除 TipTap/ProseMirror 依赖。
- Bundle 体积减少约 113KB。

## 2026-06-16

### feat: 简历可视化预览 + 可编辑功能

- 简历 HTML 实时预览，不调用 LLM。
- iframe WYSIWYG 在线编辑。
- 历史预览，可加载过往生成简历。
- 支持下载 HTML 文件。
- 侧边栏可折叠并持久化。

## 2026-06-07

### fix: lazy-import inquirer and LLMParser

- `resume_facade.py` 中 `inquirer` 和 `LLMParser` 改为方法内部懒加载。
- 后端启动不再依赖 CLI 专用包。

## 2026-06-06

### UI 架构重构：Gradio -> Vite + React + FastAPI

| 项目 | 旧 | 新 |
| --- | --- | --- |
| 前端 | Gradio Python | React 19 + Vite 6 + TypeScript |
| 后端 | 直接函数调用 | FastAPI RESTful |
| 依赖 | pip + requirements.txt | uv + pyproject.toml |
| 启动 | `python app_ui.py` | `start-dev.bat` / `start-dev.sh` |
| 端口 | 7860 | 后端 8000 / 前端 5173 |

## 2026-06-04

### 新增模块：模拟面试

- AI 扮演面试官，基于候选人简历和 JD 生成问题。
- 支持多轮对话和深入追问。
- 支持 5 种面试官风格。
- 结束后生成评估报告。

## 2026-06-03

### 新增模块：面试准备

- 基于简历和职位描述自动生成面试准备报告。
- 支持自定义问题数量。
- 支持中英文双语。
- Markdown 格式输出。

## 2026-05-28

### 修复问题 1-3

- ContentBlockParser 过滤 thinking 块，避免 prompt 泄漏到简历。
- 中文 YAML 校验放宽 URL 和邮编字段。
- 简历生成从 7-8 次 LLM 调用合并为 1-2 次。
