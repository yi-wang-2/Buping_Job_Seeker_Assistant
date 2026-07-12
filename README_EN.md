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

- **📋 Real-Time Resume Preview**
  - Preview directly from local YAML data (no LLM call, sub-second response)
  - Auto-refresh on style/language change
  - Iframe-based, fully styled preview

- **✏️ WYSIWYG Editor (iframe + designMode)**
  - **What-You-See-Is-What-You-Get**: edit mode renders 100% identical styles to preview (colors/fonts/layout all preserved)
  - 18 toolbar buttons: undo/redo, 3 heading levels, bold/italic/underline/strikethrough, ordered/unordered lists, quote, divider, link, clear formatting
  - Layout controls: adjust line height and module spacing in edit mode; saved HTML/PDF keeps the same settings
  - Powered by native `<iframe>` + `designMode="on"` with zero editor dependencies
  - Auto-save to localStorage every 1.5s (keeps 5 versions)
  - Standard shortcuts: Ctrl+Z/Y (undo/redo), Ctrl+B/I/U (bold/italic/underline)
  - Export edited version as HTML

- **👀 Previewable + Editable**
  - Real-time preview: local YAML rendering, instant style/language switch (no LLM call)
  - History preview: dropdown to load any past resume into the preview
  - One-click toggle: Preview mode (read-only iframe) ↔ Edit mode (iframe WYSIWYG)
  - Auto-loads newly generated content into preview after completion

- **📤 Resume Document Upload & Parsing**
  - Supports PDF, Word (DOCX), HTML, Markdown, YAML, LaTeX formats
  - Drag-and-drop or click to upload — LLM-powered structured extraction
  - YAML/JSON parsed directly (zero cost); other formats parsed via LLM
  - Parsed result auto-fills the YAML editor for review before saving

- **📂 History Resume Preview**
  - Dropdown picker for all historical resumes
  - One-click load any past resume into the preview
  - Auto-load newly generated resume into preview after completion

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

- **🎨 3-Column Layout**
  - Left: API config + style picker
  - Center: Resume preview (prominent, centered)
  - Right: Job description

- **📊 Generation Progress Bar**
  - 5-stage visual progress (Parse → LLM → CSS → Chrome → Save)
  - Real-time feedback during 30-60s generation
  - Better UX than spinner-only

- **🔧 Collapsible Sidebar**
  - Hide/show sidebar with one click
  - State persisted to localStorage
  - Mobile-friendly

- **⚙️ Configuration & Settings**
  - API Key configuration panel
  - Multi-language support (Chinese/English resumes and system)
  - Adjustable max_tokens (default 4096)
  - Model selection

- **📚 History**
  - List of generated resumes
  - One-click PDF download
  - Preview historical resumes

### 🚧 Planned Features

- Job matching analysis (from the web crawler pool)
- Application tracking
- Skill gap analysis
- Learning path recommendations

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | React 19 + Vite 6 + Tailwind CSS (Port 5173) |
| Backend | FastAPI + Uvicorn (Port 8000) |
| Rich Text Editor | Native iframe + designMode (zero dependencies) |
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

### 5. Prepare Resume Content (Two Methods)

Before using this tool, you need to provide your resume data. Two methods are supported:

#### Method A: Edit YAML Manually

Edit `data_folder/plain_text_resume.yaml` directly:

```yaml
personal_information:
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
    year_of_completion: "2023"
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

See [`assets/resume_schema.yaml`](assets/resume_schema.yaml) for the full schema.

#### Method B: Upload Document (Recommended)

Open the **Settings** page → **Upload Resume Document** section, then **drag-and-drop or click to upload** any supported format:

| Supported Format | Parsing Method |
|-----------------|----------------|
| `.yaml` / `.yml` / `.json` | Direct structured parse (zero LLM cost) |
| `.pdf` / `.docx` / `.html` / `.md` / `.txt` | Extract text → LLM structured extraction |
| `.tex` / `.latex` | Smart LaTeX command stripping |

**Workflow**:
1. Upload a file (max 5 MB)
2. Auto-parse (2-30s; PDF/Word require LLM call)
3. Parsed YAML auto-fills the editor below
4. Review and edit → click "Save Resume Content"
5. Resume data is written to `data_folder/plain_text_resume*.yaml`

> **Tip**: Configure your API Key in the Settings page first (PDF/DOCX parsing requires LLM);
> YAML/JSON/TXT files parse without an API Key.

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

### 👀 Real-Time Preview + ✏️ WYSIWYG Editing

After a resume is generated, you can edit it directly with full WYSIWYG fidelity:

1. **Real-time preview**: Switch style/language from the left panel — preview refreshes instantly (no LLM call)
2. **Auto-preview after generation**: Newly generated resume loads into preview automatically
3. **History preview**: Top-right dropdown lists all historical resumes; click to load any into preview
4. **Switch to edit mode**: Click the "Edit Mode" button — preview becomes a WYSIWYG editor
5. **WYSIWYG editing**: Modify text/formatting/lists/links directly inside the iframe — what you see is what you get
6. **Layout controls**: Use the line-height and module-spacing sliders to adjust information density
7. **Auto-save**: Changes saved to localStorage 1.5s after the last edit
8. **Save / Reset**: Click "Save" to commit, "Reset" to discard all changes
9. **Shortcuts**: Ctrl+Z/Y (undo/redo), Ctrl+B/I/U (bold/italic/underline)

> **Technical Note**: The editor uses native `<iframe>` + `document.designMode = "on"`,
> the same approach used by WordPress Gutenberg and early Notion.
> 100% style fidelity; the previous TipTap dependency has been removed
> (bundle size reduced by 113KB). Edited resumes are saved as complete HTML
> documents, so layout controls are preserved when generating PDFs.

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
| `josylad_blue` | Blue Business, compressed spacing for higher information density |
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

**Q: Editor does not show styles (colors/fonts/layout)?**
A: Since 2026-06-19 the editor uses iframe + designMode; edit-mode styles are
   100% identical to preview. Make sure `frontend/src/components/editor/EditableResumePreview.tsx`
   is up to date.

**Q: Chinese characters garbled in editor files?**
A: Older versions may have been written via PowerShell with GBK encoding.
   Re-save the file with UTF-8 (no BOM) encoding:
   ```powershell
   [System.IO.File]::WriteAllText(
     "path/to/file.tsx",
       $content,
       [System.Text.UTF8Encoding]::new($false)
   )
   ```

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
