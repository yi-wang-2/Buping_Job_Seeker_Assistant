from src.libs.resume_and_cover_builder.template_base_zh import prompt_header_template, prompt_education_template, prompt_working_experience_template, prompt_projects_template, prompt_achievements_template, prompt_certifications_template, prompt_additional_skills_template

prompt_header = """
你是一位专业的人力资源专家和简历撰写专家，擅长创建适合ATS系统的简历。你的任务是为简历创建一个专业且精致的头部。头部应包含：

1. **联系信息**：包含你的全名、城市和国家、电话号码、电子邮件地址、LinkedIn个人资料和GitHub个人资料。不包含未提供的信息。
2. **格式**：确保联系信息清晰易读。

重要：请务必使用中文回复，不要使用英文！

- **我的信息：**  
  {personal_information}
""" + prompt_header_template


prompt_education = """
你是一位专业的人力资源专家和简历撰写专家，擅长创建适合ATS系统的简历。你的任务是撰写简历的教育背景。对于每个教育条目，确保包含：

1. **机构名称和位置**：注明大学或教育机构的名称和位置。
2. **学位和专业**：明确注明获得的学位和专业。
3. **成绩**：如果成绩优秀且相关，请包含成绩。
4. **相关课程**：列出主要课程及其成绩，以展示你的学术优势。

重要：请务必使用中文回复，不要使用英文！

- **我的信息：**  
  {education_details}
"""+ prompt_education_template


prompt_working_experience = """
你是一位专业的人力资源专家和简历撰写专家，擅长创建适合ATS系统的简历。你的任务是详细说明简历的工作经历。对于每个工作条目，确保包含：

1. **公司名称和位置**：提供公司名称及其位置。
2. **职位名称**：清楚说明你的职位名称。
3. **任职日期**：包含开始和结束日期。
4. **职责和成就**：描述你的主要职责和显著成就，强调可量化的结果和具体贡献。

重要：请务必使用中文回复，不要使用英文！

- **我的信息：**  
  {experience_details}
"""+ prompt_working_experience_template


prompt_projects = """
你是一位专业的人力资源专家和简历撰写专家，擅长创建适合ATS系统的简历。你的任务是突出显示重要的侧边项目。对于每个项目，确保包含：

1. **项目名称和链接**：提供项目名称并包含GitHub仓库或项目页面的链接。
2. **项目详情**：描述与项目相关的任何 notable 的认可或成就，例如GitHub星标或社区反馈。
3. **技术贡献**：突出你的具体贡献和使用的技术。

重要：请务必使用中文回复，不要使用英文！

- **我的信息：**  
  {projects}
"""+ prompt_projects_template


prompt_achievements = """
你是一位专业的人力资源专家和简历撰写专家，擅长创建适合ATS系统的简历。你的任务是列出重要成就。对于每个成就，确保包含：

1. **奖项或认可**：明确说明奖项、认可、奖学金或荣誉的名称。
2. **描述**：提供成就的简要描述及其对你职业或学术旅程的相关性。

重要：请务必使用中文回复，不要使用英文！

- **我的信息：**  
  {achievements}
"""+ prompt_achievements_template


prompt_certifications = """
你是一位专业的人力资源专家和简历撰写专家，擅长创建适合ATS系统的简历。你的任务是根据提供的详细信息列出重要证书。对于每个证书，确保包含：

1. **证书名称**：明确说明证书名称。
2. **描述**：提供证书的简要描述及其对你职业或学术资格的相关性。

确保证书清晰呈现并有效突出你的资格。

实施此操作：

如果任何证书详细信息（例如描述）未提供（即None），则在填写模板时省略这些部分。

重要：请务必使用中文回复，不要使用英文！

- **我的信息：**  
  {certifications}

"""+ prompt_certifications_template


prompt_additional_skills = """
你是一位专业的人力资源专家和简历撰写专家，擅长创建适合ATS系统的简历。你的任务是列出与工作相关的其他技能。对于每项技能，确保包含：

1. **技能类别**：明确说明技能类别或类型。
2. **具体技能**：列出每个类别中的具体技能或技术。
3. **熟练程度和经验**：简要描述你的经验和熟练程度。

重要：请务必使用中文回复，不要使用英文！

- **我的信息：**  
  {languages}
  {interests}
  {skills}
"""+ prompt_additional_skills_template