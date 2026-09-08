from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Body
from fastapi.responses import Response
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import PyPDF2
import docx
from io import BytesIO
from database import db
from ai_parser import parse_resume_complete, refine_experience_and_projects_ai
from document_parser import document_parser
from scoring import scoring_engine
import traceback
import os
import re

router = APIRouter(prefix="/api/candidates", tags=["Candidates"])

def ensure_candidate_edited_details_table():
    try:
        db.execute_query("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'CandidateEditedDetails')
            BEGIN
                CREATE TABLE CandidateEditedDetails (
                    EditID INT IDENTITY(1,1) PRIMARY KEY,
                    CandidateID INT NOT NULL UNIQUE,
                    FirstName NVARCHAR(150),
                    LastName NVARCHAR(150),
                    FullName NVARCHAR(250),
                    Email NVARCHAR(250),
                    Phone NVARCHAR(50),
                    Summary NVARCHAR(MAX),
                    CurrentCTC NVARCHAR(100),
                    NoticePeriod NVARCHAR(100),
                    PreferredLocation NVARCHAR(150),
                    TotalYearsExperience FLOAT,
                    EducationRecords NVARCHAR(MAX),
                    ExperienceRecords NVARCHAR(MAX),
                    ProjectRecords NVARCHAR(MAX),
                    Certifications NVARCHAR(MAX),
                    SkillsList NVARCHAR(MAX),
                    Achievements NVARCHAR(MAX),
                    Outliers NVARCHAR(MAX),
                    SavedAt DATETIME DEFAULT GETDATE()
                );
            END
        """)
    except Exception as e:
        print(f"[CandidateRoutes] Table init notice: {e}")

ensure_candidate_edited_details_table()

INVALID_NAMES = {
    'unknown', 'anonymous', 'applicant', 'candidate', 'resume', 'candidate applicant',
    'data scientist', 'software engineer', 'full stack developer', 'developer', 'engineer',
    'frontend developer', 'backend developer', 'data analyst', 'devops engineer', ''
}

def get_clean_candidate_name(filename: str, parsed_name: Optional[str] = None, resume_text: Optional[str] = None) -> str:
    if parsed_name and parsed_name.strip() and parsed_name.strip().lower() not in INVALID_NAMES:
        return parsed_name.strip()
    
    if resume_text:
        for line in resume_text.split('\n')[:8]:
            cl = re.sub(r'^[#\s\-*|:•·]+', '', line).strip()
            cl = re.sub(r'[*_`]', '', cl).strip()
            if not cl or len(cl) < 2 or len(cl) > 35:
                continue
            if '@' in cl or 'http' in cl or 'www' in cl or 'linkedin' in cl or 'github' in cl:
                continue
            if re.search(r'^(?:resume|curriculum|cv|phone|email|contact|address|professional|education|skills|experience)\b', cl, re.IGNORECASE):
                continue
            if re.search(r'^\+?\d', cl):
                continue
            if cl.lower() in INVALID_NAMES:
                continue
            if re.search(r'\b(Tamil Nadu|India|USA|United States|Madurai|Chennai|Bangalore|California|New York)\b', cl, re.IGNORECASE) and len(cl.split()) <= 3:
                continue
            words = cl.split()
            if 1 <= len(words) <= 4:
                return cl.title() if cl.isupper() else cl
                
    if filename:
        base = os.path.splitext(os.path.basename(filename))[0]
        base = re.sub(r'[_\-]+', ' ', base).strip()
        if not base.replace(' ', '').isdigit():
            return base
            
    return "Candidate Applicant"

@router.get("")
@router.get("/")
async def get_all_candidates():
    try:
        rows = db.execute_query(
            """
            SELECT c.CandidateID, 
                   c.ResumeFileName,
                   jr.RoleName, c.YearsExperience, c.TotalScore,
                   c.CreatedAt, sc.OverallScore, sc.Recommendation,
                   sc.SkillMatchScore, sc.ExperienceMatchScore,
                   sc.EducationMatchScore, sc.SemanticMatchScore,
                   c.ResumeText, c.Certifications
            FROM Candidates c
            JOIN JobRoles jr ON c.RoleID = jr.RoleID
            LEFT JOIN (
                SELECT CandidateID, OverallScore, Recommendation,
                       SkillMatchScore, ExperienceMatchScore,
                       EducationMatchScore, SemanticMatchScore,
                       ROW_NUMBER() OVER (PARTITION BY CandidateID ORDER BY ScoreID DESC) AS rn
                FROM ScoringResults
            ) sc ON c.CandidateID = sc.CandidateID AND sc.rn = 1
            ORDER BY ISNULL(c.TotalScore, 0) DESC, c.CreatedAt DESC
            """
        )
        
        candidates = []
        for row in rows:
            filename = row[1] or 'resume.pdf'
            resume_text = row[12] or ''
            cert_raw = row[13]
            meta_name = None
            if cert_raw:
                try:
                    meta = json.loads(cert_raw)
                    if isinstance(meta, dict) and meta.get('candidate_name'):
                        meta_name = meta['candidate_name']
                except Exception:
                    pass
                    
            name = meta_name or get_clean_candidate_name(filename, resume_text=resume_text)
            
            candidates.append({
                'candidate_id': row[0],
                'full_name': name,
                'role_name': row[2],
                'years_experience': float(row[3] or 0),
                'total_score': float(row[4] or 0),
                'uploaded_at': str(row[5]),
                'overall_score': float(row[6] or row[4] or 0),
                'recommendation': row[7] or 'Not Scored',
                'skill_match': float(row[8] or 0),
                'experience_match': float(row[9] or 0),
                'education_match': float(row[10] or 0),
                'semantic_match': float(row[11] or 0),
                'resume_file_name': filename
            })
        
        return {
            'total': len(candidates),
            'candidates': candidates
        }
    except Exception as e:
        print(f"[Candidates] Error fetching candidates: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_ats_stats():
    try:
        total_candidates_row = db.execute_query("SELECT COUNT(*) FROM Candidates", fetch_one=True)
        total_candidates = total_candidates_row[0] if total_candidates_row else 0
        
        total_roles_row = db.execute_query("SELECT COUNT(*) FROM JobRoles WHERE IsActive = 1", fetch_one=True)
        total_roles = total_roles_row[0] if total_roles_row else 0
        
        avg_score_row = db.execute_query("SELECT AVG(OverallScore) FROM ScoringResults", fetch_one=True)
        avg_score = avg_score_row[0] if avg_score_row and avg_score_row[0] is not None else 0
        
        return {
            'total_candidates': total_candidates,
            'total_roles': total_roles,
            'average_score': float(avg_score)
        }
    except Exception as e:
        return {'total_candidates': 0, 'total_roles': 0, 'average_score': 0.0}



def save_debug_output_files(filename: str, raw_markdown: str, plain_text: str, structured_content: dict, final_output: dict = None):
    """
    Automatically saves the 4-tier debug extraction output files
    into backend/debug_outputs/<resume_name>/ on every upload.
    """
    try:
        base_name = os.path.splitext(os.path.basename(filename))[0]
        clean_folder = re.sub(r'[^\w\-_.]', '_', base_name).strip('_') or "uploaded_resume"
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        debug_dir = os.path.join(backend_dir, "debug_outputs", clean_folder)
        os.makedirs(debug_dir, exist_ok=True)

        # 1. OpenDataLoader / Markdown Extraction
        with open(os.path.join(debug_dir, "1_opendataloader_raw_markdown.md"), "w", encoding="utf-8") as f:
            f.write(raw_markdown or "(OpenDataLoader markdown empty or not generated)")

        # 2. PyMuPDF Plain Text
        with open(os.path.join(debug_dir, "2_pymupdf_plain_text.txt"), "w", encoding="utf-8") as f:
            f.write(plain_text or "(Plain text empty)")

        # 3. Parsed Sections & Structured Content (from Document Parser)
        with open(os.path.join(debug_dir, "3_segmented_structured_data.json"), "w", encoding="utf-8") as f:
            json.dump(structured_content or {}, f, indent=2)

        # 4. What is sent to Gemini (Work Experience, Projects, and Education)
        exp_raw = structured_content.get("experience_raw_text", "")
        proj_raw = structured_content.get("projects_raw_text", "")
        edu_raw = structured_content.get("education_raw_text", "")
        gemini_input = f"=== WORK EXPERIENCE SENT TO GEMINI ===\n{exp_raw}\n\n=== PROJECTS SENT TO GEMINI ===\n{proj_raw}\n\n=== EDUCATION SENT TO GEMINI ===\n{edu_raw}\n"
        with open(os.path.join(debug_dir, "4_sent_to_gemini.txt"), "w", encoding="utf-8") as f:
            f.write(gemini_input)

        # 5. Final Merged Output (Returned to Preview Modal)
        if final_output:
            with open(os.path.join(debug_dir, "5_final_merged_preview.json"), "w", encoding="utf-8") as f:
                json.dump(final_output, f, indent=2)

        print(f"[DebugOutput] Auto-saved 4 debug extraction files for '{filename}' to: {debug_dir}")
    except Exception as e:
        print(f"[DebugOutput] Error saving debug files: {e}")

@router.post("/parse-preview")
async def parse_resume_preview(
    role_id: Optional[int] = Form(None),
    file: UploadFile = File(...)
):
    """
    Step 1: Parse and extract text and layout without using LLM/AI.
    Returns structured resume data for user preview & text editor dialog.
    """
    try:
        content = await file.read()
        if len(content) > 10485760:
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB")
            
        text = ""
        filename_lower = file.filename.lower()
        if filename_lower.endswith('.pdf'):
            try:
                text = document_parser.extract_pdf_text(content)
                if not text.strip():
                    reader = PyPDF2.PdfReader(BytesIO(content))
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"PDF extraction error: {str(e)}")
        elif filename_lower.endswith('.docx'):
            try:
                doc = docx.Document(BytesIO(content))
                for para in doc.paragraphs:
                    if para.text:
                        text += para.text + "\n"
                for table in doc.tables:
                    for r in table.rows:
                        for cell in r.cells:
                            if cell.text:
                                text += cell.text + " "
                        text += "\n"
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"DOCX extraction error: {str(e)}")
        elif filename_lower.endswith('.txt'):
            try:
                text = content.decode('utf-8')
            except Exception:
                text = content.decode('latin-1', errors='ignore')
        else:
            raise HTTPException(status_code=400, detail="Unsupported format. Upload PDF, DOCX, or TXT.")

        if not text.strip():
            raise HTTPException(status_code=400, detail="Resume file is empty.")

        # 1. Structural extraction via OpenDataLoader & layout parsing
        structured_doc = document_parser.parse_resume(text, file.filename, raw_bytes=content)
        parsed_content = structured_doc.get('structured_content', {})
        parsed_markdown = structured_doc.get('raw_markdown', '')

        # Base fields preserved directly from extraction
        candidate_name = parsed_content.get('candidate_name') or get_clean_candidate_name(file.filename, resume_text=text)
        email_str = parsed_content.get('email', '')
        phone_str = parsed_content.get('phone', '')
        summary_str = parsed_content.get('summary', '')
        skills_list = parsed_content.get('skills_list', [])
        certifications = parsed_content.get('certifications', [])
        achievements = parsed_content.get('achievements', [])
        outliers = parsed_content.get('outliers', [])

        exp_raw = parsed_content.get('experience_raw_text', '')
        proj_raw = parsed_content.get('projects_raw_text', '')
        edu_raw = parsed_content.get('education_raw_text', '')
        fallback_exp = parsed_content.get('experience_records', [])
        fallback_proj = parsed_content.get('project_records', [])
        fallback_edu = parsed_content.get('education_records', [])

        # 2. Targeted refinement with Gemini 2.5 Flash (Work Experience, Projects, and Education)
        refined_exp, refined_proj, refined_edu = await refine_experience_and_projects_ai(
            exp_text=exp_raw,
            proj_text=proj_raw,
            edu_text=edu_raw,
            fallback_exp=fallback_exp,
            fallback_proj=fallback_proj,
            fallback_edu=fallback_edu
        )

        response_payload = {
            'candidate_name': candidate_name,
            'email': email_str,
            'phone': phone_str,
            'summary': summary_str,
            'experience_records': refined_exp,
            'project_records': refined_proj,
            'education_records': refined_edu,
            'skills_list': skills_list,
            'certifications': certifications,
            'achievements': achievements,
            'outliers': outliers,
            'raw_text': text,
            'filename': file.filename,
            'role_id': role_id
        }

        # 3. Automatically save 4 debug extraction output files to backend/debug_outputs/<resume_name>/
        save_debug_output_files(
            filename=file.filename,
            raw_markdown=parsed_markdown,
            plain_text=text,
            structured_content=parsed_content,
            final_output=response_payload
        )

        return response_payload
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ParsePreview] Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")

@router.post("/submit-and-score")
async def submit_and_score_resume(payload: Dict[str, Any] = Body(...)):
    """
    Step 2: Submit verified & edited resume preview details for LLM parsing and ATS scoring.
    """
    try:
        role_id = int(payload.get('role_id') or 1)
        candidate_name = payload.get('candidate_name', 'Candidate Applicant').strip()
        email_str = payload.get('email', '').strip()
        phone_str = payload.get('phone', '').strip()
        summary_str = payload.get('summary', '').strip()
        exp_records = payload.get('experience_records', [])
        proj_records = payload.get('project_records', [])
        edu_records = payload.get('education_records', [])
        skills_list = payload.get('skills_list', []) or payload.get('skills', [])
        certifications = payload.get('certifications', [])
        achievements = payload.get('achievements', [])
        outliers = payload.get('outliers', [])
        raw_text = payload.get('raw_text', '')
        filename = payload.get('filename', 'resume.pdf')

        # Get role details
        role = db.execute_query(
            "SELECT RoleID, RoleName, MinExperience, EducationRequirements FROM JobRoles WHERE RoleID = ? AND IsActive = 1",
            (role_id,),
            fetch_one=True
        )
        if not role:
            raise HTTPException(status_code=404, detail="Job Role not found")

        role_name = role[1]
        min_exp = float(role[2] or 0)
        edu_req = role[3] or ''

        jd = db.execute_query(
            "SELECT Description, Responsibilities FROM JobDescriptions WHERE RoleID = ?",
            (role_id,),
            fetch_one=True
        )
        jd_text = f"{jd[0] if jd else ''} {jd[1] if jd else ''}".strip() or role_name

        # Calculate experience tenure from experience records
        from ai_parser import calculate_years_experience
        years_exp = 0.0
        if exp_records:
            for exp in exp_records:
                p_text = f"{exp.get('period', '')} {exp.get('title', '')}"
                years_exp += calculate_years_experience(p_text)
        else:
            years_exp = calculate_years_experience(raw_text)
            
        years_exp = round(years_exp, 1)

        education_str = ""
        if isinstance(edu_records, list):
            education_str = ", ".join([f"{e.get('degree', '')} ({e.get('institution', '')})" for e in edu_records if isinstance(e, dict)])
        else:
            education_str = str(edu_records)

        # Store complete structured metadata in Certifications column
        metadata = {
            'candidate_name': candidate_name,
            'email': email_str,
            'phone': phone_str,
            'summary': summary_str,
            'experience_records': exp_records,
            'project_records': proj_records,
            'education_records': edu_records,
            'skills_list': skills_list,
            'certifications': certifications,
            'achievements': achievements,
            'outliers': outliers
        }

        # Insert candidate record into SQL database
        db.execute_query(
            """
            INSERT INTO Candidates (RoleID, ResumeText, ResumeFileName, ResumeFileData,
                                    ParsedSkills, YearsExperience, Education, Certifications, TotalScore)
            VALUES (?, ?, ?, NULL, ?, ?, ?, ?, 0)
            """,
            (role_id, raw_text, filename,
             json.dumps(skills_list), years_exp, json.dumps(edu_records), json.dumps(metadata))
        )
        candidate_id = db.get_last_insert_id()
        if not candidate_id:
            last_row = db.execute_query("SELECT TOP 1 CandidateID FROM Candidates ORDER BY CandidateID DESC", fetch_one=True)
            candidate_id = last_row[0] if last_row else 1
        candidate_id = int(candidate_id)

        # Required & Preferred Skills
        req_rows = db.execute_query(
            "SELECT s.SkillName FROM RoleSkills rs JOIN Skills s ON rs.SkillID = s.SkillID WHERE rs.RoleID = ? AND rs.IsRequired = 1",
            (role_id,)
        )
        required_skills = [r[0] for r in req_rows]
        
        pref_rows = db.execute_query(
            "SELECT s.SkillName FROM RoleSkills rs JOIN Skills s ON rs.SkillID = s.SkillID WHERE rs.RoleID = ? AND rs.IsRequired = 0",
            (role_id,)
        )
        preferred_skills = [r[0] for r in pref_rows]

        candidate_data = {
            'candidate_id': candidate_id,
            'candidate_name': candidate_name,
            'parsed_skills': skills_list,
            'years_experience': years_exp,
            'education': education_str,
            'certifications': [],
            'resume_text': raw_text
        }
        role_data = {
            'role_id': role_id,
            'role_name': role_name,
            'required_skills': required_skills,
            'preferred_skills': preferred_skills,
            'min_experience': min_exp,
            'education_requirements': edu_req
        }

        score_result = scoring_engine.score_candidate(candidate_data, role_data, jd_text)
        overall_score = score_result.get('overall_score', 0)
        recommendation = score_result.get('recommendation', 'Not Scored')

        db.execute_query(
            """
            INSERT INTO ScoringResults (
                CandidateID, RoleID, SkillMatchScore, ExperienceMatchScore,
                EducationMatchScore, SemanticMatchScore,
                OverallScore, Strengths, Gaps, Recommendation
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id, role_id,
                score_result.get('skill_match', 0),
                score_result.get('experience_match', 0),
                score_result.get('education_match', 0),
                score_result.get('semantic_match', 0),
                overall_score,
                json.dumps(score_result.get('actionable_recs', [])),
                json.dumps(score_result.get('missing_skills', [])),
                recommendation
            )
        )
        db.execute_query("UPDATE Candidates SET TotalScore = ?, YearsExperience = ? WHERE CandidateID = ?", (overall_score, years_exp, candidate_id))

        return {
            'message': 'Resume scored successfully',
            'candidate_id': candidate_id,
            'candidate_name': candidate_name,
            'role_name': role_name,
            'role_id': role_id,
            'overall_score': overall_score,
            'total_score': overall_score,
            'recommendation': recommendation,
            'skill_match': score_result.get('skill_match', 0),
            'experience_match': score_result.get('experience_match', 0),
            'education_match': score_result.get('education_match', 0),
            'semantic_match': score_result.get('semantic_match', 0),
            'matched_skills': score_result.get('matched_skills', []),
            'missing_skills': score_result.get('missing_skills', []),
            'actionable_recs': score_result.get('actionable_recs', []),
            'summary_desc': score_result.get('summary_desc', ''),
            'weights': score_result.get('weights', {}),
            'formula_str': score_result.get('formula_str', ''),
            'telemetry': score_result.get('telemetry', {}),
            'uploaded_at': datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SubmitScore] Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Scoring failed: {str(e)}")

