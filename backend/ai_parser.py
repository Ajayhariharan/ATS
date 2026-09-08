import json
import re
import os
import httpx
import logging
from typing import Optional, Dict, Any, List, Tuple
import time
from datetime import datetime
from config import config

# Logger setup
logger = logging.getLogger("ATSParser")
logger.setLevel(logging.INFO)

async def call_openrouter_gemini(prompt: str, system_prompt: str = "You are an expert Enterprise ATS qualification parser. Return only valid JSON.") -> Optional[str]:
    """
    Call OpenRouter Gemini model exclusively.
    """
    if not config.OPENROUTER_API_KEY or config.OPENROUTER_API_KEY.startswith("your_"):
        print("[AI Gemini] [WARN] OPENROUTER_API_KEY not configured in .env")
        return None

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "EnterpriseATS/1.0",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Enterprise ATS Gemini Parser"
    }
    
    payload = {
        "model": config.OPENROUTER_MODEL or "google/gemini-2.5-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 3000,
        "response_format": {"type": "json_object"}
    }
    
    start_time = time.time()
    print(f"[AI Gemini] [SEND] Sending request to OpenRouter (Model: {config.OPENROUTER_MODEL}, Prompt: {len(prompt)} chars)...")
    
    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            response = await client.post(config.OPENROUTER_URL, headers=headers, json=payload)
            duration = time.time() - start_time
            if response.status_code == 200:
                data = response.json()
                msg = data['choices'][0]['message']
                content = msg.get('content') or ''
                usage = data.get('usage', {})
                total_tokens = usage.get('total_tokens', 'N/A')
                print(f"[AI Gemini] [OK] Gemini response received in {duration:.2f}s (Tokens: {total_tokens}, Chars: {len(content)})")
                return content
            else:
                print(f"[AI Gemini] [ERROR] OpenRouter status {response.status_code} in {duration:.2f}s: {response.text}")
                return None
    except Exception as e:
        duration = time.time() - start_time
        print(f"[AI Gemini] [ERROR] OpenRouter connection failed after {duration:.2f}s: {e}")
        return None

MONTHS_MAP = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
    'apr': 4, 'april': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
    'aug': 8, 'august': 8, 'sep': 9, 'september': 9, 'oct': 10, 'october': 10,
    'nov': 11, 'november': 11, 'dec': 12, 'december': 12
}

def calculate_years_experience(text: str) -> float:
    """Extract years of experience from text, accurately parsing single months, date ranges, and numeric periods"""
    if not text:
        return 0.0
        
    t_clean = text.strip().lower()
    t_clean = t_clean.replace('\ufffd', '-').replace('\u2013', '-').replace('\u2014', '-')
    current_year = datetime.now().year
    current_month = datetime.now().month
    total_months = 0.0

    month_regex = r'(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?'
    
    # 1. 'Dec 2023 to May 2024' or 'March 2023 - Present'
    pattern_month_range = rf'{month_regex}\s+(\d{{4}})\s*(?:[-–至to\s]+)\s*(?:{month_regex}\s+)?(\d{{4}}|present|current|now|till\s*date)'
    for m in re.finditer(pattern_month_range, t_clean):
        sm_name, sy, em_name, ey = m.groups()
        start_m = MONTHS_MAP.get(sm_name, 1)
        start_y = int(sy)
        if ey in ('present', 'current', 'now') or 'till' in ey:
            end_y, end_m = current_year, current_month
        else:
            end_y = int(ey)
            end_m = MONTHS_MAP.get(em_name, 12) if em_name else 12
        months = (end_y - start_y) * 12 + (end_m - start_m + 1)
        if months > 0:
            total_months += months

    # 2. 'MM/YYYY - MM/YYYY' (e.g. 06/2023 - 12/2024)
    if total_months == 0:
        pattern_num_range = r'(\d{1,2})[\/\.-](\d{4})\s*(?:[-–至to\s]+)\s*(\d{1,2})[\/\.-](\d{4}|present|current)'
        for m in re.finditer(pattern_num_range, t_clean):
            sm, sy, em, ey = m.groups()
            start_m, start_y = int(sm), int(sy)
            if ey in ('present', 'current'):
                end_y, end_m = current_year, current_month
            else:
                end_y, end_m = int(ey), int(em)
            months = (end_y - start_y) * 12 + (end_m - start_m + 1)
            if months > 0:
                total_months += months

    # 3. '2022 to 2025' or '2022 - Present' (Year spans)
    if total_months == 0:
        pattern_years = r'\b(20\d{2}|19\d{2})\s*(?:[-–至to\s]+)\s*(20\d{2}|19\d{2}|present|current|now|till\s*date)\b'
        for m in re.finditer(pattern_years, t_clean):
            sy, ey = m.groups()
            start_y = int(sy)
            end_y = current_year if ey in ('present', 'current', 'now') or 'till' in ey else int(ey)
            if end_y >= start_y:
                total_months += max(1, (end_y - start_y)) * 12

    # 4. Explicit token: "3 years", "2.5 yrs", "6 months"
    if total_months == 0:
        matches = re.findall(r'(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\b', t_clean)
        if matches:
            return float(matches[0])
        month_matches = re.findall(r'(\d+)\s*(?:months?|mos?)\b', t_clean)
        if month_matches:
            total_months = sum(float(m) for m in month_matches)

    # 5. Single Month Point: "Jun 2025" or "Jan 2020" or "Dec 2025" (1 month nominal for single-month project/internship)
    if total_months == 0:
        pattern_single_month = rf'\b{month_regex}\s+(\d{{4}})\b'
        m = re.search(pattern_single_month, t_clean)
        if m:
            total_months = 1.0

    if total_months > 0:
        return round(total_months / 12.0, 2)

    return 0.0

