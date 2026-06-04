# AI Job Assistant Agent (Buping) - Intelligent Job Seeker Assistant

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Gradio](https://img.shields.io/badge/UI-Gradio-orange.svg)](https://www.gradio.app/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Bumps on the road forge an extraordinary life.**

An intelligent job seeker assistant powered by Large Language Models (LLM). It covers the entire job hunting cycle from resume optimization, job matching, interview preparation to career development.

> **中文版文档**: [README.md](README.md)

---

## ✨ Core Features

### 🎯 Implemented Features

- **📄 Resume Generation Engine**
  - Standard resume generation (YAML-based)
  - JD-customized resume generation (optimized for specific job descriptions)
  - Single LLM call generates complete resume (~30 seconds)
  - Supports 5 professional style templates
  - Detailed quantitative content, ATS-friendly

- **📋 Interview Preparation Module**
  - Auto-generate interview prep reports based on resume and JD
  - Includes: Technical questions, Behavioral interview (STAR), Resume deep-dive, Prep checklist
  - Bilingual support (Chinese/English)
  - Markdown report export

- **🎭 Mock Interview Module**
  - AI plays the interviewer with multi-turn dialogue simulation
  - 5 interviewer styles: Friendly / Professional / Pressure / Academic / Casual
  - Auto round control: Opening → Project → Technical → Behavioral → Q&A → Closing
  - Multi-dimensional evaluation report at the end

- **⚙️ Configuration & Settings**
  - API Key configuration panel
  - Multi-language support (Chinese/English resumes and system)
  - Adjustable max_tokens (default 4096)
  - Model selection

- **📚 History**
  - List of generated resumes
  - One-click PDF download

### 🚧 Planned Features

- Job matching analysis
- Application tracking
- Skill gap analysis
- Learning path recommendations

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | Gradio Web UI (Port 7860) |
| LLM Engine | Anthropic-compatible API (Recommended `MiniMax-M3`) |
| PDF Generation | Selenium + Chrome DevTools Protocol |
| Data Validation | Pydantic v2 |
| LLM Framework | LangChain |
| Python Version | 3.11+ |

---

## 📁 Project Structure

```
Jobs_Applier_AI_Agent_AIHawk-main/
├── app_ui.py                    # Gradio Web UI entry point
├── main.py                      # Main program entry
├── config.py                    # Global configuration (API Key, etc.)
├── requirements.txt             # Python dependencies
├── pytest.ini                   # Pytest configuration
├── .gitignore                   # Git ignore rules
│
├── data_folder/                 # User data (real data, desensitized)
│   ├── plain_text_resume.yaml
│   ├── plain_text_resume_zh.yaml
│   ├── work_preferences.yaml
│   ├── work_preferences_zh.yaml
│   └── secrets.yaml             # API Key template
│
├── data_folder_example/         # User data examples
│   ├── plain_text_resume.yaml
│   ├── resume_liam_murphy.txt
│   ├── work_preferences.yaml
│   └── secrets.yaml
│
├── src/
│   ├── __init__.py
│   ├── job.py
│   ├── jobContext.py
│   ├── job_application_saver.py
│   ├── logging.py
│   ├── resume_schemas/          # Pydantic models for resume
│   ├── utils/                   # Utility modules
│   └── libs/
│       ├── llm_manager.py
│       ├── resume_and_cover_builder/  # Resume and cover letter generation
│       └── interview_prep/           # Interview module ⭐
│
├── tests/                       # Test suite
│   ├── __init__.py
│   ├── test_smoke.py
│   └── test_imports.py
│
└── assets/                      # Static assets
    └── resume_schema.yaml
```

---

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone git@github.com:yi-wang-2/Buping_Job_Seeker_Assistant.git
cd Buping_Job_Seeker_Assistant
```

### 2. Create a Virtual Environment (Recommended)

```bash
conda create -n jobagent python=3.11
conda activate jobagent
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure API Key

Edit `config.py` with your LLM API configuration:

```python
# Anthropic-compatible API
ANTHROPIC_AUTH_TOKEN = "your-api-key-here"
ANTHROPIC_BASE_URL = "https://api.example.com/anthropic"
ANTHROPIC_MODEL = "MiniMax-M3"
```

Or edit `data_folder/secrets.yaml`:

```yaml
llm_api_key: "your-api-key-here"
llm_base_url: "https://api.example.com/anthropic"
llm_model_type: "anthropic"
resume_language: "zh"
system_language: "zh"
```

> **Priority**: User input → `config.py` → `secrets.yaml`

### 5. Prepare Resume Content

Edit `data_folder/plain_text_resume.yaml`:

```yaml
first_name: "John"
last_name: "Doe"
title: "Senior Software Engineer"
email: "john@example.com"
phone: "+1 555-0100"
location: "San Francisco"
summary: "5 years of Python backend development experience..."
```

### 6. Launch the Application

```bash
python app_ui.py
```

Visit http://localhost:7860 to open the Web UI.

---

## 📖 Usage

### Tab 1: Generate Resume
1. Select a resume style template (5 options)
2. Click "Generate AI Resume"
3. Wait ~30 seconds
4. Preview / Download PDF

### Tab 2: Customized Resume
1. Paste target job description (JD)
2. Select a style template
3. Click "Generate Customized Resume"
4. LLM will optimize resume content based on JD

### Tab 3: Interview Preparation
1. Paste resume and JD
2. Set number of questions (3-20)
3. Select language
4. Click "Generate Interview Prep Report"
5. Download Markdown report

### Tab 4: Mock Interview
1. Configure company, position, interview type
2. Select interviewer style (5 options)
3. Paste resume and JD
4. Click "Start Interview"
5. Multi-turn dialogue, AI interviewer will follow up
6. Click "End Interview" to generate evaluation report

### Tab 5: History
View all previously generated resumes.

### Tab 6: Settings
Configure API Key, model, max_tokens, etc.

---

## 🎨 Style Templates

| Template | Style |
|----------|-------|
| `cloyola` | Clean Professional |
| `josylad_blue` | Blue Business |
| `josylad_grey` | Grey Minimalist |
| `krishnavalliappan` | Modern Tech |
| `samodum_bold` | Bold Striking |

---

## 📊 Performance

| Metric | Value |
|--------|-------|
| Standard resume generation | ~30s (1 LLM call) |
| Customized resume generation | ~30s (2 LLM calls) |
| Interview prep report | ~15-20s |
| Mock interview response | ~3-5s/round |
| Resume PDF generation | ~5s |

---

## 🧪 Testing

```bash
pytest tests/ -v
```

11 tests covering project structure, file existence, and module imports.

---

## 🔧 Troubleshooting

**Q: Generated resume content is too simple?**
A: Increase `max_tokens` in settings (recommended 4096 or higher).

**Q: 401 authentication error?**
A: Confirm `ANTHROPIC_AUTH_TOKEN` in `config.py` is correctly set.

**Q: PDF generation failed?**
A: Ensure Chrome is installed and supports headless mode. Windows requires Chrome 90+.

**Q: CSS file reading error (GBK)?**
A: Fixed in latest version, ensure `encoding="utf-8"` is used.

**Q: Mock interview not responding?**
A: Check if API Key is valid, see terminal logs.

---

## 🤝 Contributing

Contributions are welcome! Please follow this workflow:

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feat/amazing-feature`)
5. Create a Pull Request

Commit message convention:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation update
- `style:` Code formatting
- `refactor:` Refactor
- `test:` Tests
- `chore:` Build/tools

---

## 📜 License

[MIT License](LICENSE)

---

## 🔗 Related Links

| Resource | Link |
|----------|------|
| GitHub Repository | https://github.com/yi-wang-2/Buping_Job_Seeker_Assistant |
| Reference (paper-ppt-agent) | https://github.com/CRui5in/paper-ppt-agent |
| Gradio Docs | https://www.gradio.app/docs/ |
| LangChain | https://python.langchain.com/ |
| Pydantic | https://docs.pydantic.dev/ |
| Anthropic API | https://docs.anthropic.com/ |

---

## 🙏 Acknowledgments

This project is based on the open source project [Jobs_Applier_AI_Agent_AIHawk](https://github.com/feder-cr/Jobs_Applier_AI_Agent_AIHawk). Thanks to the original author [feder-cr](https://github.com/feder-cr) for the contribution.

Extensions on top of the original:
- Chinese resume support
- Mock interview module
- Interview preparation module
- API Key Fallback mechanism
- Performance optimization (LLM call merging)

---

**Made with ❤️ by yi-wang-2**
