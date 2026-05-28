# AI Resume Generator - 待办事项

最后更新: 2026-05-28

## ✅ 已完成

- [x] 样式选择修复 - Dropdown 改为 Radio 组件解决无法点击问题
- [x] 简历内容优化 - max_tokens 从 1024 增加到 4096
- [x] README 更新 - 写入了完整的中文项目文档
- [x] 配置面板 - API Key、模型选择功能
- [x] 历史记录 - Tab 3 显示生成的简历列表
- [x] PDF下载 - File组件实现一键下载
- [x] 简历语言选择功能 - 支持中文或英文，默认中文
- [x] 系统语言选择功能 - 默认中文界面
- [x] 合并生成/定制简历标签 - 统一为一个 Tab，有职位描述则定制
- [x] 带职位描述的简历生成修复 - 直接调用 create_resume_job_description_text()
- [x] **API Content Block 解析问题** (2026-05-28) - 创建 ContentBlockParser 替代 StrOutputParser，解决 thinking 块内容泄漏到简历的问题
- [x] **中文 YAML 验证修复** (2026-05-28) - 修改 resume.py，将 HttpUrl 改为 str 类型，移除 zip_code 的 min_length 约束，添加 wechat 字段支持

---

## 🐛 问题修复记录

### 问题 1: 简历生成包含 prompt 模板乱码

**现象**: 生成的简历 PDF 中包含大量乱码，看起来像把 prompt 模板也写进去了

**根因**: `StrOutputParser()` 无法正确处理 API 返回的 content 列表结构（包含 `thinking` 和 `text` 两种块）。当 API 返回 thinking 块时，`str()` 转换会把完整 prompt 模板也包含进去。

**修复方案**:
```python
class ContentBlockParser(BaseOutputParser):
    """只提取 type='text' 的内容块，过滤掉 thinking 块"""
    def parse(self, result):
        if isinstance(result, list):
            text_parts = []
            for block in result:
                if isinstance(block, dict) and block.get('type') == 'text':
                    text_parts.append(block.get('text', ''))
            return ''.join(text_parts)
        return str(result)
```

**修复文件**: `src/libs/resume_and_cover_builder/llm/llm_generate_resume.py`

**影响**: 所有 7 个简历区块生成方法（header, education, work_experience, projects, achievements, certifications, additional_skills）

---

### 问题 2: 中文 YAML 解析 Pydantic 验证错误

**现象**: 
```
pydantic_core.ValidationError: 3 validation errors for Resume
personal_information.zip_code - String should have at least 5 characters
personal_information.linkedin - Input should be a valid URL, input is empty
projects.2.link - Input should be a valid URL, input is empty
```

**根因**: 
1. `zip_code` 有 `min_length=5` 约束，但中国邮编可能为空
2. `github`, `linkedin`, `Project.link` 使用 `HttpUrl` 类型，空字符串无法通过 URL 验证
3. 中文简历缺少 `wechat` 字段支持

**修复方案**:
```python
# resume.py - PersonalInformation 类
zip_code: Optional[str] = None  # 移除 min_length 约束
github: Optional[str] = None     # HttpUrl → str
linkedin: Optional[str] = None   # HttpUrl → str
wechat: Optional[str] = None      # 新增微信字段

# resume.py - Project 类
link: Optional[str] = None        # HttpUrl → str
```

**影响文件**: `src/resume_schemas/resume.py`

---

## 📊 简历生成流程分析 (2026-05-28)

### 一、整体数据流

```
User Input
    ↓
plain_text_resume.yaml (解析为 Resume 对象)
    ↓
[可选] job_description 文本
    ↓
┌─────────────────────────────────────────┐
│  LLMResumeJobDescription                 │
│  (如果提供 job_description)              │
│  - 总结职位描述关键要求                  │
└─────────────────────────────────────────┘
    ↓
并行生成 7 个简历区块 (各 1 次 LLM 调用)
    ↓
合并 HTML body
    ↓
注入 CSS 样式 → HTML 模板
    ↓
Chrome 浏览器转 PDF
```

