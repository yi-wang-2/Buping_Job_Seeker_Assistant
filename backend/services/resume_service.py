"""Resume generation service — wraps existing src/ logic."""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.services.config_service import load_secrets, save_secrets

DATA_FOLDER = Path("data_folder")
OUTPUT_FOLDER = DATA_FOLDER / "output"
STYLES_DIR = Path("src/libs/resume_and_cover_builder/resume_style")

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)


def get_available_styles() -> dict[str, dict[str, str]]:
    """Get available resume CSS styles."""
    from src.libs.resume_and_cover_builder import StyleManager

    style_manager = StyleManager()
    raw_styles = style_manager.get_styles()
    styles: dict[str, dict[str, str]] = {}
    for name, (file_name, author_link) in raw_styles.items():
        styles[name] = {"file": file_name, "author": author_link}
    return styles


def generate_resume(
    api_key: str,
    model_type: str,
    base_url: str,
    style_name: str,
    job_description: str | None,
    resume_language: str = "zh",
    system_language: str = "zh",
) -> dict[str, Any]:
    """Generate a resume PDF. Returns {path, filename, status}."""
    from src.libs.resume_and_cover_builder import ResumeFacade, ResumeGenerator, StyleManager
    from src.resume_schemas.resume import Resume
    from src.utils.chrome_utils import init_browser

    # Save config
    if api_key:
        save_secrets({
            "llm_api_key": api_key,
            "llm_model_type": model_type,
            "llm_base_url": base_url,
            "resume_language": resume_language,
            "system_language": system_language,
        })

    # Load resume content
    resume_file = DATA_FOLDER / ("plain_text_resume.yaml" if resume_language == "en" else "plain_text_resume_zh.yaml")
    with open(resume_file, "r", encoding="utf-8") as f:
        plain_text_resume = f.read()

    # Setup style
    style_manager = StyleManager()
    available_styles = style_manager.get_styles()
    if style_name and style_name in available_styles:
        style_manager.set_selected_style(style_name)
    elif available_styles:
        style_manager.set_selected_style(list(available_styles.keys())[0])

    # Generate
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

    try:
        is_tailored = job_description and job_description.strip()
        if is_tailored:
            style_path = style_manager.get_style_path()
            html_resume = resume_generator.create_resume_job_description_text(style_path, job_description)
            from src.utils.chrome_utils import HTML_to_PDF
            result = HTML_to_PDF(html_resume, driver)
            pdf_data = base64.b64decode(result)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"resume_tailored_{timestamp}.pdf"
        else:
            result_base64 = resume_facade.create_resume_pdf()
            pdf_data = base64.b64decode(result_base64)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"resume_{timestamp}.pdf"

        output_path = OUTPUT_FOLDER / filename
        with open(output_path, "wb") as f:
            f.write(pdf_data)

        # Also save as resume_base.pdf
        with open(OUTPUT_FOLDER / "resume_base.pdf", "wb") as f:
            f.write(pdf_data)

        return {"path": str(output_path), "filename": filename, "status": "success"}
    finally:
        try:
            driver.quit()
        except Exception:
            pass