def parse_skills_fallback(text: str) -> List[str]:
    """Dynamic regex-based skills extraction fallback across common technologies"""
    common_skills = [
        "Python", "SQL", "Machine Learning", "AWS", "Docker", "FastAPI",
        "React", "Node.js", "Java", "JavaScript", "TypeScript", "TensorFlow",
        "PyTorch", "Pandas", "NumPy", "Scikit-learn", "Kubernetes", "Git",
        "Jenkins", "Azure", "GCP", "Spark", "Django", "Flask", "PostgreSQL",
        "MongoDB", "Redis", "HTML", "CSS", "Angular", "Vue.js", "C#", "C++", "C", "PHP",
        "Data Visualization", "Statistical Analysis", "Tableau", "PowerBI", "Deep Learning",
        "NLP", "Computer Vision", "Time Series", "Communication", "Leadership", "Management"
    ]
    return [s for s in common_skills if re.search(r'\b' + re.escape(s) + r'\b', text, re.IGNORECASE)]

async def parse_resume_complete(text: str, jd_text: str = "", structured_content: Optional[dict] = None) -> dict:
    """
    Candidate Resume Parsing using OpenRouter Gemini with dynamic layout parser fallback.
    """
    # 1. Build prompt for OpenRouter Gemini
    prompt = f"""
    You are an expert Enterprise ATS qualification parser. Extract candidate details from the resume below into clean valid JSON.
    
    Resume Text:
    {text[:4000]}
    
    Output JSON format:
    {{
        "candidate_name": "Full Name",
        "email": "email@example.com",
        "phone": "phone number",
        "skills": ["Skill1", "Skill2", "Skill3"],
        "experience": [
            {{"title": "Role Title", "company": "Company", "period": "Duration", "bullets": ["Achievement 1"]}}
        ],
        "education": [
            {{"degree": "Degree", "institution": "College/University", "period": "Years", "score": "GPA/Score"}}
        ],
        "summary": "Professional candidate summary",
        "years_experience": 0.0
    }}
    
    Return ONLY valid JSON.
    """
    