### 二、模板化部分 (100% 固定)

| 模块 | 位置 | 说明 |
|------|------|------|
| **HTML 模板** | `template_base.py` | 固定结构 `{body}`, `{style_css}`, `{lang}` |
| **CSS 样式** | `resume_style/*.css` | 5 种内置样式 |
| **提示词结构** | `strings_*.py` | 各区块提示词模板 |
| **Section 顺序** | `llm_generate_resume.py` | header → education → work → projects → achievements → certs → skills |
| **PDF 转换** | `chrome_utils.py` | Selenium + Chrome headless |

### 三、AI 自由发挥部分 (可变)

| Section | LLM 调用 | 内容变化 |
|---------|----------|----------|
| `generate_header()` | 1次 | 根据个人信息格式化联系方式 |
| `generate_education_section()` | 1次 | 描述学历，**Tailored版会加入职位相关课程** |
| `generate_work_experience_section()` | 1次 | 描述工作经历，**Tailored版会强调相关技能** |
| `generate_projects_section()` | 1次 | 展示项目，**Tailored版会突出职位匹配度** |
| `generate_achievements_section()` | 1次 | 列出成就 |
| `generate_certifications_section()` | 1次 | 列出证书 |
| `generate_additional_skills_section()` | 1次 | 汇总语言、兴趣、技能 |
| `summarize_prompt_template` (Tailored) | 1次 | 总结职位描述关键要求 |

### 四、当前 LLM 调用次数

| 场景 | 调用次数 | 说明 |
|------|----------|------|
| **普通简历** | **7 次** | 并行执行 |
| **定制简历** | **8 次** | 7次 + 1次职位描述总结 |

### 五、优化空间

| # | 优化方向 | 收益 | 难度 |
|---|----------|------|------|
| 1 | **合并 LLM 调用** - 将多个区块合并到一次调用 | 减少 API 费用 + 加速生成 | 中 |
| 2 | **批量生成** - 单次调用生成多个相关区块 | 减少 token 消耗 | 中 |
| 3 | **缓存职位分析结果** - 如果重复投递同一家公司 | 避免重复总结 | 低 |
| 4 | **模板变量标准化** - 统一 prompt 中的占位符格式 | 提升可维护性 | 低 |
| 5 | **错误重试机制** - 某区块失败时单独重试 | 提升稳定性 | 中 |
| 6 | **流式输出预览** - 边生成边显示进度 | 改善 UX | 高 |

### 六、关键代码文件索引

| 功能 | 文件路径 |
|------|----------|
| 入口 | `app_ui.py` → `generate_resume()` |
| 简历解析 | `src/resume_schemas/resume.py` → `Resume` 类 |
| HTML 生成 | `src/libs/resume_and_cover_builder/resume_generator.py` |
| LLM 调用 | `src/libs/resume_and_cover_builder/llm/llm_generate_resume.py` |
| 职位描述定制 | `src/libs/resume_and_cover_builder/llm/llm_generate_resume_from_job.py` |
| 提示词模板 | `src/libs/resume_and_cover_builder/resume_prompt/strings_zh-cn.py` |
| PDF 转换 | `src/utils/chrome_utils.py` → `HTML_to_PDF()` |

---

## 🔍 YAML vs LLM 分工说明

### YAML 提供的是"原材料"（原始数据）

```yaml
# plain_text_resume.yaml 示例
experience_details:
  - company: "ABC公司"
    position: "高级Python开发工程师"
    start_date: "2020-01"
    end_date: "2023-06"
    description: "负责后端开发，使用Django和FastFramework"
    skills_acquired: ["Python", "Django", "PostgreSQL", "Redis"]
```

### LLM 做的"加工工作"（智能转换）