@router.get("/{candidate_id}")
async def get_candidate_detail(candidate_id: int):
    try:
        row = db.execute_query(
            """
            SELECT c.CandidateID,
                   jr.RoleID, jr.RoleName, jr.Description AS RoleDescription,
                   jr.MinExperience, jr.EducationRequirements,
                   c.ResumeText, c.ResumeFileName, c.YearsExperience,
                   c.Education, c.ParsedSkills, c.Certifications,
                   c.TotalScore, c.CreatedAt
            FROM Candidates c
            JOIN JobRoles jr ON c.RoleID = jr.RoleID
            WHERE c.CandidateID = ?
            """,
            (candidate_id,),
            fetch_one=True
        )
        
        if not row:
            raise HTTPException(status_code=404, detail="Candidate not found")
        
        role_id = row[1]
        role_name = row[2]
        min_exp = float(row[4] or 0)
        edu_req = row[5] or ''
        resume_text = row[6] or ''
        filename = row[7] or 'resume.pdf'
        years_exp = float(row[8] or 0)
        education_raw = row[9] or ''
        parsed_skills = json.loads(row[10]) if row[10] else []
        meta_raw = row[11]
        
        # Check if saved in dedicated CandidateEditedDetails table
        edited_row = db.execute_query(
            """
            SELECT FirstName, LastName, FullName, Email, Phone, Summary,
                   CurrentCTC, NoticePeriod, PreferredLocation, TotalYearsExperience,
                   EducationRecords, ExperienceRecords, ProjectRecords, Certifications,
                   SkillsList, Achievements, Outliers
            FROM CandidateEditedDetails
            WHERE CandidateID = ?
            """,
            (candidate_id,),
            fetch_one=True
        )

        metadata = {}
        if edited_row:
            first_name = edited_row[0] or ''
            last_name = edited_row[1] or ''
            candidate_name = edited_row[2] or f"{first_name} {last_name}".strip() or get_clean_candidate_name(filename, resume_text=resume_text)
            extracted_email = edited_row[3] or ''
            extracted_phone = edited_row[4] or ''
            summary_text = edited_row[5] or ''
            current_ctc = edited_row[6] or ''
            notice_period = edited_row[7] or ''
            preferred_location = edited_row[8] or ''
            years_exp = float(edited_row[9] or years_exp or 0)
            total_years_exp_input = years_exp
            
            try: edu_records = json.loads(edited_row[10]) if edited_row[10] else []
            except Exception: edu_records = []
            try: exp_records = json.loads(edited_row[11]) if edited_row[11] else []
            except Exception: exp_records = []
            try: proj_records = json.loads(edited_row[12]) if edited_row[12] else []
            except Exception: proj_records = []
            try: certifications = json.loads(edited_row[13]) if edited_row[13] else []
            except Exception: certifications = []
            try: parsed_skills = json.loads(edited_row[14]) if edited_row[14] else parsed_skills
            except Exception: pass
            try: achievements = json.loads(edited_row[15]) if edited_row[15] else []
            except Exception: achievements = []
            try: outliers = json.loads(edited_row[16]) if edited_row[16] else []
            except Exception: outliers = []
            
            metadata = {
                'candidate_name': candidate_name, 'first_name': first_name, 'last_name': last_name,
                'email': extracted_email, 'gmail': extracted_email, 'phone': extracted_phone,
                'mobile_number': extracted_phone, 'summary': summary_text,
                'current_ctc': current_ctc, 'notice_period': notice_period,
                'preferred_location': preferred_location, 'total_years_experience': years_exp,
                'education_records': edu_records, 'experience_records': exp_records,
                'project_records': proj_records, 'certifications': certifications,
                'skills_list': parsed_skills, 'achievements': achievements, 'outliers': outliers
            }
        else:
            if meta_raw:
                try:
                    loaded = json.loads(meta_raw)
                    if isinstance(loaded, dict):
                        metadata = loaded
                except Exception:
                    metadata = {}

            candidate_name = metadata.get('candidate_name') or get_clean_candidate_name(filename, resume_text=resume_text)
            extracted_email = metadata.get('email') or metadata.get('gmail') or ''
            extracted_phone = metadata.get('phone') or metadata.get('mobile_number') or ''
            first_name = metadata.get('first_name') or (candidate_name.split()[0] if candidate_name else '')
            last_name = metadata.get('last_name') or (" ".join(candidate_name.split()[1:]) if len(candidate_name.split()) > 1 else '')
            current_ctc = metadata.get('current_ctc', '')
            notice_period = metadata.get('notice_period', '')
            preferred_location = metadata.get('preferred_location', '')
            total_years_exp_input = metadata.get('total_years_experience', '')

            summary_text = metadata.get('summary') or ''
            exp_records = metadata.get('experience_records') or []
            proj_records = metadata.get('project_records') or []
            certifications = metadata.get('certifications') or []
            achievements = metadata.get('achievements') or []
            outliers = metadata.get('outliers') or []
            
            # Education records
            edu_records = []
            if metadata.get('education_records'):
                edu_records = metadata['education_records']
            elif education_raw:
                try:
                    loaded_edu = json.loads(education_raw)
                    if isinstance(loaded_edu, list):
                        edu_records = loaded_edu
                    else:
                        edu_records = [{'degree': str(loaded_edu), 'course': str(loaded_edu), 'institution': '', 'institute': '', 'period': '', 'score': ''}]
                except Exception:
                    edu_records = [{'degree': education_raw, 'course': education_raw, 'institution': '', 'institute': '', 'period': '', 'score': ''}]

            # If metadata was not stored, fallback to dynamic extraction
            if not summary_text or not exp_records or not edu_records:
                structured_doc = document_parser.parse_resume(resume_text, filename)
                sc = structured_doc.get('structured_content', {})
                if not candidate_name or candidate_name == 'Candidate Applicant':
                    candidate_name = sc.get('candidate_name') or candidate_name
                    if not first_name:
                        first_name = candidate_name.split()[0] if candidate_name else ''
                    if not last_name:
                        last_name = " ".join(candidate_name.split()[1:]) if len(candidate_name.split()) > 1 else ''
                if not extracted_email:
                    extracted_email = sc.get('email', '')
                if not extracted_phone:
                    extracted_phone = sc.get('phone', '')
                if not summary_text:
                    summary_text = sc.get('summary', '')
                if not exp_records:
                    exp_records = sc.get('experience_records', [])
                if not proj_records:
                    proj_records = sc.get('project_records', [])
                if not edu_records:
                    edu_records = sc.get('education_records', [])
                if not parsed_skills and sc.get('skills_list'):
                    parsed_skills = sc['skills_list']
                if not certifications:
                    certifications = sc.get('certifications', [])
                if not achievements:
                    achievements = sc.get('achievements', [])
                if not outliers:
                    outliers = sc.get('outliers', [])

        # Normalize education records for standardized field consumption
        normalized_edu = []
        for e in edu_records:
            if isinstance(e, dict):
                c_name = e.get('course') or e.get('degree') or ''
                lvl = e.get('level_of_education')
                if not lvl:
                    cl = c_name.lower()
                    if any(w in cl for w in ['b.', 'btech', 'b.e', 'bachelor', 'bsc', 'bca']):
                        lvl = 'Undergraduate'
                    elif any(w in cl for w in ['m.', 'mtech', 'm.e', 'master', 'msc', 'mca', 'mba']):
                        lvl = 'Postgraduate'
                    elif any(w in cl for w in ['phd', 'doctorate']):
                        lvl = 'Doctorate'
                    elif any(w in cl for w in ['diploma']):
                        lvl = 'Diploma'
                    elif any(w in cl for w in ['12th', 'hsc', 'cbse', 'higher secondary', 'secondary', '10th', 'sslc']):
                        lvl = 'Schooling'
                    else:
                        lvl = 'Undergraduate'

                p_str = e.get('period', '')
                f_yr = e.get('from_year') or (p_str.split('–')[0].split('-')[0].strip() if p_str else '')
                t_yr = e.get('to_year') or (p_str.split('–')[1].strip() if '–' in p_str else (p_str.split('-')[1].strip() if '-' in p_str else ''))
                inst_val = e.get('institute') or e.get('institution') or ''
                p_val = p_str or (f"{f_yr} - {t_yr}".strip(" -") if (f_yr or t_yr) else "")

                normalized_edu.append({
                    'level_of_education': lvl or 'Undergraduate',
                    'course': c_name,
                    'degree': c_name,
                    'study_mode': e.get('study_mode') or 'Full Time',
                    'specialization': e.get('specialization') or '',
                    'institute': inst_val,
                    'institution': inst_val,
                    'from_year': str(f_yr),
                    'to_year': str(t_yr),
                    'period': p_val,
                    'duration': e.get('duration') or '',
                    'score_type': e.get('score_type') or ('CGPA' if 'cgpa' in str(e.get('score', '')).lower() else ('Percentage' if '%' in str(e.get('score', '')) else 'CGPA')),
                    'score': str(e.get('score', '')),
                    'currently_pursuing': bool(e.get('currently_pursuing', False) or ('present' in p_str.lower() or 'pursuing' in p_str.lower()))
                })
        if normalized_edu:
            edu_records = normalized_edu

        # Normalize experience records for standardized field consumption
        normalized_exp = []
        for x in exp_records:
            if isinstance(x, dict):
                p_str = x.get('period', '')
                j_dt = x.get('joining_date') or (p_str.split('–')[0].split('-')[0].strip() if p_str else '')
                r_dt = x.get('relieved_date') or (p_str.split('–')[1].strip() if '–' in p_str else (p_str.split('-')[1].strip() if '-' in p_str else ''))
                is_curr = bool(x.get('currently_working', False) or ('present' in p_str.lower() or 'current' in p_str.lower()))
                desig_val = x.get('designation') or x.get('title') or ''
                p_val = p_str or (f"{j_dt} - {'Present' if is_curr else r_dt}".strip(" -") if (j_dt or r_dt) else "")

                normalized_exp.append({
                    'company': x.get('company') or '',
                    'industry_type': x.get('industry_type') or '',
                    'location': x.get('location') or '',
                    'employment_type': x.get('employment_type') or 'Full Time',
                    'designation': desig_val,
                    'title': desig_val,
                    'joining_date': str(j_dt),
                    'relieved_date': '' if is_curr else str(r_dt),
                    'period': p_val,
                    'work_duration': x.get('work_duration') or '',
                    'ctc_pa': x.get('ctc_pa') or '',
                    'reason_for_leaving': x.get('reason_for_leaving') or '',
                    'currently_working': is_curr,
                    'bullets': x.get('bullets', [])
                })
        if normalized_exp:
            exp_records = normalized_exp

        # Normalize certification records for standardized field consumption
        normalized_cert = []
        for c in certifications:
            if isinstance(c, dict):
                cert_title = c.get('course') or c.get('title') or c.get('name') or ''
                cert_inst = c.get('institute') or c.get('issuer') or c.get('organization') or ''
                normalized_cert.append({
                    'course': cert_title,
                    'title': cert_title,
                    'specialization': c.get('specialization') or '',
                    'study_mode': c.get('study_mode') or 'Online',
                    'institute': cert_inst,
                    'issuer': cert_inst,
                    'currently_pursuing': bool(c.get('currently_pursuing', False)),
                    'from_year': str(c.get('from_year') or ''),
                    'to_year': str(c.get('to_year') or ''),
                    'duration': c.get('duration') or '',
                    'score_type': c.get('score_type') or 'Score / Grade',
                    'score': str(c.get('score') or '')
                })
            elif isinstance(c, str) and c.strip():
                normalized_cert.append({
                    'course': c.strip(),
                    'title': c.strip(),
                    'specialization': '',
                    'study_mode': 'Online',
                    'institute': '',
                    'issuer': '',
                    'currently_pursuing': False,
                    'from_year': '',
                    'to_year': '',
                    'duration': '',
                    'score_type': 'Grade',
                    'score': ''
                })
        if normalized_cert:
            certifications = normalized_cert

        # Get Job Description
        jd_row = db.execute_query(
            "SELECT Description, Responsibilities FROM JobDescriptions WHERE RoleID = ?",
            (role_id,),
            fetch_one=True
        )
        jd_desc = jd_row[0] if jd_row and jd_row[0] else ''
        jd_resp = jd_row[1] if jd_row and jd_row[1] else ''
        jd_text = f"{jd_desc} {jd_resp}".strip() or role_name
        
        # Required & Preferred Skills
        req_rows = db.execute_query(
            "SELECT s.SkillName FROM RoleSkills rs JOIN Skills s ON rs.SkillID = s.SkillID WHERE rs.RoleID = ? AND rs.IsRequired = 1",
            (role_id,)
        )
        required_skills = [r[0] for r in req_rows]
        
        pref_rows = db.execute_query(
            "SELECT s.SkillName FROM RoleSkills rs JOIN Skills s ON rs.SkillID = s.SkillID WHERE rs.RoleID = ? AND rs.IsRequired = 0",
            (role_id,)
        )
        preferred_skills = [r[0] for r in pref_rows]
        
        education_str = ""
        if isinstance(edu_records, list):
            education_str = ", ".join([f"{e.get('degree', '')} ({e.get('institution', '')})" for e in edu_records if isinstance(e, dict)])
        else:
            education_str = str(edu_records)

        # Fetch stored scoring result from database (DO NOT re-score on simple view!)
        score_row = db.execute_query(
            """
            SELECT TOP 1 SkillMatchScore, ExperienceMatchScore, EducationMatchScore,
                         SemanticMatchScore, OverallScore, Strengths, Gaps, Recommendation
            FROM ScoringResults
            WHERE CandidateID = ?
            ORDER BY ScoreID DESC
            """,
            (candidate_id,),
            fetch_one=True
        )
        
        from scoring import get_scoring_weights
        weights = get_scoring_weights()
        w_sk = float(weights.get('skills', 40.0))
        w_ex = float(weights.get('experience', 30.0))
        w_ed = float(weights.get('education', 15.0))
        w_se = float(weights.get('semantic', 15.0))
        w_tot = (w_sk + w_ex + w_ed + w_se) or 100.0

        if score_row:
            strengths_list = []
            if score_row[5]:
                try:
                    strengths_list = json.loads(score_row[5])
                except Exception:
                    strengths_list = [str(score_row[5])]
                    
            missing_skills = []
            if score_row[6]:
                try:
                    missing_skills = json.loads(score_row[6])
                except Exception:
                    missing_skills = [str(score_row[6])]

            miss_set = set([s.lower() for s in missing_skills])
            matched_skills = [s for s in required_skills if s.lower() not in miss_set]

            s_skill = float(score_row[0] or 0)
            s_exp = float(score_row[1] or 0)
            s_edu = float(score_row[2] or 0)
            s_sem = float(score_row[3] or 0)

            # Dynamically calculate overall score using active custom weights
            overall_score = round(
                s_skill * (w_sk / w_tot) +
                s_exp * (w_ex / w_tot) +
                s_edu * (w_ed / w_tot) +
                s_sem * (w_se / w_tot),
                1
            )

            w_sk_factor = w_sk / w_tot
            w_ex_factor = w_ex / w_tot
            w_ed_factor = w_ed / w_tot
            w_se_factor = w_se / w_tot
            formula_str = f"Formula: ({w_sk_factor:.2f} * {s_skill:.1f}) + ({w_ex_factor:.2f} * {s_exp:.1f}) + ({w_ed_factor:.2f} * {s_edu:.1f}) + ({w_se_factor:.2f} * {s_sem:.1f}) = {overall_score:.1f}%"

            from scoring import scoring_engine
            _, _, _, _, computed_matched_details = scoring_engine.calculate_keyword_semantic_skills_match(
                parsed_skills, required_skills, resume_text
            )
            _, matched_kws, missing_kws, total_kws, top_kws = scoring_engine.extract_keywords_comparison(resume_text, jd_text)

            score_details = {
                'skill_match': s_skill,
                'experience_match': s_exp,
                'education_match': s_edu,
                'semantic_match': s_sem,
                'overall_score': overall_score,
                'actionable_recs': strengths_list,
                'missing_skills': missing_skills,
                'matched_skills': matched_skills,
                'matched_skills_details': computed_matched_details if computed_matched_details else [{'display': s, 'skill': s} for s in matched_skills],
                'top_jd_keywords': top_kws,
                'matched_keywords': matched_kws,
                'missing_keywords': missing_kws,
                'recommendation': score_row[7] or 'Not Scored',
                'formula_str': formula_str,
                'weights': weights,
                'telemetry': {
                    'pillar1': {
                        'title': f"SKILLS MATCHING (Weight: {w_sk:.0f}%)",
                        'extracted_skills': parsed_skills,
                        'required_skills': [{'name': s, 'weight': 1} for s in required_skills],
                        'matched_details': computed_matched_details if computed_matched_details else [{'display': s, 'skill': s} for s in matched_skills],
                        'missing_skills': missing_skills,
                        'calc_str': f"Calculation: ({len(matched_skills)}.0 matched / {len(required_skills) or 1}.0 total) * 100 = {s_skill:.1f}%"
                    },
                    'pillar2': {
                        'title': f"EXPERIENCE MATCHING (Weight: {w_ex:.0f}%)",
                        'candidate_years': years_exp,
                        'required_years': min_exp,
                        'calc_str': f"Calculation: min(100, ({years_exp} candidate years / {min_exp or 1} required years) * 100) = {s_exp:.1f}%"
                    },
                    'pillar3': {
                        'title': f"EDUCATION MATCHING (Weight: {w_ed:.0f}%)",
                        'insight': "Evaluated against degree hierarchy ranking."
                    },
                    'pillar4': {
                        'title': f"SEMANTIC & DOMAIN KEYWORDS MATCHING (Weight: {w_se:.0f}%)",
                        'top_jd_keywords': top_kws,
                        'matched_keywords': matched_kws,
                        'missing_keywords': missing_kws,
                        'total_keywords': total_kws,
                        'calc_str': f"Calculation: ({len(matched_kws)} matched / {total_kws} target JD keywords) + BGE Semantic Embedding Cosine Alignment = {s_sem:.1f}%"
                    }
                }
            }
        else:
            score_details = {
                'skill_match': 0, 'experience_match': 0, 'education_match': 0, 'semantic_match': 0,
                'overall_score': float(row[13] or 0),
                'actionable_recs': [], 'missing_skills': [], 'matched_skills': [],
                'matched_skills_details': [], 'recommendation': 'Not Scored',
                'formula_str': 'Not Scored',
                'weights': weights,
                'telemetry': {}
            }
        
        return {
            'candidate': {
                'candidate_id': row[0],
                'full_name': candidate_name,
                'first_name': first_name,
                'last_name': last_name,
                'email': extracted_email,
                'gmail': extracted_email,
                'phone': extracted_phone,
                'mobile_number': extracted_phone,
                'current_ctc': current_ctc,
                'notice_period': notice_period,
                'preferred_location': preferred_location,
                'total_years_experience': total_years_exp_input or years_exp,
                'role_id': role_id,
                'role_name': role_name,
                'role_description': row[3] or jd_desc,
                'resume_text': resume_text,
                'resume_file_name': filename,
                'years_experience': years_exp,
                'education': education_str,
                'parsed_skills': parsed_skills,
                'skills_list': parsed_skills,
                'total_score': float(row[12] or score_details.get('overall_score', 0)),
                'uploaded_at': str(row[13]),
                'summary': summary_text,
                'experience_records': exp_records,
                'project_records': proj_records,
                'education_records': edu_records,
                'certifications': certifications,
                'achievements': achievements,
                'outliers': outliers
            },
            'role_requirements': {
                'role_id': role_id,
                'role_name': role_name,
                'min_experience': min_exp,
                'education_requirements': edu_req,
                'required_skills': required_skills,
                'preferred_skills': preferred_skills,
                'jd_description': jd_desc,
                'jd_responsibilities': jd_resp
            },
            'scoring': score_details
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Candidates] Fetch error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{candidate_id}")
async def delete_candidate(candidate_id: int):
    try:
        row = db.execute_query("SELECT CandidateID FROM Candidates WHERE CandidateID = ?", (candidate_id,), fetch_one=True)
        if not row:
            raise HTTPException(status_code=404, detail="Candidate not found")
        db.execute_query("DELETE FROM ScoringResults WHERE CandidateID = ?", (candidate_id,))
        db.execute_query("DELETE FROM Candidates WHERE CandidateID = ?", (candidate_id,))
        return {'message': 'Candidate deleted successfully', 'candidate_id': candidate_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{candidate_id}/resume-file")
async def get_candidate_resume_file(candidate_id: int):
    try:
        row = db.execute_query("SELECT ResumeFileName, ResumeFileData, ResumeText FROM Candidates WHERE CandidateID = ?", (candidate_id,), fetch_one=True)
        if not row:
            raise HTTPException(status_code=404, detail="Candidate not found")
        
        file_name = row[0] or "resume.pdf"
        file_data = row[1]
        
        if not file_data:
            resume_text = row[2] or ""
            return Response(content=resume_text.encode('utf-8'), media_type="text/plain", headers={"Content-Disposition": f'inline; filename="{file_name}.txt"'})
        
        lower_name = file_name.lower()
        if lower_name.endswith('.pdf'):
            media_type = "application/pdf"
        elif lower_name.endswith('.docx'):
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif lower_name.endswith('.txt'):
            media_type = "text/plain"
        else:
            media_type = "application/octet-stream"
            
        return Response(content=file_data, media_type=media_type, headers={"Content-Disposition": f'inline; filename="{file_name}"'})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{candidate_id}/recalculate-score")
async def recalculate_candidate_score(candidate_id: int):
    """
    Recalculates the candidate's ATS score using local NLP & SentenceTransformer embeddings
    without requiring any re-upload or LLM API usage.
    """
    try:
        cand_row = db.execute_query(
            """
            SELECT c.CandidateID, c.RoleID, c.ResumeFileName, c.ResumeText,
                   c.ParsedSkills, c.YearsExperience, c.Education, c.Certifications
            FROM Candidates c
            WHERE c.CandidateID = ?
            """,
            (candidate_id,),
            fetch_one=True
        )
        if not cand_row:
            raise HTTPException(status_code=404, detail="Candidate not found")

        role_id = cand_row[1]
        filename = cand_row[2] or "resume.pdf"
        resume_text = cand_row[3] or ""
        parsed_skills_raw = cand_row[4]
        cert_raw = cand_row[7]

        parsed_skills = []
        if parsed_skills_raw:
            try:
                parsed_skills = json.loads(parsed_skills_raw)
            except Exception:
                parsed_skills = [s.strip() for s in parsed_skills_raw.split(',') if s.strip()]

        candidate_name = get_clean_candidate_name(filename, resume_text=resume_text)
        exp_records = []
        edu_records = []
        if cert_raw:
            try:
                meta = json.loads(cert_raw)
                if isinstance(meta, dict):
                    candidate_name = meta.get('candidate_name') or candidate_name
                    exp_records = meta.get('experience_records', [])
                    edu_records = meta.get('education_records', [])
                    if not parsed_skills:
                        parsed_skills = meta.get('skills_list', [])
            except Exception:
                pass

        if not exp_records or not edu_records or not parsed_skills:
            structured_doc = document_parser.parse_resume(resume_text, filename)
            sc = structured_doc.get('structured_content', {})
            if not exp_records:
                exp_records = sc.get('experience_records', [])
            if not edu_records:
                edu_records = sc.get('education_records', [])
            if not parsed_skills:
                parsed_skills = sc.get('skills_list', [])
            if not candidate_name or candidate_name == "Candidate Applicant":
                candidate_name = sc.get('candidate_name') or candidate_name

        from ai_parser import calculate_years_experience
        years_exp = 0.0
        if exp_records:
            for exp in exp_records:
                p_text = f"{exp.get('period', '')} {exp.get('title', '')}"
                years_exp += calculate_years_experience(p_text)
        else:
            years_exp = calculate_years_experience(resume_text)
        years_exp = round(years_exp, 1)

        role = db.execute_query(
            "SELECT RoleID, RoleName, MinExperience, EducationRequirements FROM JobRoles WHERE RoleID = ?",
            (role_id,),
            fetch_one=True
        )
        if not role:
            raise HTTPException(status_code=404, detail="Assigned Job Role not found")

        role_name = role[1]
        min_exp = float(role[2] or 0)
        edu_req = role[3] or ''

        jd = db.execute_query(
            "SELECT Description, Responsibilities FROM JobDescriptions WHERE RoleID = ?",
            (role_id,),
            fetch_one=True
        )
        jd_text = f"{jd[0] if jd else ''} {jd[1] if jd else ''}".strip() or role_name

        req_rows = db.execute_query(
            "SELECT s.SkillName FROM RoleSkills rs JOIN Skills s ON rs.SkillID = s.SkillID WHERE rs.RoleID = ? AND rs.IsRequired = 1",
            (role_id,)
        )
        required_skills = [r[0] for r in req_rows]
        
        pref_rows = db.execute_query(
            "SELECT s.SkillName FROM RoleSkills rs JOIN Skills s ON rs.SkillID = s.SkillID WHERE rs.RoleID = ? AND rs.IsRequired = 0",
            (role_id,)
        )
        preferred_skills = [r[0] for r in pref_rows]

        education_str = ""
        if isinstance(edu_records, list):
            education_str = ", ".join([f"{e.get('degree', '')} ({e.get('institution', '')})" for e in edu_records if isinstance(e, dict)])
        else:
            education_str = str(edu_records)

        candidate_data = {
            'candidate_id': candidate_id,
            'candidate_name': candidate_name,
            'parsed_skills': parsed_skills,
            'years_experience': years_exp,
            'education': education_str,
            'certifications': [],
            'resume_text': resume_text
        }
        role_data = {
            'role_id': role_id,
            'role_name': role_name,
            'required_skills': required_skills,
            'preferred_skills': preferred_skills,
            'min_experience': min_exp,
            'education_requirements': edu_req
        }

        score_result = scoring_engine.score_candidate(candidate_data, role_data, jd_text)
        overall_score = score_result.get('overall_score', 0)
        recommendation = score_result.get('recommendation', 'Not Scored')

        db.execute_query(
            """
            UPDATE ScoringResults
            SET SkillMatchScore = ?,
                ExperienceMatchScore = ?,
                EducationMatchScore = ?,
                SemanticMatchScore = ?,
                OverallScore = ?,
                Strengths = ?,
                Gaps = ?,
                Recommendation = ?
            WHERE CandidateID = ?
            """,
            (
                score_result.get('skill_match', 0),
                score_result.get('experience_match', 0),
                score_result.get('education_match', 0),
                score_result.get('semantic_match', 0),
                overall_score,
                json.dumps(score_result.get('actionable_recs', [])),
                json.dumps(score_result.get('missing_skills', [])),
                recommendation,
                candidate_id
            )
        )
        db.execute_query(
            "UPDATE Candidates SET TotalScore = ?, YearsExperience = ? WHERE CandidateID = ?",
            (overall_score, years_exp, candidate_id)
        )

        return {
            'message': 'Score recalculated successfully (Zero LLM used)',
            'candidate_id': candidate_id,
            'candidate_name': candidate_name,
            'role_name': role_name,
            'years_experience': years_exp,
            'overall_score': overall_score,
            'total_score': overall_score,
            'recommendation': recommendation,
            'skill_match': score_result.get('skill_match', 0),
            'experience_match': score_result.get('experience_match', 0),
            'education_match': score_result.get('education_match', 0),
            'semantic_match': score_result.get('semantic_match', 0),
            'matched_skills': score_result.get('matched_skills', []),
            'matched_skills_details': score_result.get('matched_skills_details', []),
            'missing_skills': score_result.get('missing_skills', []),
            'top_jd_keywords': score_result.get('top_jd_keywords', []),
            'matched_keywords': score_result.get('matched_keywords', []),
            'missing_keywords': score_result.get('missing_keywords', []),
            'actionable_recs': score_result.get('actionable_recs', []),
            'summary_desc': score_result.get('summary_desc', ''),
            'weights': score_result.get('weights', {}),
            'formula_str': score_result.get('formula_str', ''),
            'telemetry': score_result.get('telemetry', {})
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RecalculateScore] Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Recalculation failed: {str(e)}")

@router.put("/{candidate_id}")
async def update_candidate_details(candidate_id: int, payload: Dict[str, Any] = Body(...)):
    """
    Updates a candidate's personal and structured professional details,
    persists the updated profile to the database, and re-scores the candidate.
    """
    try:
        cand_row = db.execute_query(
            "SELECT CandidateID, RoleID, ResumeFileName, ResumeText FROM Candidates WHERE CandidateID = ?",
            (candidate_id,),
            fetch_one=True
        )
        if not cand_row:
            raise HTTPException(status_code=404, detail="Candidate not found")

        role_id = cand_row[1]
        filename = cand_row[2] or "resume.pdf"
        resume_text = cand_row[3] or ""

        first_name = payload.get('first_name', '') or ''
        last_name = payload.get('last_name', '') or ''
        candidate_name = f"{first_name} {last_name}".strip() if (first_name or last_name) else (payload.get('candidate_name') or payload.get('full_name') or get_clean_candidate_name(filename, resume_text=resume_text))
        email_str = payload.get('gmail') or payload.get('email', '') or ''
        phone_str = payload.get('mobile_number') or payload.get('phone', '') or ''
        summary_str = payload.get('summary', '') or ''
        current_ctc = payload.get('current_ctc', '') or ''
        notice_period = payload.get('notice_period', '') or ''
        preferred_location = payload.get('preferred_location', '') or ''
        total_years_exp_input = payload.get('total_years_experience')

        exp_records = payload.get('experience_records', []) or []
        proj_records = payload.get('project_records', []) or []
        edu_records = payload.get('education_records', []) or []
        raw_skills = payload.get('skills') if 'skills' in payload else (payload.get('skills_list') or payload.get('parsed_skills') or [])
        if isinstance(raw_skills, str):
            skills_list = [s.strip() for s in raw_skills.split(',') if s.strip()]
        elif isinstance(raw_skills, list):
            skills_list = [s.strip() for s in raw_skills if isinstance(s, str) and s.strip()]
        else:
            skills_list = []

        certifications = payload.get('certifications', []) or []
        achievements = payload.get('achievements', []) or []
        outliers = payload.get('outliers', []) or []

        # Calculate years experience
        from ai_parser import calculate_years_experience
        years_exp = 0.0
        if total_years_exp_input is not None and str(total_years_exp_input).strip():
            try:
                years_exp = float(str(total_years_exp_input).replace('yrs', '').replace('years', '').replace('+', '').strip())
            except Exception:
                years_exp = 0.0

        if years_exp <= 0 and exp_records:
            for exp in exp_records:
                p_text = f"{exp.get('joining_date', '')} {exp.get('relieved_date', '')} {exp.get('period', '')} {exp.get('designation', '')} {exp.get('title', '')}"
                years_exp += calculate_years_experience(p_text)
        elif years_exp <= 0:
            years_exp = calculate_years_experience(resume_text)
        years_exp = round(years_exp, 1)

        education_str = ""
        if isinstance(edu_records, list):
            education_str = ", ".join([f"{e.get('course') or e.get('degree', '')} ({e.get('institute') or e.get('institution', '')})" for e in edu_records if isinstance(e, dict)])
        else:
            education_str = str(edu_records)

        # Store complete structured metadata in Certifications column
        metadata = {
            'candidate_name': candidate_name,
            'first_name': first_name,
            'last_name': last_name,
            'email': email_str,
            'gmail': email_str,
            'phone': phone_str,
            'mobile_number': phone_str,
            'summary': summary_str,
            'current_ctc': current_ctc,
            'notice_period': notice_period,
            'preferred_location': preferred_location,
            'total_years_experience': years_exp,
            'experience_records': exp_records,
            'project_records': proj_records,
            'education_records': edu_records,
            'skills_list': skills_list,
            'certifications': certifications,
            'achievements': achievements,
            'outliers': outliers
        }

        # Role details
        role = db.execute_query(
            "SELECT RoleID, RoleName, MinExperience, EducationRequirements FROM JobRoles WHERE RoleID = ?",
            (role_id,),
            fetch_one=True
        )
        if not role:
            raise HTTPException(status_code=404, detail="Assigned Job Role not found")

        role_name = role[1]
        min_exp = float(role[2] or 0)
        edu_req = role[3] or ''

        jd = db.execute_query(
            "SELECT Description, Responsibilities FROM JobDescriptions WHERE RoleID = ?",
            (role_id,),
            fetch_one=True
        )
        jd_text = f"{jd[0] if jd else ''} {jd[1] if jd else ''}".strip() or role_name

        req_rows = db.execute_query(
            "SELECT s.SkillName FROM RoleSkills rs JOIN Skills s ON rs.SkillID = s.SkillID WHERE rs.RoleID = ? AND rs.IsRequired = 1",
            (role_id,)
        )
        required_skills = [r[0] for r in req_rows]
        
        pref_rows = db.execute_query(
            "SELECT s.SkillName FROM RoleSkills rs JOIN Skills s ON rs.SkillID = s.SkillID WHERE rs.RoleID = ? AND rs.IsRequired = 0",
            (role_id,)
        )
        preferred_skills = [r[0] for r in pref_rows]

        candidate_data = {
            'candidate_id': candidate_id,
            'candidate_name': candidate_name,
            'parsed_skills': skills_list,
            'years_experience': years_exp,
            'education': education_str,
            'certifications': [],
            'resume_text': resume_text
        }
        role_data = {
            'role_id': role_id,
            'role_name': role_name,
            'required_skills': required_skills,
            'preferred_skills': preferred_skills,
            'min_experience': min_exp,
            'education_requirements': edu_req
        }

        score_result = scoring_engine.score_candidate(candidate_data, role_data, jd_text)
        overall_score = score_result.get('overall_score', 0)
        recommendation = score_result.get('recommendation', 'Not Scored')

        # 1. Store directly in dedicated CandidateEditedDetails table in MSSQL DB
        db.execute_query(
            """
            IF EXISTS (SELECT 1 FROM CandidateEditedDetails WHERE CandidateID = ?)
            BEGIN
                UPDATE CandidateEditedDetails
                SET FirstName = ?, LastName = ?, FullName = ?, Email = ?, Phone = ?,
                    Summary = ?, CurrentCTC = ?, NoticePeriod = ?, PreferredLocation = ?,
                    TotalYearsExperience = ?, EducationRecords = ?, ExperienceRecords = ?,
                    ProjectRecords = ?, Certifications = ?, SkillsList = ?,
                    Achievements = ?, Outliers = ?, SavedAt = GETDATE()
                WHERE CandidateID = ?
            END
            ELSE
            BEGIN
                INSERT INTO CandidateEditedDetails (
                    CandidateID, FirstName, LastName, FullName, Email, Phone,
                    Summary, CurrentCTC, NoticePeriod, PreferredLocation,
                    TotalYearsExperience, EducationRecords, ExperienceRecords,
                    ProjectRecords, Certifications, SkillsList, Achievements, Outliers, SavedAt
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            END
            """,
            (
                candidate_id,
                first_name, last_name, candidate_name, email_str, phone_str,
                summary_str, current_ctc, notice_period, preferred_location,
                years_exp, json.dumps(edu_records), json.dumps(exp_records),
                json.dumps(proj_records), json.dumps(certifications), json.dumps(skills_list),
                json.dumps(achievements), json.dumps(outliers), candidate_id,
                # For INSERT branch:
                candidate_id, first_name, last_name, candidate_name, email_str, phone_str,
                summary_str, current_ctc, notice_period, preferred_location,
                years_exp, json.dumps(edu_records), json.dumps(exp_records),
                json.dumps(proj_records), json.dumps(certifications), json.dumps(skills_list),
                json.dumps(achievements), json.dumps(outliers)
            )
        )

        # 2. Update Database Candidates & ScoringResults
        db.execute_query(
            """
            UPDATE Candidates
            SET ParsedSkills = ?,
                YearsExperience = ?,
                Education = ?,
                Certifications = ?,
                TotalScore = ?
            WHERE CandidateID = ?
            """,
            (
                json.dumps(skills_list),
                years_exp,
                json.dumps(edu_records),
                json.dumps(metadata),
                overall_score,
                candidate_id
            )
        )

        # Check if existing ScoringResults row exists
        existing_score = db.execute_query(
            "SELECT ScoreID FROM ScoringResults WHERE CandidateID = ?",
            (candidate_id,),
            fetch_one=True
        )

        if existing_score:
            db.execute_query(
                """
                UPDATE ScoringResults
                SET SkillMatchScore = ?,
                    ExperienceMatchScore = ?,
                    EducationMatchScore = ?,
                    SemanticMatchScore = ?,
                    OverallScore = ?,
                    Strengths = ?,
                    Gaps = ?,
                    Recommendation = ?
                WHERE CandidateID = ?
                """,
                (
                    score_result.get('skill_match', 0),
                    score_result.get('experience_match', 0),
                    score_result.get('education_match', 0),
                    score_result.get('semantic_match', 0),
                    overall_score,
                    json.dumps(score_result.get('actionable_recs', [])),
                    json.dumps(score_result.get('missing_skills', [])),
                    recommendation,
                    candidate_id
                )
            )
        else:
            db.execute_query(
                """
                INSERT INTO ScoringResults (
                    CandidateID, RoleID, SkillMatchScore, ExperienceMatchScore,
                    EducationMatchScore, SemanticMatchScore,
                    OverallScore, Strengths, Gaps, Recommendation
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id, role_id,
                    score_result.get('skill_match', 0),
                    score_result.get('experience_match', 0),
                    score_result.get('education_match', 0),
                    score_result.get('semantic_match', 0),
                    overall_score,
                    json.dumps(score_result.get('actionable_recs', [])),
                    json.dumps(score_result.get('missing_skills', [])),
                    recommendation
                )
            )

        return {
            'status': 'success',
            'message': 'Candidate details updated and re-scored successfully',
            'candidate_id': candidate_id,
            'candidate_name': candidate_name,
            'role_name': role_name,
            'years_experience': years_exp,
            'overall_score': overall_score,
            'total_score': overall_score,
            'recommendation': recommendation,
            'scoring': score_result
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[UpdateCandidateDetails] Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to update candidate: {str(e)}")