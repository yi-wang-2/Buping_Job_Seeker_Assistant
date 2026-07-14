from backend.services.resume_validation import validate_resume_data, validate_resume_yaml


def test_empty_resume_is_blocked():
    result = validate_resume_data({})
    assert result["valid"] is False
    paths = {item["path"] for item in result["errors"]}
    assert "personal_information.name" in paths
    assert "personal_information.email/phone" in paths
    assert "education_details/experience_details/projects" in paths


def test_new_graduate_resume_with_education_is_valid():
    result = validate_resume_data({
        "personal_information": {"name": "张三", "email": "zhangsan@example.com"},
        "education_details": [{"institution": "某大学", "field_of_study": "计算机"}],
        "experience_details": [],
        "projects": [],
    })
    assert result["valid"] is True
    assert result["errors"] == []


def test_incomplete_existing_experience_only_warns():
    result = validate_resume_data({
        "personal_information": {"name": "张三", "phone": "13800000000"},
        "experience_details": [{"company": "某公司"}],
    })
    assert result["valid"] is True
    paths = {item["path"] for item in result["warnings"]}
    assert "experience_details[0].position" in paths
    assert "experience_details[0].employment_period" in paths


def test_empty_placeholder_entries_are_ignored():
    result = validate_resume_data({
        "personal_information": {"name": "张三", "email": "zhangsan@example.com"},
        "education_details": [{"institution": "", "education_level": ""}],
        "experience_details": [{"company": "", "position": "", "employment_period": ""}],
        "projects": [{"name": "", "description": ""}],
    })
    assert result["valid"] is False
    paths = {item["path"] for item in result["errors"]}
    assert paths == {"education_details/experience_details/projects"}


def test_yaml_syntax_error_is_blocked():
    result = validate_resume_yaml("personal_information: [")
    assert result["valid"] is False
    assert result["errors"][0]["path"] == "$"
