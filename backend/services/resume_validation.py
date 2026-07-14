"""Business validation for resume YAML completeness."""

from __future__ import annotations

from typing import Any

import yaml


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _has_content(value: Any) -> bool:
    """Treat parser-created empty placeholder objects as absent."""
    if isinstance(value, dict):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    return value not in (None, "", False)


def validate_resume_data(data: Any) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    def add(target: list[dict[str, str]], path: str, message: str) -> None:
        target.append({"path": path, "message": message})

    if not isinstance(data, dict):
        add(errors, "$", "YAML 顶层必须是对象结构")
        return {"valid": False, "errors": errors, "warnings": warnings}

    personal = data.get("personal_information")
    if not isinstance(personal, dict):
        personal = {}
        add(errors, "personal_information", "缺少个人信息")
    if not (_present(personal.get("name")) or _present(personal.get("surname"))):
        add(errors, "personal_information.name", "姓名不能为空")
    has_email = _present(personal.get("email"))
    has_phone = _present(personal.get("phone"))
    if not (has_email or has_phone):
        add(errors, "personal_information.email/phone", "邮箱或电话号码至少填写一项")
    if not has_email:
        add(warnings, "personal_information.email", "建议填写邮箱")
    if not has_phone:
        add(warnings, "personal_information.phone", "建议填写电话号码")
    if not (_present(personal.get("city")) or _present(personal.get("country"))):
        add(warnings, "personal_information.city", "建议填写所在城市或国家")

    education = data.get("education_details") or []
    experience = data.get("experience_details") or []
    projects = data.get("projects") or []
    meaningful_education = [item for item in education if _has_content(item)] if isinstance(education, list) else []
    meaningful_experience = [item for item in experience if _has_content(item)] if isinstance(experience, list) else []
    meaningful_projects = [item for item in projects if _has_content(item)] if isinstance(projects, list) else []
    if not any((meaningful_education, meaningful_experience, meaningful_projects)):
        add(errors, "education_details/experience_details/projects", "教育、工作经历或项目经历至少填写一个板块")

    for index, item in enumerate(education if isinstance(education, list) else []):
        if not _has_content(item):
            continue
        if not isinstance(item, dict):
            add(warnings, f"education_details[{index}]", "教育经历格式不正确，已忽略")
            continue
        if not _present(item.get("institution")):
            add(warnings, f"education_details[{index}].institution", "建议补充学校/机构")
        if not (_present(item.get("education_level")) or _present(item.get("field_of_study"))):
            add(warnings, f"education_details[{index}].education_level", "建议补充学历或专业")

    for index, item in enumerate(experience if isinstance(experience, list) else []):
        if not _has_content(item):
            continue
        if not isinstance(item, dict):
            add(warnings, f"experience_details[{index}]", "工作经历格式不正确，已忽略")
            continue
        for field, label in (("company", "公司"), ("position", "职位"), ("employment_period", "任职时间")):
            if not _present(item.get(field)):
                add(warnings, f"experience_details[{index}].{field}", f"建议补充{label}")
        if not item.get("key_responsibilities"):
            add(warnings, f"experience_details[{index}].key_responsibilities", "建议填写至少一项工作职责或成果")

    for index, item in enumerate(projects if isinstance(projects, list) else []):
        if not _has_content(item):
            continue
        if not isinstance(item, dict):
            add(warnings, f"projects[{index}]", "项目经历格式不正确，已忽略")
            continue
        if not _present(item.get("name")):
            add(warnings, f"projects[{index}].name", "建议补充项目名称")
        if not _present(item.get("description")):
            add(warnings, f"projects[{index}].description", "建议补充项目描述")

    if not meaningful_education:
        add(warnings, "education_details", "教育经历为空，请确认是否符合实际情况")
    if not meaningful_experience:
        add(warnings, "experience_details", "工作经历为空，请确认是否符合实际情况")

    return {"valid": not errors, "errors": errors, "warnings": warnings}


def validate_resume_yaml(content: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        return {
            "valid": False,
            "errors": [{"path": "$", "message": f"YAML 语法错误：{exc}"}],
            "warnings": [],
        }
    return validate_resume_data(data)