| 原材料 (YAML) | 加工后 (LLM输出) |
|--------------|-----------------|
| `Python` | `熟练使用 Python 进行后端开发，熟悉 Django/Flask 框架` |
| `Django` | `基于 Django 构建可扩展的 Web 应用，实现过日均 10 万 QPS 的 API 服务` |
| `PostgreSQL` | `精通 PostgreSQL 数据库设计与优化，能处理千万级数据` |
| 无数据 | `根据职位描述补充：『熟悉微服务架构，有 Docker/K8s 经验者优先』` |

### LLM 的核心作用

| # | 作用 | 说明 |
|---|------|------|
| 1 | **格式转换** | 原始文本 → ATS友好格式 |
| 2 | **量化呈现** | 模糊描述 → 具体数字 |
| 3 | **职位匹配** (Tailored) | 通用描述 → 定向优化 |
| 4 | **语言润色** | 口语化 → 专业表达 |

### 对比总结

| 方面 | YAML 数据 | LLM 作用 |
|------|----------|----------|
| **事实准确性** | ✅ 来源真实 | 仅转发，不编造 |
| **表达专业化** | ❌ 原始描述 | ✅ ATS优化 |
| **量化指标** | ❌ 模糊 | ✅ 精确数字 |
| **职位匹配** | ❌ 通用 | ✅ 定向突出 |
| **格式规范** | ❌ 自由格式 | ✅ HTML结构 |

### 核心结论

> **YAML 是"食材"，LLM 是"厨师"**
> - YAML 保证了信息的**真实性**（姓名、公司、日期等不可篡改）
> - LLM 负责**烹饪方式**（如何切块、调味、摆盘让招聘官爱吃）
> - LLM 不会编造你没做过的事，但会**更好地讲述你的故事**

---

## ⚠️ 待优化功能

| # | 功能 | 优先级 | 状态 |
|---|------|--------|------|
| 1 | 样式预览 | 中 | Radio已实现，待添加可视化CSS样式预览 |
| 2 | LLM 调用优化 | 中 | 当前普通简历7次调用，定制简历8次 |
| 3 | 历史记录搜索/筛选 | 低 | 待实现 |
| 4 | 职位分析结果缓存 | 低 | 避免重复分析同一职位描述 |
| 5 | **简历排版优化** | 中 | 当前CSS样式较基础，视觉效果待提升 |

## � 问题分析

### 问题 1: 简历排版优化方向

**当前问题**:
- CSS 样式基础，缺乏视觉层次感
- 字体、颜色、间距不够精致
- 各区块之间缺乏统一的视觉节奏

**优化方向**:
1. **CSS 样式升级** - 添加渐变色、阴影效果，优化字体层级
2. **内容布局优化** - 更好的信息密度控制，关键信息突出显示
3. **响应式设计** - 支持不同屏幕尺寸预览，打印友好格式
4. **样式预览功能** - 生成缩略图预览，实时切换不同样式

### 问题 2: 为何带 JD 的简历质量更高？

**现象观察**:
- 带职位描述(JD)生成的简历内容更丰富、更匹配
- 不带JD的简历显得泛泛、缺乏针对性

**可能原因**:

| # | 原因 | 说明 |
|---|------|------|
| 1 | **信息增量** | JD提供了额外上下文，LLM能更好地"理解"需要强调什么 |
| 2 | **Prompt 差异** | 带JD的prompt包含`job_description`相关上下文 |
| 3 | **内容填充** | 无JD时LLM只能依赖YAML原始数据，有限时创造性输出 |
| 4 | **Tailored vs Base** | 带JD走的是`LLMResumeJobDescription`路径，内容经过二次加工 |

**需要深入分析**:
- 对比两个路径的 prompt 差异
- 检查 `llm_generate_resume_from_job.py` 中的额外处理逻辑
- 验证是否是因为 prompt 长度不同导致的差异

---

## 📊 分析结论

### 问题 2 分析结果：为何带 JD 的简历质量更高？

**关键发现**：问题出在 **Prompt 模板差异**，不是 LLM 质量问题。