async def refine_experience_and_projects_ai(
    exp_text: str = "",
    proj_text: str = "",
    edu_text: str = "",
    fallback_exp: Optional[List[Dict[str, Any]]] = None,
    fallback_proj: Optional[List[Dict[str, Any]]] = None,
    fallback_edu: Optional[List[Dict[str, Any]]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Selectively sends raw Work Experience, Projects, and Education text to Gemini
    to accurately parse and refine job titles, companies, dates, bullets, and education qualifications.
    """
    fallback_exp = fallback_exp or []
    fallback_proj = fallback_proj or []
    fallback_edu = fallback_edu or []

    exp_clean = (exp_text or "").strip()
    proj_clean = (proj_text or "").strip()
    edu_clean = (edu_text or "").strip()

    # If all three sections are empty or minimal, skip LLM call
    if len(exp_clean) < 15 and len(proj_clean) < 15 and len(edu_clean) < 10:
        print("[AI Gemini] Experience, Projects, and Education sections empty. Skipping LLM call.")
        return fallback_exp, fallback_proj, fallback_edu

    prompt = f"""
You are an expert Enterprise ATS Resume Structure Parsing Engine.
Analyze ONLY the provided Work Experience, Projects, and Education raw text segments below.
Extract and clean up all roles, projects, and educational qualifications into a strictly valid JSON object matching this schema exactly:

{{
  "experience_records": [
    {{
      "title": "Exact Job Title / Designation",
      "company": "Company / Organization Name (and Location/Client if present)",
      "period": "Date range (e.g. '2023 - Present' or 'Jan 2024 - Dec 2024')",
      "bullets": ["Responsibility, accomplishment, or metric bullet point 1", "bullet point 2"]
    }}
  ],
  "project_records": [
    {{
      "title": "Exact Full Project Title including any tools/technologies listed in the title line (e.g. 'Smart Water Pressure Management System — Flask, Python, ML, Epanet, Supabase' or 'Docsheild — MERN Stack, Blockchain, Web3.js')",
      "organization": "Project Type or Organization ONLY (e.g. 'Independent Project', 'Academic Project', or Client Name). Do NOT append the tech stack here.",
      "period": "Date range or duration (e.g. 'Jan 2026 – Apr 2026' or 'Jul 2025 – Oct 2025')",
      "bullets": ["Project detail, architecture, or outcome bullet point 1"]
    }}
  ],
  "education_records": [
    {{
      "degree": "Degree / Qualification (e.g. 'Bachelor of Science, Computer Science', 'M.Sc. Data Science', 'Higher Secondary (HSC)', 'SSLC')",
      "institution": "University / College / School Name (e.g. 'UC Berkeley', 'Stanford University', 'PKN Higher Secondary School')",
      "period": "Years or Duration (e.g. '2015 - 2019' or '2019')",
      "score": "Score, GPA, or Percentage if present (e.g. 'CGPA: 8.61', '92.6%', '68.20%', 'Pass')"
    }}
  ]
}}

Ensure each bullet is clean, meaningful, and associated with the correct role or project.
For education, keep the degree, school/university, dates, and scores properly separated.
Do not hallucinate or add fake roles or degrees.

CRITICAL INSTRUCTIONS FOR PROJECTS:
- When a project title line includes tools or tech stacks (e.g., 'Smart Water Pressure Management System — Flask, Python, ML, Epanet, Supabase' or 'Docsheild — MERN Stack, Blockchain, Web3.js, Smart Contracts, Encryption'), preserve the complete line with the tech stack in "title".
- "organization" must strictly be the project type or organization (e.g., 'Independent Project' or 'Academic Project'). NEVER append or merge the tech stack into "organization".
- "period" must capture the date range (e.g., 'Jan 2026 – Apr 2026').

CRITICAL INSTRUCTION FOR WORK EXPERIENCE VS PROJECTS:
- Any entry completed for or at a Company / Organization / Employer (e.g. 'Aparajitha Corporate Services', 'Mondelez International', 'Lakshmi Corporate Services') MUST be classified under "experience_records", NOT "project_records". Deduplicate identical entries.
- "project_records" must ONLY contain personal, academic, or independent projects.

--- RAW WORK EXPERIENCE SECTION ---
{exp_clean if exp_clean else "(None provided)"}

--- RAW PROJECTS SECTION ---
{proj_clean if proj_clean else "(None provided)"}

--- RAW EDUCATION SECTION ---
{edu_clean if edu_clean else "(None provided)"}
"""

    ai_response = await call_openrouter_gemini(
        prompt=prompt,
        system_prompt="You are an expert Enterprise ATS parser specialized in work experience, project history, and education. Return only valid JSON."
    )

    if ai_response:
        try:
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                parsed_json = json.loads(json_match.group())
                if isinstance(parsed_json, dict):
                    exp_results = parsed_json.get('experience_records')
                    proj_results = parsed_json.get('project_records')
                    edu_results = parsed_json.get('education_records')

                    refined_exp = exp_results if isinstance(exp_results, list) and len(exp_results) > 0 else fallback_exp
                    refined_proj = proj_results if isinstance(proj_results, list) and len(proj_results) > 0 else fallback_proj
                    refined_edu = edu_results if isinstance(edu_results, list) and len(edu_results) > 0 else fallback_edu

                    print(f"[AI Gemini] [TARGETED-PARSED] Refined {len(refined_exp)} experience entries, {len(refined_proj)} project entries, and {len(refined_edu)} education entries.")
                    return refined_exp, refined_proj, refined_edu
        except Exception as e:
            print(f"[AI Gemini] Error parsing targeted JSON: {e}")

    return fallback_exp, fallback_proj, fallback_edu