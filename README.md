# AI Job Assistant Agent - 智能求职助手

AI求职助手是一个基于大语言模型(LLM)的智能求职辅助工具，定位不止于简历生成，而是成为求职全流程的智能助手，覆盖从简历优化、岗位匹配、面试准备到职业发展的完整求职周期。

## 功能架构

### 1. 简历生成与优化模块
- **智能简历分析**: ATS兼容性检测，识别简历中的关键词缺失和格式问题
- **个性化内容建议**: 基于目标岗位JD，智能优化简历内容
- **成就量化与故事化**: 将工作经历转化为可量化的成就陈述，增强竞争力

### 2. 岗位匹配模块
- **智能岗位推荐**: 基于用户技能库与简历，进行技能-岗位匹配度分析
- **公司文化适配度评估**: 分析公司价值观与个人偏好的匹配程度
- **薪资范围预测**: 根据岗位、公司、地区预测合理薪资范围

### 3. 面试准备模块
- **个性化面试问题生成**: 根据简历和JD生成针对性的面试题库
- **模拟面试对话**: AI模拟面试官进行实时对话练习
- **行为面试(STAR法则)指导**: 提供STAR法则指导与案例库

### 4. 申请跟踪模块
- **申请进度管理**: 追踪每个岗位的申请状态和时间线
- **跟进提醒系统**: 智能提醒面试时间点、感谢信发送时机
- **拒绝原因分析与改进建议**: 分析被拒原因并提供针对性改进方案

### 5. 职业发展模块
- **技能缺口分析**: 对比目标岗位要求与当前技能水平
- **学习路径推荐**: 推荐个性化学习资源与成长路径
- **行业趋势洞察**: 追踪行业动态，提供职业发展建议

## 技术架构

- **前端**: Gradio Web UI (端口 7860)
- **LLM引擎**: MiniMax-M2.7 (通过Anthropic兼容API)
- **PDF生成**: Selenium + Chrome DevTools Protocol
- **Python版本**: 3.11+

## 目录结构

`
├── main.py              # 主程序入口
├── app_ui.py            # Gradio Web界面
├── config.py            # 配置文件
├── requirements.txt     # Python依赖
├── data_folder/         # 用户数据文件夹
│   ├── plain_text_resume.yaml  # 简历内容
│   ├── secrets.yaml     # API密钥配置
│   └── work_preferences.yaml   # 工作偏好设置
├── src/
│   ├── llm_manager.py           # LLM管理器
│   ├── resume_and_cover_builder/  # 简历生成模块
│   │   ├── resume_generator.py    # 简历生成器
│   │   ├── cover_letter_generator.py  # 求职信生成
│   │   └── style_manager.py      # 样式管理
│   ├── job.py                   # 职位相关类
│   ├── job_application_saver.py  # 申请跟踪模块
│   └── jobContext.py             # 求职上下文管理
└── assets/             # 静态资源
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置API密钥

编辑 data_folder/secrets.yaml:

```yaml
api_key_name: your-api-key-name
api_key: your-api-key
```

### 3. 配置简历内容

编辑 data_folder/plain_text_resume.yaml:

```yaml
first_name: 张
last_name: 三
title: 软件工程师
email: zhang@example.com
phone: "+86 13800000000"
location: 北京
```

### 4. 运行程序

```bash
python main.py
```

访问 http://localhost:7860 打开Web界面。

## 使用说明

### Tab 1: 生成简历 (简历生成与优化)

1. 在左侧粘贴职位描述(JD)
2. 选择简历样式模板
3. 点击"生成AI简历"
4. 等待生成完成，点击下载PDF

**其他简历功能 (待开发)**
- ATS兼容性检测与分析
- 基于JD的个性化内容建议
- 成就量化与故事化优化

### Tab 2: 生成定制简历 (简历生成与优化)

1. 粘贴Job Description
2. 选择样式模板
3. 点击"生成定制简历"
4. 可预览和下载结果

### Tab 3: 岗位匹配 (待开发)

- 智能岗位推荐与技能匹配度分析
- 公司文化适配度评估
- 薪资范围预测

### Tab 4: 面试准备 (待开发)

- 个性化面试问题生成
- 模拟面试对话练习
- STAR法则指导与案例库

### Tab 5: 申请跟踪 (待开发)

- 申请进度管理
- 跟进提醒系统
- 拒绝原因分析与改进建议

### Tab 6: 职业发展 (待开发)

- 技能缺口分析
- 学习路径推荐
- 行业趋势洞察

### Tab 7: 历史记录

查看之前生成的简历记录。

### Tab 8: 设置

配置LLM参数，如max_tokens等。

## 配置说明

### secrets.yaml

| 参数 | 说明 |
|------|------|
| api_key_name | API密钥名称 |
| api_key | API密钥值 |

### work_preferences.yaml

| 参数 | 说明 |
|------|------|
| suggest_thinking | 是否显示思考建议 |

## 样式模板

| 模板名称 | 说明 |
|---------|------|
| cloyola | 简洁专业风格 |
| josylad_blue | 蓝色商务风格 |
| josylad_grey | 灰色简约风格 |
| krishnavalliappan | 现代技术风格 |
| samodum_bold | 醒目粗体风格 |

## 问题排查

**Q: 生成的简历内容太简单？**
A: 尝试在设置中增加 max_tokens 值（当前默认4096）

**Q: 样式选择无法点击？**
A: 已修复，使用Radio组件替代Dropdown

**Q: PDF生成失败？**
A: 确保Chrome已安装且版本支持headless模式

## License

MIT License
