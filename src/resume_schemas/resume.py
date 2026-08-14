from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
import re
import yaml
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class ResumeModel(BaseModel):
    """Base model for the canonical resume YAML.

    Unknown fields are preserved for forward compatibility instead of being
    silently discarded. All fields currently supported by the application are
    nevertheless declared explicitly below.
    """

    model_config = ConfigDict(extra="allow")



class PersonalInformation(ResumeModel):
    full_name: Optional[str] = None
    name: Optional[str] = None
    surname: Optional[str] = None
    date_of_birth: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    zip_code: Optional[str] = None  # 中国不需要
    phone_prefix: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    github: Optional[str] = None  # 改为 str 类型避免URL验证
    linkedin: Optional[str] = None  # 改为 str 类型避免URL验证
    wechat: Optional[str] = None  # 微信 - 中国求职市场必备

    @field_validator("email", mode="before")
    @classmethod
    def normalize_empty_email(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class EducationAdditionalInfo(ResumeModel):
    is_211: Optional[bool] = None
    is_double_first_class: Optional[bool] = None
    college: Optional[str] = None
    study_mode: Optional[str] = None
    honors: Optional[str] = None
    relevant_courses: Optional[str] = None


class EducationDetails(ResumeModel):
    education_level: Optional[str] = None
    institution: Optional[str] = None
    field_of_study: Optional[str] = None
    final_evaluation_grade: Optional[str] = None
    start_date: Optional[str] = None
    year_of_completion: Optional[int] = None
    research_direction: Optional[str] = None
    research_topics: Optional[List[str]] = None
    additional_info: Optional[EducationAdditionalInfo] = None
    exam: Optional[Union[List[Dict[str, str]], Dict[str, str]]] = None

    @field_validator("year_of_completion", mode="before")
    @classmethod
    def normalize_year_of_completion(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            match = re.search(r"\d{4}", value)
            if match:
                return int(match.group(0))
        return value


class ExperienceDetails(ResumeModel):
    position: Optional[str] = None
    company: Optional[str] = None
    employment_period: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    key_responsibilities: Optional[List[Dict[str, str]]] = None
    skills_acquired: Optional[List[str]] = None


class Project(ResumeModel):
    name: Optional[str] = None
    description: Optional[str] = None
    link: Optional[str] = None  # 改为 str 类型避免URL验证


class Achievement(ResumeModel):
    name: Optional[str] = None
    description: Optional[str] = None


class Certifications(ResumeModel):
    name: Optional[str] = None
    description: Optional[str] = None


class Language(ResumeModel):
    language: Optional[str] = None
    proficiency: Optional[str] = None


class Availability(ResumeModel):
    notice_period: Optional[str] = None


class SalaryExpectations(ResumeModel):
    salary_range_usd: Optional[str] = None


class SelfIdentification(ResumeModel):
    gender: Optional[str] = None
    pronouns: Optional[str] = None
    veteran: Optional[str] = None
    disability: Optional[str] = None
    ethnicity: Optional[str] = None


class LegalAuthorization(ResumeModel):
    eu_work_authorization: Optional[str] = None
    us_work_authorization: Optional[str] = None
    requires_us_visa: Optional[str] = None
    requires_us_sponsorship: Optional[str] = None
    requires_eu_visa: Optional[str] = None
    legally_allowed_to_work_in_eu: Optional[str] = None
    legally_allowed_to_work_in_us: Optional[str] = None
    requires_eu_sponsorship: Optional[str] = None
    canada_work_authorization: Optional[str] = None
    requires_canada_visa: Optional[str] = None
    legally_allowed_to_work_in_canada: Optional[str] = None
    requires_canada_sponsorship: Optional[str] = None
    uk_work_authorization: Optional[str] = None
    requires_uk_visa: Optional[str] = None
    legally_allowed_to_work_in_uk: Optional[str] = None
    requires_uk_sponsorship: Optional[str] = None


class WorkPreferences(ResumeModel):
    remote_work: Optional[str] = None
    in_person_work: Optional[str] = None
    open_to_relocation: Optional[str] = None
    willing_to_complete_assessments: Optional[str] = None
    willing_to_undergo_drug_tests: Optional[str] = None
    willing_to_undergo_background_checks: Optional[str] = None


class Resume(ResumeModel):
    professional_summary: Optional[str] = None
    personal_information: Optional[PersonalInformation] = None
    education_details: Optional[List[EducationDetails]] = None
    experience_details: Optional[List[ExperienceDetails]] = None
    projects: Optional[List[Project]] = None
    achievements: Optional[List[Achievement]] = None
    certifications: Optional[List[Certifications]] = None
    languages: Optional[List[Language]] = None
    interests: Optional[List[str]] = None
    availability: Optional[Availability] = None
    salary_expectations: Optional[SalaryExpectations] = None
    self_identification: Optional[SelfIdentification] = None
    legal_authorization: Optional[LegalAuthorization] = None
    work_preferences: Optional[WorkPreferences] = None

    @staticmethod
    def normalize_exam_format(exam):
        if isinstance(exam, dict):
            return [{k: v} for k, v in exam.items()]
        return exam

    def __init__(self, yaml_str: str):
        try:
            # Parse the YAML string
            data = yaml.safe_load(yaml_str)

            if 'education_details' in data:
                for ed in data['education_details']:
                    # Backward compatibility for the original public schema.
                    aliases = {
                        'degree': 'education_level',
                        'university': 'institution',
                        'gpa': 'final_evaluation_grade',
                        'graduation_year': 'year_of_completion',
                    }
                    for old_key, new_key in aliases.items():
                        if new_key not in ed and old_key in ed:
                            ed[new_key] = ed.pop(old_key)
                    # Some historical examples nested exam under
                    # additional_info. The canonical location is directly on
                    # the education entry.
                    additional = ed.get('additional_info')
                    if isinstance(additional, dict) and 'exam' in additional and 'exam' not in ed:
                        ed['exam'] = additional.pop('exam')
                    if 'exam' in ed:
                        ed['exam'] = self.normalize_exam_format(ed['exam'])

            # Create an instance of Resume from the parsed data
            super().__init__(**data)
        except yaml.YAMLError as e:
            raise ValueError("Error parsing YAML file.") from e
        except Exception as e:
            raise Exception(f"Unexpected error while parsing YAML: {e}") from e


    def _process_personal_information(self, data: Dict[str, Any]) -> PersonalInformation:
        try:
            return PersonalInformation(**data)
        except TypeError as e:
            raise TypeError(f"Invalid data for PersonalInformation: {e}") from e
        except AttributeError as e:
            raise AttributeError(f"AttributeError in PersonalInformation: {e}") from e
        except Exception as e:
            raise Exception(f"Unexpected error in PersonalInformation processing: {e}") from e

    def _process_education_details(self, data: List[Dict[str, Any]]) -> List[EducationDetails]:
        education_list = []
        for edu in data:
            try:
                exams = [Exam(name=k, grade=v) for k, v in edu.get('exam', {}).items()]
                education = EducationDetails(
                    education_level=edu.get('education_level'),
                    institution=edu.get('institution'),
                    field_of_study=edu.get('field_of_study'),
                    final_evaluation_grade=edu.get('final_evaluation_grade'),
                    start_date=edu.get('start_date'),
                    year_of_completion=edu.get('year_of_completion'),
                    exam=exams
                )
                education_list.append(education)
            except KeyError as e:
                raise KeyError(f"Missing field in education details: {e}") from e
            except TypeError as e:
                raise TypeError(f"Invalid data for Education: {e}") from e
            except AttributeError as e:
                raise AttributeError(f"AttributeError in Education: {e}") from e
            except Exception as e:
                raise Exception(f"Unexpected error in Education processing: {e}") from e
        return education_list

    def _process_experience_details(self, data: List[Dict[str, Any]]) -> List[ExperienceDetails]:
        experience_list = []
        for exp in data:
            try:
                key_responsibilities = [
                    Responsibility(description=list(resp.values())[0])
                    for resp in exp.get('key_responsibilities', [])
                ]
                skills_acquired = [str(skill) for skill in exp.get('skills_acquired', [])]
                experience = ExperienceDetails(
                    position=exp['position'],
                    company=exp['company'],
                    employment_period=exp['employment_period'],
                    location=exp['location'],
                    industry=exp['industry'],
                    key_responsibilities=key_responsibilities,
                    skills_acquired=skills_acquired
                )
                experience_list.append(experience)
            except KeyError as e:
                raise KeyError(f"Missing field in experience details: {e}") from e
            except TypeError as e:
                raise TypeError(f"Invalid data for Experience: {e}") from e
            except AttributeError as e:
                raise AttributeError(f"AttributeError in Experience: {e}") from e
            except Exception as e:
                raise Exception(f"Unexpected error in Experience processing: {e}") from e
        return experience_list


@dataclass
class Exam:
    name: str
    grade: str

@dataclass
class Responsibility:
    description: str
