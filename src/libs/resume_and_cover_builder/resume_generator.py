"""
This module is responsible for generating resumes and cover letters using the LLM model.
"""
# app/libs/resume_and_cover_builder/resume_generator.py
from string import Template
from typing import Any
from src.libs.resume_and_cover_builder.llm.llm_generate_resume import LLMResumer
from src.libs.resume_and_cover_builder.llm.llm_generate_resume_from_job import LLMResumeJobDescription
from src.libs.resume_and_cover_builder.llm.llm_generate_cover_letter_from_job import LLMCoverLetterJobDescription
from .module_loader import load_module
from .config import global_config
from .resume_html import add_default_profile_photo

class ResumeGenerator:
    def __init__(self):
        self.regeneration_context_html = ""
        self.regenerate_targets: list[str] = []
        self.target_pages = 1
        self.progress_callback = None

    def set_regeneration_context(self, context_html: str, targets: list[str] | None = None):
        self.regeneration_context_html = context_html or ""
        self.regenerate_targets = list(targets or [])

    def set_target_pages(self, target_pages: int):
        self.target_pages = target_pages if target_pages in {1, 2} else 1

    def set_progress_callback(self, callback):
        self.progress_callback = callback

    def set_resume_object(self, resume_object):
         self.resume_object = resume_object
         

    def _create_resume(self, gpt_answerer: Any, style_path):
        # Imposta il resume nell'oggetto gpt_answerer
        gpt_answerer.set_resume(self.resume_object)
        gpt_answerer.set_regeneration_context(
            self.regeneration_context_html,
            self.regenerate_targets,
        )
        gpt_answerer.set_target_pages(self.target_pages)
        gpt_answerer.set_progress_callback(self.progress_callback)
        
        # Leggi il template HTML
        template = Template(global_config.html_template)
        
        try:
            with open(style_path, "r", encoding="utf-8") as f:
                style_css = f.read()  # Correzione: chiama il metodo `read` con le parentesi
        except FileNotFoundError:
            raise ValueError(f"Il file di stile non è stato trovato nel percorso: {style_path}")
        except Exception as e:
            raise RuntimeError(f"Errore durante la lettura del file CSS: {e}")
        
        # Genera l'HTML del resume
        body_html = gpt_answerer.generate_html_resume()
        
        # 获取简历语言用于HTML lang属性
        lang_code = global_config.RESUME_LANGUAGE if global_config.RESUME_LANGUAGE else "zh"
        lang_attr = "zh" if lang_code in ["zh", "zh-cn"] else ("en" if lang_code == "en" else "zh")
        
        # Applica i contenuti al template
        full_html = template.substitute(body=body_html, style_css=style_css, lang=lang_attr)
        return add_default_profile_photo(full_html)

    def create_resume(self, style_path):
        strings = load_module(global_config.STRINGS_MODULE_RESUME_PATH, global_config.STRINGS_MODULE_NAME)
        gpt_answerer = LLMResumer(global_config.API_KEY, strings)
        return self._create_resume(gpt_answerer, style_path)

    def create_resume_job_description_text(self, style_path: str, job_description_text: str):
        strings = load_module(global_config.STRINGS_MODULE_RESUME_JOB_DESCRIPTION_PATH, global_config.STRINGS_MODULE_NAME)
        gpt_answerer = LLMResumeJobDescription(global_config.API_KEY, strings)
        gpt_answerer.set_progress_callback(self.progress_callback)
        gpt_answerer.set_job_description_from_text(job_description_text)
        return self._create_resume(gpt_answerer, style_path)

    def create_cover_letter_job_description(self, style_path: str, job_description_text: str):
        strings = load_module(global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH, global_config.STRINGS_MODULE_NAME)
        gpt_answerer = LLMCoverLetterJobDescription(global_config.API_KEY, strings)
        gpt_answerer.set_resume(self.resume_object)
        gpt_answerer.set_job_description_from_text(job_description_text)
        cover_letter_html = gpt_answerer.generate_cover_letter()
        template = Template(global_config.html_template)
        with open(style_path, "r", encoding="utf-8") as f:
            style_css = f.read()
        # 获取简历语言用于 HTML lang 属性
        lang_code = global_config.RESUME_LANGUAGE if global_config.RESUME_LANGUAGE else "zh"
        lang_attr = "zh" if lang_code in ["zh", "zh-cn"] else ("en" if lang_code == "en" else "zh")
        return template.substitute(body=cover_letter_html, style_css=style_css, lang=lang_attr)
