"""
Gradio UI for Jobs Applier AI Agent
Provides a web interface for resume generation and management.
"""
import base64
import os
from pathlib import Path
from datetime import datetime

import gradio as gr
import yaml

# Import existing project modules
from src.libs.resume_and_cover_builder import ResumeFacade, ResumeGenerator, StyleManager
from src.resume_schemas.resume import Resume
from src.utils.chrome_utils import init_browser
from src.logging import logger

# Constants
DATA_FOLDER = Path("data_folder")
OUTPUT_FOLDER = DATA_FOLDER / "output"
STYLES_DIR = Path("src/libs/resume_and_cover_builder/resume_style")

# Ensure output directory exists
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

# Load saved system language at startup
secrets_global = {}
secrets_path_global = DATA_FOLDER / "secrets.yaml"
if secrets_path_global.exists():
    with open(secrets_path_global, "r", encoding="utf-8") as f:
        secrets_global = yaml.safe_load(f) or {}

# Get initial system language - will be determined by JavaScript on page load
INITIAL_SYSTEM_LANG = "zh"  # Default, will be overridden by JS based on localStorage

# Gradio i18n configuration - for all UI text
i18n = gr.I18n(
    en={
        "tab_generate": "Generate Resume",
        "tab_history": "History",
        "tab_settings": "Settings",
        "header": "AI Resume Generator",
        "header_config": "⚙️ Configuration",
        "header_generated": "📁 Generated Resumes",
        "header_settings": "🔧 Application Settings",
        "header_resume_editor": "📋 Resume Content Editor",
        "label_api_key": "API Key",
        "label_model_type": "Model Type",
        "label_base_url": "API Base URL",
        "label_resume_style": "Resume Style",
        "label_resume_lang": "Resume Language",
        "label_system_lang": "System Language",
        "label_status": "Status",
        "label_download": "Download Resume",
        "label_job_desc": "Job Description",
        "label_available_styles": "ℹ️ Available Styles",
        "info_resume_lang": "Select the language for resume content",
        "info_system_lang": "Select the UI language",
        "placeholder_api_key": "Enter your API key",
        "placeholder_base_url": "https://api.minimaxi.com/anthropic",
        "placeholder_job_desc": "Paste the job description here...",
        "btn_generate": "🚀 Generate Resume",
        "btn_refresh": "🔄 Refresh History",
        "btn_clear": "🗑️ Clear All",
        "btn_save_resume": "💾 Save Resume Content",
        "msg_provided": "Please provide a job description",
        "msg_success": "Resume generated successfully",
        "msg_error": "Error",
        "msg_no_history": "No resumes generated yet",
        "msg_cleared": "Cleared",
        "msg_load_error": "Could not load resume content",
        "msg_config_saved": "Configuration saved!",
        "footer": "*Built with ❤️ using Gradio | Jobs Applier AI Agent*",
        "subtitle": "Generate professional resumes with AI",
    },
    zh={
        "tab_generate": "生成简历",
        "tab_history": "历史记录",
        "tab_settings": "设置",
        "header": "AI 简历生成器",
        "header_config": "⚙️ 配置",
        "header_generated": "📁 已生成的简历",
        "header_settings": "🔧 应用设置",
        "header_resume_editor": "📋 简历内容编辑器",
        "label_api_key": "API 密钥",
        "label_model_type": "模型类型",
        "label_base_url": "API 地址",
        "label_resume_style": "简历样式",
        "label_resume_lang": "简历语言",
        "label_system_lang": "系统语言",
        "label_status": "状态",
        "label_download": "下载简历",
        "label_job_desc": "职位描述",
        "label_available_styles": "ℹ️ 可用样式",
        "info_resume_lang": "选择简历内容的语言",
        "info_system_lang": "选择界面语言",
        "placeholder_api_key": "请输入您的 API 密钥",
        "placeholder_base_url": "https://api.minimaxi.com/anthropic",
        "placeholder_job_desc": "请在此粘贴职位描述...",
        "btn_generate": "🚀 生成简历",
        "btn_refresh": "🔄 刷新历史",
        "btn_clear": "🗑️ 清空全部",
        "btn_save_resume": "💾 保存简历内容",
        "msg_provided": "请提供职位描述",
        "msg_success": "简历生成成功",
        "msg_error": "错误",
        "msg_no_history": "尚未生成简历",
        "msg_cleared": "已清空",
        "msg_load_error": "无法加载简历内容",
        "msg_config_saved": "配置已保存！",
        "footer": "*使用 ❤️ 和 Gradio 构建 | Jobs Applier AI Agent*",
        "subtitle": "使用 AI 助手生成专业简历",
    }
)