#### 对比分析

| 路径 | Prompt 变量 | 内容丰富度 |
|------|------------|----------|
| **Base (不带JD)** | `{education_details}` | 仅 YAML 数据，无额外上下文 |
| **Tailored (带JD)** | `{education_details}` + `{job_description}` | YAML数据 + JD上下文 |

#### 核心差异

**不带 JD 的 Prompt**:
```
- **My information:**  
  {education_details}
```
LLM 只能基于 YAML 数据生成，描述是"通用型"的。

**带 JD 的 Prompt**:
```
- **My information:**  
  {education_details}

- **Job Description:**  
  {job_description}
```
LLM 能看到职位描述，会：
1. **对齐技能** - 强调与 JD 相关的技能
2. **关键词优化** - 包含 JD 中的ATS关键词
3. **内容定制** - 调整描述语气和侧重点

#### 结论

> **信息量决定输出质量** - LLM 不是"更用心"，而是有更多上下文来发挥。
> 
> 这不是 bug，而是设计上的差异。如果想让基础简历也有更高质量，可以考虑：
> 1. 预设一些"默认职位方向"作为隐含上下文
> 2. 优化 Base 模式的 prompt，增加更详细的指令
> 3. 让用户即使不提供 JD 也选择一个目标职位类型（如"后端开发"、"数据科学"等）

### 问题 1：简历排版优化方向

**当前 CSS 样式分析**:

| 样式文件 | 特点 |
|---------|------|
| `style_cloyola.css` | 简洁风格 |
| `style_josylad_blue.css` | 蓝色商务 |
| `style_josylad_grey.css` | 灰色简约 |
| `style_krishnavalliappan.css` | 现代技术风格 |
| `style_samodum_bold.css` | 醒目粗体 |

**优化建议**:

1. **视觉层次**
   - 区分姓名、标题、正文的字体大小和粗细
   - 添加区块之间的分隔线或间距
   - 使用颜色渐变或图标增强可读性

2. **信息密度**
   - 关键信息（如姓名、职位）突出显示
   - 次要信息（如地址）适当缩小
   - 避免所有内容同等权重导致层次不清

3. **技术实现**
   - 添加 CSS 变量便于主题切换
   - 优化打印样式（@media print）
   - 考虑添加深色/浅色主题切换

- [ ] 考虑添加真正的WebSocket支持用于实时进度推送
- [ ] 样式模板缩略图预览功能
- [ ] 历史记录搜索/筛选功能
- [ ] 职位分析结果缓存机制 - 避免重复分析同一职位描述

## 🔧 当前配置

- LLM: MiniMax-M2.7 (Anthropic兼容API)
- max_tokens: 4096
- 样式模板: 5个 (cloyola, josylad_blue, josylad_grey, krishnavalliappan, samodum_bold)
- 服务端口: 7860

## 📝 备注

项目根目录: `D:\code\Jobs_Applier_AI_Agent_AIHawk-main`
关键文件:
- `app_ui.py` - Gradio Web界面
- `src/libs/resume_and_cover_builder/` - 简历生成模块
- `main.py` - 程序入口

## 🔗 相关文档

| 文档 | 路径 |
|------|------|
| 简历 YAML 格式 | `data_folder/plain_text_resume.yaml` |
| 中文简历 YAML | `data_folder/plain_text_resume_zh.yaml` |
| 样式模板目录 | `src/libs/resume_and_cover_builder/resume_style/` |
| LLM Prompt 模板 | `src/libs/resume_and_cover_builder/resume_prompt/strings_feder-cr.py` |

## 📌 Bug 修复索引

| # | 日期 | 问题描述 | 修复文件 |
|---|------|----------|----------|
| 1 | 2026-05-28 | 简历生成包含 prompt 乱码 | `llm_generate_resume.py` |
| 2 | 2026-05-28 | 中文 YAML Pydantic 验证失败 | `resume.py` |