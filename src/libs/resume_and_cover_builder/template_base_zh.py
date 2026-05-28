"""
这个模块用于存储简历模板的中文版本
"""
# 中文模板库

prompt_cover_letter_template = """
- **使用的模板**
```
<section id="cover-letter">
    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px;">
        <div>
            <p>[您的姓名]</p>
            <p>[您的地址]</p>
            <p>[城市, 省份 邮编]</p>
            <p>[您的邮箱]</p>
            <p>[您的电话号码]</p>
        </div>
        <div style="text-align: right;">
            <p>[公司名称]</p>
        </div>
    </div>
    <div>
    <p>[收件人团队]，</p>
    <p>[开头段落：介绍自己并说明您申请的职位。]</p>
    <p>[正文段落：突出您的资格、经验和如何符合职位要求。]</p>
    <p>[结尾段落：表达您对职位的热情，并感谢收件人的考虑。]</p>
    <p>此致</p>
    <p>[您的姓名]</p>
    <p>[日期]</p>
    </div>
</section>
```
请以HTML格式提供结果，仅提供简历的HTML代码，不包含任何解释或其他文字，也不包含```html ```
"""

prompt_header_template = """
- **使用的模板**
```
<header>
  <h1>[姓名]</h1>
  <div class="contact-info"> 
    <p class="fas fa-map-marker-alt">
      <span>[您的城市, 国家]</span>
    </p> 
    <p class="fas fa-phone">
      <span>[您的国际区号 电话号码]</span>
    </p> 
    <p class="fas fa-envelope">
      <span>[您的邮箱]</span>
    </p> 
    <p class="fab fa-linkedin">
      <a href="[领英链接]">领英</a>
    </p> 
    <p class="fab fa-github">
      <a href="[GitHub链接]">GitHub</a>
    </p> 
  </div>
</header>
```
请以HTML格式提供结果，仅提供简历的HTML代码，不包含任何解释或其他文字，也不包含```html ```
"""

prompt_education_template = """
- **使用的模板**
```
<section id="education">
    <h2>教育背景</h2>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name">[大学名称]</span>
          <span class="entry-location">[地点] </span>
      </div>
      <div class="entry-details">
          <span class="entry-title">[学位] | [专业] | 成绩: [您的成绩]</span>
          <span class="entry-year">[开始年份] – [结束年份]  </span>
      </div>
      <ul class="compact-list">
          <li>[课程名称] → 成绩: [成绩]</li>
          <li>[课程名称] → 成绩: [成绩]</li>
          <li>[课程名称] → 成绩: [成绩]</li>
          <li>[课程名称] → 成绩: [成绩]</li>
          <li>[课程名称] → 成绩: [成绩]</li>
      </ul>
    </div>
</section>
```
请以HTML格式提供结果，仅提供简历的HTML代码，不包含任何解释或其他文字，也不包含```html ```
"""

prompt_working_experience_template = """
- **使用的模板**
```
<section id="work-experience">
    <h2>工作经验</h2>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name">[公司名称]</span>
          <span class="entry-location">[地点]</span>
      </div>
      <div class="entry-details">
          <span class="entry-title">[您的职位]</span>
          <span class="entry-year">[开始日期] – [结束日期] </span>
      </div>
      <ul class="compact-list">
          <li>[描述您在这个职位上的职责和成就] </li>
          <li>[描述您参与的关键项目或使用的技术]  </li>
          <li>[提及任何显著的成就或成果]</li>
      </ul>
    </div>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name">[公司名称]</span>
          <span class="entry-location">[地点]</span>
      </div>
      <div class="entry-details">
          <span class="entry-title">[您的职位]</span>
          <span class="entry-year">[开始日期] – [结束日期] </span>
      </div>
      <ul class="compact-list">
          <li>[描述您在这个职位上的职责和成就] </li>
          <li>[描述您参与的关键项目或使用的技术]  </li>
          <li>[提及任何显著的成就或成果]</li>
      </ul>
    </div>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name">[公司名称]</span>
          <span class="entry-location">[地点]</span>
      </div>
      <div class="entry-details">
          <span class="entry-title">[您的职位]</span>
          <span class="entry-year">[开始日期] – [结束日期] </span>
      </div>
      <ul class="compact-list">
          <li>[描述您在这个职位上的职责和成就] </li>
          <li>[描述您参与的关键项目或使用的技术]  </li>
          <li>[提及任何显著的成就或成果]</li>
      </ul>
    </div>
</section>
```
请以HTML格式提供结果，仅提供简历的HTML代码，不包含任何解释或其他文字，也不包含```html ```
"""

prompt_projects_template = """
- **使用的模板**
```
<section id="side-projects">
    <h2>项目经验</h2>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name"><i class="fab fa-github"></i> <a href="[GitHub仓库链接]">[项目名称]</a></span>
      </div>
      <ul class="compact-list">
          <li>[描述任何显著的认可或成就]</li>
          <li>[描述任何显著的认可或成就]</li>
      </ul>
    </div>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name"><i class="fab fa-github"></i> <a href="[GitHub仓库链接]">[项目名称]</a></span>
      </div>
      <ul class="compact-list">
          <li>[描述任何显著的认可或成就]</li>
          <li>[描述任何显著的认可或成就]</li>
      </ul>
    </div>
    <div class="entry">
      <div class="entry-header">
          <span class="entry-name"><i class="fab fa-github"></i> <a href="[GitHub仓库链接]">[项目名称]</a></span>
      </div>
      <ul class="compact-list">
          <li>[描述任何显著的认可或成就]</li>
          <li>[描述任何显著的认可或成就]</li>
      </ul>
    </div>
</section>
```
请以HTML格式提供结果，仅提供简历的HTML代码，不包含任何解释或其他文字，也不包含```html ```
"""

prompt_achievements_template = """
- **使用的模板**
```
<section id="achievements">
    <h2>成就</h2>
    <ul class="compact-list">
      <li><strong>[奖项或认可]:</strong> [描述]</li>
      <li><strong>[奖项或认可]:</strong> [描述]</li>
      <li><strong>[奖项或认可]:</strong> [描述]</li>
    </ul>
</section>
```
请以HTML格式提供结果，仅提供简历的HTML代码，不包含任何解释或其他文字，也不包含```html ```
"""

prompt_certifications_template = """
- **使用的模板**
```
<section id="certifications">
    <h2>证书</h2>
    <ul class="compact-list">
      <li><strong>[证书名称]:</strong> [描述]</li>
      <li><strong>[证书名称]:</strong> [描述]</li>
    </ul>
</section>
```
请以HTML格式提供结果，仅提供简历的HTML代码，不包含任何解释或其他文字，也不包含```html ```
"""

prompt_additional_skills_template = """
- **使用的模板**
```
<section id="skills-languages">
    <h2>其他技能</h2>
    <div class="two-column">
      <ul class="compact-list">
          <li>[具体技能或技术]</li>
          <li>[具体技能或技术]</li>
          <li>[具体技能或技术]</li>
          <li>[具体技能或技术]</li>
          <li>[具体技能或技术]</li>
          <li>[具体技能或技术]</li>
      </ul>
      <ul class="compact-list">
          <li>[具体技能或技术]</li>
          <li>[具体技能或技术]</li>
          <li>[具体技能或技术]</li>
          <li>[具体技能或技术]</li>
          <li>[具体技能或技术]</li>
          <li><strong>语言能力:</strong> </li>
      </ul>
    </div>
</section>
```
请以HTML格式提供结果，仅提供简历的HTML代码，不包含任何解释或其他文字，也不包含```html ```
"""