# ============== Configuration ==============

def load_secrets():
    """Load API key from secrets.yaml"""
    secrets_path = DATA_FOLDER / "secrets.yaml"
    if secrets_path.exists():
        with open(secrets_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}

def get_ui_strings(system_language="zh"):
    """Get UI strings based on system language"""
    if system_language == "en":
        return {
            # Tab titles
            "tab_generate": "Generate Resume",
            "tab_history": "History",
            "tab_settings": "Settings",
            
            # Headers
            "header_config": "⚙️ Configuration",
            "header_generated": "📁 Generated Resumes",
            "header_settings": "🔧 Application Settings",
            
            # Labels
            "label_api_key": "API Key",
            "label_model_type": "Model Type",
            "label_base_url": "API Base URL",
            "label_resume_style": "Resume Style",
            "label_resume_lang": "Resume Language",
            "label_system_lang": "System Language",
            "label_status": "Status",
            "label_download": "Download Resume",
            "label_job_desc": "Job Description",
            "label_available_styles": "ℹ️ Available Styles",
            "label_data_folders": "#### 📁 Data Folders",
            "label_data_folder": "Data Folder",
            "label_output_folder": "Output Folder",
            "label_styles_folder": "Styles Folder",
            "label_style_templates": "#### 🎨 Style Templates",
            "label_preview_style": "Preview Style",
            "label_resume_editor": "### 📋 Resume Content Editor",
            "label_resume_content": "plain_text_resume.yaml Content",
            "label_save_status": "Save Status",
            "label_cleared_status": "Clear Status",
            
            # Info
            "info_resume_lang": "Select the language for resume content",
            "info_system_lang": "Select the UI language",
            
            # Placeholders
            "placeholder_api_key": "Enter your API key",
            "placeholder_base_url": "https://api.minimaxi.com/anthropic",
            "placeholder_job_desc": "Paste the job description here...",
            
            # Buttons
            "btn_generate": "🚀 Generate Resume",
            "btn_refresh": "🔄 Refresh History",
            "btn_clear": "🗑️ Clear All",
            "btn_save_resume": "💾 Save Resume Content",
            
            # Messages
            "msg_no_styles": "No styles found!",
            "msg_provided": "Please provide a job description",
            "msg_success": "Resume generated successfully",
            "msg_error": "Error",
            "msg_no_history": "No resumes generated yet",
            "msg_cleared": "Cleared",
            "msg_found_files": "Found {} resume(s)",
            "msg_style_preview_soon": "*Style preview coming soon...*",
            "msg_load_error": "Could not load resume content",
            "msg_config_saved": "Configuration saved!",
            
            # Footer
            "footer": "*Built with ❤️ using Gradio | Jobs Applier AI Agent*",
        }
    else:  # Chinese
        return {
            # Tab titles
            "tab_generate": "生成简历",
            "tab_history": "历史记录",
            "tab_settings": "设置",
            
            # Headers
            "header_config": "⚙️ 配置",
            "header_generated": "📁 已生成的简历",
            "header_settings": "🔧 应用设置",
            
            # Labels
            "label_api_key": "API 密钥",
            "label_model_type": "模型类型",
            "label_base_url": "API 地址",
            "label_resume_style": "简历样式",
            "label_resume_lang": "简历语言",
            "label_system_lang": "系统语言",
            "label_status": "状态",
            "label_download": "下载简历",
            "label_job_desc": "职位描述",
            "label_available_styles": "ℹ️ 可用样式",
            "label_data_folders": "#### 📁 数据文件夹",
            "label_data_folder": "数据文件夹",
            "label_output_folder": "输出文件夹",
            "label_styles_folder": "样式文件夹",
            "label_style_templates": "#### 🎨 样式模板",
            "label_preview_style": "预览样式",
            "label_resume_editor": "### 📋 简历内容编辑器",
            "label_resume_content": "plain_text_resume.yaml 内容",
            "label_save_status": "保存状态",
            "label_cleared_status": "清空状态",
            
            # Info
            "info_resume_lang": "选择简历内容的语言",
            "info_system_lang": "选择界面语言",
            
            # Placeholders
            "placeholder_api_key": "请输入您的 API 密钥",
            "placeholder_base_url": "https://api.minimaxi.com/anthropic",
            "placeholder_job_desc": "请在此粘贴职位描述...",
            
            # Buttons
            "btn_generate": "🚀 生成简历",
            "btn_refresh": "🔄 刷新历史",
            "btn_clear": "🗑️ 清空全部",
            "btn_save_resume": "💾 保存简历内容",
            
            # Messages
            "msg_no_styles": "未找到样式！",
            "msg_provided": "请提供职位描述",
            "msg_success": "简历生成成功",
            "msg_error": "错误",
            "msg_no_history": "尚未生成简历",
            "msg_cleared": "已清空",
            "msg_found_files": "找到 {} 份简历",
            "msg_style_preview_soon": "*样式预览即将推出...*",
            "msg_load_error": "无法加载简历内容",
            "msg_config_saved": "配置已保存！",
            
            # Footer
            "footer": "*使用 ❤️ 和 Gradio 构建 | Jobs Applier AI Agent*",
        }

def save_secrets(api_key, model_type, base_url, resume_language="zh", system_language="zh"):
    """Save configuration to secrets.yaml"""
    secrets_path = DATA_FOLDER / "secrets.yaml"
    data = {}
    if secrets_path.exists():
        with open(secrets_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    data["llm_api_key"] = api_key
    data["llm_model_type"] = model_type
    data["llm_base_url"] = base_url
    data["resume_language"] = resume_language  # 简历语言: zh/en
    data["system_language"] = system_language  # 系统语言: zh/en
    with open(secrets_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)
    s = get_ui_strings(system_language)
    return i18n("msg_config_saved")

def get_available_styles():
    """Get list of available CSS styles using StyleManager"""
    style_manager = StyleManager()
    raw_styles = style_manager.get_styles()
    styles = {}
    for name, (file_name, author_link) in raw_styles.items():
        styles[name] = {"file": file_name, "author": author_link}
    return styles

# ============== Core Functions ==============

def generate_resume(api_key, model_type, base_url, style_name, job_description, resume_language, progress=gr.Progress()):
    """Generate resume - if job_description provided, generates tailored resume; otherwise generates regular resume"""
    try:
        # 使用默认中文界面语言
        system_language = "zh"
        
        # 获取UI字符串
        s = get_ui_strings(system_language)
        
        # Determine if this is a tailored resume request
        is_tailored = job_description and job_description.strip()
        
        if not is_tailored:
            # Regular resume generation
            progress(0.1, desc="初始化...")
            
            print(f"Generating resume with style: {style_name}, resume_lang: {resume_language}")
            
            if api_key:
                save_secrets(api_key, model_type, base_url, resume_language)
            
            # 根据简历语言选择对应的简历文件
            if resume_language == "en":
                resume_file = DATA_FOLDER / "plain_text_resume.yaml"
            else:
                resume_file = DATA_FOLDER / "plain_text_resume_zh.yaml"
            
            with open(resume_file, "r", encoding="utf-8") as f:
                plain_text_resume = f.read()
            
            progress(0.2, desc="加载样式...")
            
            # Use StyleManager and match with get_available_styles
            available_styles_map = get_available_styles()
            
            print(f"Available styles: {list(available_styles_map.keys())}")
            print(f"User selected: {style_name}")
            
            style_manager = StyleManager()
            all_styles = style_manager.get_styles()
            
            # Set selected style - match by key
            if style_name and style_name in all_styles:
                print(f"Style {style_name} found in StyleManager")
                style_manager.set_selected_style(style_name)
            elif available_styles_map and style_name in available_styles_map:
                # Fallback - if style not in get_styles, use the one from get_available_styles
                print(f"Using style from available_styles")
                style_manager.set_selected_style(style_name)
            else:
                # Use first available
                if all_styles:
                    first_style = list(all_styles.keys())[0]
                    print(f"No match found, using first style: {first_style}")
                    style_manager.set_selected_style(first_style)
            
            progress(0.4, desc="正在使用 AI 生成简历内容...")
            
            resume_generator = ResumeGenerator()
            resume_object = Resume(plain_text_resume)
            driver = init_browser()
            resume_generator.set_resume_object(resume_object)
            
            resume_facade = ResumeFacade(
                api_key=api_key,
                style_manager=style_manager,
                resume_generator=resume_generator,
                resume_object=resume_object,
                output_path=OUTPUT_FOLDER,
                resume_language=resume_language,
                system_language=system_language,
            )
            resume_facade.set_driver(driver)
            
            progress(0.8, desc="正在转换为 PDF...")
            
            result_base64 = resume_facade.create_resume_pdf()
            pdf_data = base64.b64decode(result_base64)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"resume_{timestamp}.pdf"
            output_path = OUTPUT_FOLDER / filename
            with open(output_path, "wb") as f:
                f.write(pdf_data)
            
            with open(OUTPUT_FOLDER / "resume_base.pdf", "wb") as f:
                f.write(pdf_data)
            
            progress(1.0, desc="完成！")
            
            return str(output_path), f"{i18n('msg_success')}: {filename}"
        else:
            # Tailored resume generation - job description provided
            progress(0.1, desc="初始化...")
            
            print(f"Generating tailored resume with style: {style_name}, resume_lang: {resume_language}")
            
            if api_key:
                save_secrets(api_key, model_type, base_url, resume_language)
            
            # 根据简历语言选择对应的简历文件
            if resume_language == "en":
                resume_file = DATA_FOLDER / "plain_text_resume.yaml"
            else:
                resume_file = DATA_FOLDER / "plain_text_resume_zh.yaml"
            
            with open(resume_file, "r", encoding="utf-8") as f:
                plain_text_resume = f.read()
            
            progress(0.2, desc="加载样式...")
            
            style_manager = StyleManager()
            available_styles = style_manager.get_styles()
            
            if style_name and style_name in available_styles:
                style_manager.set_selected_style(style_name)
            else:
                if available_styles:
                    first_style = list(available_styles.keys())[0]
                    style_manager.set_selected_style(first_style)
            
            progress(0.4, desc="正在分析职位描述并定制简历...")
            
            resume_generator = ResumeGenerator()
            resume_object = Resume(plain_text_resume)
            driver = init_browser()
            resume_generator.set_resume_object(resume_object)
            
            resume_facade = ResumeFacade(
                api_key=api_key,
                style_manager=style_manager,
                resume_generator=resume_generator,
                resume_object=resume_object,
                output_path=OUTPUT_FOLDER,
                resume_language=resume_language,
                system_language=system_language,
            )
            resume_facade.set_driver(driver)
            
            progress(0.8, desc="正在转换为 PDF...")
            
            # 使用带职位描述的简历生成方法
            style_path = style_manager.get_style_path()
            html_resume = resume_generator.create_resume_job_description_text(style_path, job_description)
            
            # 转换为 PDF
            from src.utils.chrome_utils import HTML_to_PDF
            result = HTML_to_PDF(html_resume, driver)
            pdf_data = base64.b64decode(result)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"resume_tailored_{timestamp}.pdf"
            output_path = OUTPUT_FOLDER / filename
            with open(output_path, "wb") as f:
                f.write(pdf_data)
            
            # 关闭浏览器
            driver.quit()
            
            progress(1.0, desc="完成！")
            
            return str(output_path), f"{i18n('msg_success')}: {filename}"
    
    except Exception as e:
        # 确保关闭浏览器
        if 'driver' in locals():
            try:
                driver.quit()
            except:
                pass
        logger.exception(f"Error generating resume: {e}")
        return None, f"{i18n('msg_error')}: {str(e)}"

def list_output_files():
    """List all PDF files in the output directory"""
    files = []
    if OUTPUT_FOLDER.exists():
        for f in OUTPUT_FOLDER.glob("*.pdf"):
            files.append({
                "name": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
    return sorted(files, key=lambda x: x["modified"], reverse=True)

def clear_output_folder():
    """Clear all PDF files in output folder"""
    count = 0
    if OUTPUT_FOLDER.exists():
        for f in OUTPUT_FOLDER.glob("*.pdf"):
            f.unlink()
            count += 1
    return f"已清空 {count} 个文件"

def save_resume_content(content, resume_language="zh"):
    """Save resume content to plain_text_resume.yaml or plain_text_resume_zh.yaml"""
    try:
        # 根据简历语言选择保存的文件
        if resume_language == "en":
            filename = DATA_FOLDER / "plain_text_resume.yaml"
        else:
            filename = DATA_FOLDER / "plain_text_resume_zh.yaml"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return "简历内容已保存！" if resume_language == "zh" else "Resume content saved!"
    except Exception as e:
        return f"保存错误: {e}" if resume_language == "zh" else f"Save error: {e}"

def load_resume_content(resume_language="zh"):
    """Load resume content based on language selection"""
    try:
        if resume_language == "en":
            filename = DATA_FOLDER / "plain_text_resume.yaml"
        else:
            filename = DATA_FOLDER / "plain_text_resume_zh.yaml"
        
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"# Error loading file: {e}"

def refresh_history(system_language="zh"):
    """Refresh history display"""
    s = get_ui_strings(system_language)
    files = list_output_files()
    if not files:
        return "", i18n("msg_no_history")
    
    file_list = "\n".join([f"- **{f['name']}** ({f['size']/1024:.1f} KB) - {f['modified']}" for f in files])
    return file_list, i18n("msg_found_files").replace("{}", str(len(files)))

# ============== UI Layout ==============

def update_ui_language(system_language):
    """Update all UI components when system language changes"""
    s = get_ui_strings(system_language)
    return (
        # Tab 1: Generate Resume
        i18n("tab_generate"),  # Tab title
        i18n("header_config"),  # Header
        i18n("label_api_key"),  # API Key label
        i18n("placeholder_api_key"),  # API Key placeholder
        i18n("label_model_type"),  # Model Type label
        i18n("label_base_url"),  # Base URL label
        i18n("placeholder_base_url"),  # Base URL placeholder
        i18n("label_resume_style"),  # Style label
        i18n("label_resume_lang"),  # Resume Language label
        i18n("info_resume_lang"),  # Resume Language info
        i18n("label_system_lang"),  # System Language label
        i18n("info_system_lang"),  # System Language info
        i18n("btn_generate"),  # Generate button
        i18n("label_status"),  # Status label
        i18n("label_download"),  # Download label
        i18n("label_available_styles"),  # Available styles label
        # Tab 2: History
        i18n("tab_history"),
        i18n("header_generated"),
        i18n("btn_refresh"),
        i18n("btn_clear"),
        i18n("label_cleared_status"),
        # Tab 4: Settings
        i18n("tab_settings"),
        i18n("header_settings"),
        i18n("label_data_folders"),
        i18n("label_data_folder"),
        i18n("label_output_folder"),
        i18n("label_styles_folder"),
        i18n("label_style_templates"),
        i18n("label_preview_style"),
        i18n("msg_style_preview_soon"),
        i18n("label_resume_editor"),
        i18n("label_resume_content"),
        i18n("btn_save_resume"),
        i18n("label_save_status"),
        i18n("msg_load_error"),
        i18n("footer"),
    )

def create_ui():
    """Create and return the Gradio UI blocks"""
    
    secrets = load_secrets()
    available_styles = get_available_styles()
    style_list = list(available_styles.keys())
    
    # Ensure we have styles
    if not style_list:
        print("Warning: No styles found!")
        style_list = ["Default"]
    
    print(f"Available styles: {style_list}")
    
    with gr.Blocks(title=i18n("header")) as app:
        
        gr.Markdown("# 📄 " + i18n("header"))
        gr.Markdown(i18n("subtitle"))
        
        with gr.Tabs():
            # ========== Tab 1: Generate Resume ==========
            with gr.TabItem(i18n("tab_generate"), id="tab_generate"):
                gr.Markdown("### " + i18n("header_config"), elem_id="header_config_1")
                
                with gr.Row():
                    with gr.Column(scale=1):
                        api_key = gr.Textbox(
                            label=i18n("label_api_key"),
                            value=secrets.get("llm_api_key", ""),
                            placeholder=i18n("placeholder_api_key"),
                            type="password",
                            elem_id="api_key_input"
                        )
                        
                        model_type = gr.Dropdown(
                            label=i18n("label_model_type"),
                            choices=["anthropic", "openai"],
                            value=secrets.get("llm_model_type", "anthropic"),
                            elem_id="model_type_input"
                        )
                        
                        base_url = gr.Textbox(
                            label=i18n("label_base_url"),
                            value=secrets.get("llm_base_url", "https://api.minimaxi.com/anthropic"),
                            placeholder=i18n("placeholder_base_url"),
                            elem_id="base_url_input"
                        )
                        
                        style_choice = gr.Radio(
                            label=i18n("label_resume_style"),
                            choices=style_list,
                            value=style_list[0] if style_list else None,
                            elem_id="style_choice_input"
                        )
                        
                        resume_language = gr.Dropdown(
                            label=i18n("label_resume_lang"),
                            choices=[("中文", "zh"), ("English", "en")],
                            value=secrets.get("resume_language", "zh"),
                            info=i18n("info_resume_lang"),
                            elem_id="resume_lang_input"
                        )
                        
                        generate_btn = gr.Button(i18n("btn_generate"), variant="primary", elem_id="generate_btn")
                    
                    with gr.Column(scale=2):
                        job_description = gr.Textbox(
                            label=i18n("label_job_desc"),
                            placeholder=i18n("placeholder_job_desc"),
                            lines=8,
                            elem_id="job_desc_input"
                        )
                        status_output = gr.Textbox(label=i18n("label_status"), interactive=False, lines=3, elem_id="status_output")
                        output_file = gr.File(label=i18n("label_download"), elem_id="output_file")
                
                with gr.Accordion(i18n("label_available_styles"), open=False, elem_id="styles_accordion"):
                    for name, info in available_styles.items():
                        gr.Markdown(f"- **{name}** by {info['author']}")
                
                generate_btn.click(
                    fn=generate_resume,
                    inputs=[api_key, model_type, base_url, style_choice, job_description, resume_language],
                    outputs=[output_file, status_output]
                )
            
            # ========== Tab 2: History ==========
            with gr.TabItem(i18n("tab_history"), id="tab_history"):
                gr.Markdown(f"### {i18n('header_generated')}", elem_id="header_history")
                
                history_display = gr.Markdown("", visible=False)
                history_info = gr.Textbox(label=i18n("label_status"), interactive=False, lines=1)
                
                with gr.Row():
                    refresh_btn = gr.Button(i18n("btn_refresh"))
                    clear_btn = gr.Button(i18n("btn_clear"))
                
                clear_status = gr.Textbox(label=i18n("label_cleared_status"), interactive=False)
                
                refresh_btn.click(
                    fn=refresh_history,
                    outputs=[history_display, history_info]
                )
                
                clear_btn.click(
                    fn=clear_output_folder,
                    outputs=[clear_status]
                )
                
                # Initial load
                initial_files = list_output_files()
                if initial_files:
                    initial_list = "\n".join([f"- **{f['name']}** ({f['size']/1024:.1f} KB) - {f['modified']}" for f in initial_files])
                    history_display.value = initial_list
                    history_display.visible = True
                    history_info.value = i18n("msg_found_files").replace("{}", str(len(initial_files)))
            
            # ========== Tab 4: Settings ==========
            with gr.TabItem(i18n("tab_settings"), id="tab_settings"):
                gr.Markdown(f"### {i18n('header_settings')}", elem_id="header_settings")
                
                with gr.Row():
                    with gr.Column():
                        gr.Markdown(i18n("label_data_folders"), elem_id="data_folders_header")
                        gr.Markdown(f"**{i18n('label_data_folder')}:** `{DATA_FOLDER}`", elem_id="data_folder_value")
                        gr.Markdown(f"**{i18n('label_output_folder')}:** `{OUTPUT_FOLDER}`", elem_id="output_folder_value")
                        gr.Markdown(f"**{i18n('label_styles_folder')}:** `{STYLES_DIR}`", elem_id="styles_folder_value")
                    
                    with gr.Column():
                        gr.Markdown(i18n("label_style_templates"), elem_id="style_templates_header")
                        style_preview = gr.Dropdown(
                            label=i18n("label_preview_style"),
                            choices=style_list,
                            value=style_list[0] if style_list else None
                        )
                        gr.Markdown(i18n("msg_style_preview_soon"), elem_id="style_preview_soon")
                
                gr.Markdown("---")
                gr.Markdown(i18n("label_resume_editor"), elem_id="resume_editor_header")
                
                try:
                    # 使用函数加载对应语言的简历文件
                    resume_content = load_resume_content(resume_language.value if resume_language else "zh")
                    resume_editor = gr.Textbox(
                        label=i18n("label_resume_content"),
                        value=resume_content,
                        lines=20,
                        elem_id="resume_editor_textbox"
                    )
                    save_btn = gr.Button(i18n("btn_save_resume"))
                    save_status = gr.Textbox(label=i18n("label_save_status"), interactive=False, lines=1)
                    
                    save_btn.click(
                        fn=save_resume_content,
                        inputs=[resume_editor, resume_language],
                        outputs=[save_status]
                    )
                    
                    # 当简历语言改变时，重新加载对应语言的文件
                    resume_language.change(
                        fn=load_resume_content,
                        inputs=[resume_language],
                        outputs=[resume_editor]
                    )
                except Exception as e:
                    gr.Markdown(f"⚠️ {i18n('msg_load_error')}: {e}")
        
        # Footer
        gr.Markdown("---")
        gr.Markdown(i18n("footer"))
        
        # JavaScript to sync UI with Gradio Settings language
        app.load(
            fn=None,
            js="""
            () => {
                // Check URL for __locale parameter (set by Gradio Settings)
                function getLocaleFromURL() {
                    const params = new URLSearchParams(window.location.search);
                    return params.get('__locale');
                }
                
                // Convert locale to app language code
                function localeToAppLang(locale) {
                    if (!locale) return 'zh';
                    const l = locale.toLowerCase();
                    if (l.includes('zh')) return 'zh';
                    if (l.includes('en')) return 'en';
                    return 'zh';
                }
                
                // UI strings for translation
                const uiStrings = {
                    'zh': {
                        'tab_generate': '生成简历',
                        'tab_history': '历史记录',
                        'tab_settings': '设置',
                        'header_config': '⚙️ 配置',
                        'header_generated': '📁 已生成的简历',
                        'header_settings': '🔧 应用设置',
                        'label_api_key': 'API 密钥',
                        'label_model_type': '模型类型',
                        'label_base_url': 'API 地址',
                        'label_resume_style': '简历样式',
                        'label_resume_lang': '简历语言',
                        'label_system_lang': '系统语言',
                        'label_status': '状态',
                        'label_download': '下载简历',
                        'label_job_desc': '职位描述',
                        'label_available_styles': 'ℹ️ 可用样式',
                        'label_data_folders': '📁 数据文件夹',
                        'label_data_folder': '数据文件夹',
                        'label_output_folder': '输出文件夹',
                        'label_styles_folder': '样式文件夹',
                        'label_style_templates': '🎨 样式模板',
                        'label_preview_style': '预览样式',
                        'label_resume_editor': '📋 简历内容编辑器',
                        'label_resume_content': 'plain_text_resume.yaml 内容',
                        'label_save_status': '保存状态',
                        'label_cleared_status': '清空状态',
                        'info_resume_lang': '选择简历内容的语言',
                        'info_system_lang': '选择界面语言',
                        'placeholder_api_key': '请输入您的 API 密钥',
                        'placeholder_base_url': 'https://api.minimaxi.com/anthropic',
                        'placeholder_job_desc': '请在此粘贴职位描述...',
                        'btn_generate': '🚀 生成简历',
                        'btn_refresh': '🔄 刷新历史',
                        'btn_clear': '🗑️ 清空全部',
                        'btn_save_resume': '💾 保存简历内容',
                        'msg_no_history': '尚未生成简历',
                        'msg_cleared': '已清空',
                        'msg_load_error': '无法加载简历内容',
                        'msg_style_preview_soon': '*样式预览即将推出...*',
                        'footer': '*使用 ❤️ 和 Gradio 构建 | Jobs Applier AI Agent*',
                    },
                    'en': {
                        'tab_generate': 'Generate Resume',
                        'tab_history': 'History',
                        'tab_settings': 'Settings',
                        'header_config': '⚙️ Configuration',
                        'header_generated': '📁 Generated Resumes',
                        'header_settings': '🔧 Application Settings',
                        'label_api_key': 'API Key',
                        'label_model_type': 'Model Type',
                        'label_base_url': 'API Base URL',
                        'label_resume_style': 'Resume Style',
                        'label_resume_lang': 'Resume Language',
                        'label_system_lang': 'System Language',
                        'label_status': 'Status',
                        'label_download': 'Download Resume',
                        'label_job_desc': 'Job Description',
                        'label_available_styles': 'ℹ️ Available Styles',
                        'label_data_folders': '📁 Data Folders',
                        'label_data_folder': 'Data Folder',
                        'label_output_folder': 'Output Folder',
                        'label_styles_folder': 'Styles Folder',
                        'label_style_templates': '🎨 Style Templates',
                        'label_preview_style': 'Preview Style',
                        'label_resume_editor': '📋 Resume Content Editor',
                        'label_resume_content': 'plain_text_resume.yaml Content',
                        'label_save_status': 'Save Status',
                        'label_cleared_status': 'Clear Status',
                        'info_resume_lang': 'Select the language for resume content',
                        'info_system_lang': 'Select the UI language',
                        'placeholder_api_key': 'Enter your API key',
                        'placeholder_base_url': 'https://api.minimaxi.com/anthropic',
                        'placeholder_job_desc': 'Paste the job description here...',
                        'btn_generate': '🚀 Generate Resume',
                        'btn_refresh': '🔄 Refresh History',
                        'btn_clear': '🗑️ Clear All',
                        'btn_save_resume': '💾 Save Resume Content',
                        'msg_no_history': 'No resumes generated yet',
                        'msg_cleared': 'Cleared',
                        'msg_load_error': 'Could not load resume content',
                        'msg_style_preview_soon': '*Style preview coming soon...*',
                        'footer': '*Built with ❤️ using Gradio | Jobs Applier AI Agent*',
                    }
                };
                
                // Update all UI elements based on language
                function updateUI(lang) {
                    const s = uiStrings[lang] || uiStringi18n('zh');
                    console.log('Updating UI to:', lang);
                    
                    // Update headers
                    document.querySelectorAll('h1').forEach(el => {
                        if (el.textContent.includes('简历') || el.textContent.includes('Resume')) {
                            el.textContent = lang === 'zh' ? '📄 AI 简历生成器' : '📄 AI Resume Generator';
                        }
                    });
                    
                    // Update h3/h4 headers - including tab content headers
                    document.querySelectorAll('h3, h4').forEach(el => {
                        const text = el.textContent.trim();
                        if (text.includes('配置') || text.includes('Configuration') || text.includes('⚙️')) el.textContent = s.header_config;
                        if (text.includes('已生成') || text.includes('Generated') || text.includes('📁')) el.textContent = s.header_generated;
                        if (text.includes('应用设置') || text.includes('Application') || text.includes('🔧')) el.textContent = s.header_settings;
                        if (text.includes('简历内容编辑器') || text.includes('Resume Content') || text.includes('📋')) el.textContent = s.label_resume_editor;
                    });
                    
                    // Update Tab content headers specifically (by elem_id pattern)
                    document.querySelectorAll('[id="header_history"] h3, #header_history').forEach(el => {
                        el.textContent = s.header_generated;
                    });
                    document.querySelectorAll('[id="header_settings"] h3, #header_settings').forEach(el => {
                        el.textContent = s.header_settings;
                    });
                    
                    // Update tab labels - target Gradio tab buttons
                    document.querySelectorAll('[id*="tab_"]').forEach(el => {
                        const text = el.textContent.trim().toLowerCase();
                        if (text.includes('生成') || text.includes('generate')) el.textContent = s.tab_generate;
                        if (text.includes('历史') || text.includes('history')) el.textContent = s.tab_history;
                        if (text.includes('设置') || text.includes('settings')) el.textContent = s.tab_settings;
                    });
                    
                    // Also update Gradio Tab buttons directly (they use different structure)
                    document.querySelectorAll('.tab-nav button, [role="tab"]').forEach(el => {
                        const text = el.textContent.trim();
                        if (text.includes('生成') || text.includes('generate') || text.includes('Generate')) {
                            el.textContent = s.tab_generate;
                        }
                        if (text.includes('历史') || text.includes('history') || text.includes('History')) {
                            el.textContent = s.tab_history;
                        }
                        if (text.includes('设置') || text.includes('settings') || text.includes('Settings')) {
                            el.textContent = s.tab_settings;
                        }
                    });
                    
                    // Also target tab button labels via text content patterns
                    document.querySelectorAll('button[id^="tab"]').forEach(el => {
                        const text = el.textContent.trim();
                        if (text.includes('生成') || text.includes('generate')) el.textContent = s.tab_generate;
                        if (text.includes('历史') || text.includes('history')) el.textContent = s.tab_history;
                        if (text.includes('设置') || text.includes('settings')) el.textContent = s.tab_settings;
                    });
                    
                    // Update footer
                    document.querySelectorAll('.gradio-footer, footer').forEach(el => {
                        if (el.innerHTML.includes('使用') || el.innerHTML.includes('Built')) {
                            el.innerHTML = `<div>${s.footer}</div>`;
                        }
                    });
                }
                
                // Initial update
                const initialLocale = getLocaleFromURL();
                if (initialLocale) {
                    const lang = localeToAppLang(initialLocale);
                    console.log('Initial locale from URL:', initialLocale, '-> lang:', lang);
                    updateUI(lang);
                    localStorage.setItem('gradio_locale', lang);
                } else {
                    // Check stored locale
                    const stored = localStorage.getItem('gradio_locale');
                    if (stored) {
                        updateUI(stored);
                    }
                }
                
                // Poll for URL changes (Gradio Settings changes language)
                setInterval(() => {
                    const newLocale = getLocaleFromURL();
                    if (newLocale) {
                        const newLang = localeToAppLang(newLocale);
                        const stored = localStorage.getItem('gradio_locale');
                        if (newLang !== stored) {
                            console.log('Locale changed in URL:', newLocale);
                            localStorage.setItem('gradio_locale', newLang);
                            updateUI(newLang);
                        }
                    }
                }, 1000);
            }
            """
        )
    
    return app

def main():
    """Main entry point"""
    print("=" * 50)
    print("正在启动 AI 简历生成器...")
    print("=" * 50)
    
    # 显示可用的样式
    print("\n[1/4] 加载样式中...")
    available_styles = get_available_styles()
    style_list = list(available_styles.keys())
    print(f"      找到 {len(style_list)} 个样式:")
    for s in style_list:
        print(f"        - {s}")
    
    # 创建 UI
    print("\n[2/4] 创建 UI 组件...")
    app = create_ui()
    
    # 启动
    print("\n[3/4] 启动服务器...")
    print("      服务器: http://localhost:7860")
    print("      浏览器将自动打开")
    
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        i18n=i18n
    )
    
    print("\n[4/4] 服务器启动成功！")
    print("=" * 50)

if __name__ == "__main__":
    main()