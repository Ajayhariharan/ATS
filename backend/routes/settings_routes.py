import json
import traceback
from fastapi import APIRouter, HTTPException, Body
from database import db
from scoring import scoring_engine, get_scoring_weights, save_scoring_weights

router = APIRouter(prefix="/api/settings", tags=["Settings"])

@router.get("/scoring-weights")
async def get_scoring_weights_endpoint():
    """Returns current active scoring weight percentages"""
    try:
        weights = get_scoring_weights()
        return {
            "status": "success",
            "weights": weights
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load weights: {str(e)}")

@router.post("/scoring-weights")
async def update_scoring_weights_endpoint(payload: dict = Body(...)):
    """Updates scoring weights and batch recalculates all candidates based on new custom percentages"""
    try:
        skills = float(payload.get('skills', 40.0))
        experience = float(payload.get('experience', 30.0))
        education = float(payload.get('education', 15.0))
        semantic = float(payload.get('semantic', 15.0))
        recalculate_all = bool(payload.get('recalculate_all', True))

        total = skills + experience + education + semantic
        if abs(total - 100.0) > 0.5:
            raise HTTPException(
                status_code=400,
                detail=f"Scoring percentages must sum to 100%. Current sum: {total:.1f}%"
            )

        saved = save_scoring_weights(skills, experience, education, semantic)

        recalc_count = 0
        if recalculate_all:
            cand_rows = db.execute_query("SELECT CandidateID FROM Candidates")
            if cand_rows:
                for row in cand_rows:
                    cid = row[0]
                    cand_row = db.execute_query(
                        "SELECT CandidateID, RoleID, ResumeText, ParsedSkills, YearsExperience, Education, Certifications FROM Candidates WHERE CandidateID = ?",
                        (cid,),
                        fetch_one=True
                    )
                    if not cand_row:
                        continue

                    role_id = cand_row[1]
                    resume_text = cand_row[2] or ""
                    parsed_skills = json.loads(cand_row[3]) if cand_row[3] else []
                    years_exp = float(cand_row[4] or 0.0)
                    edu_records = json.loads(cand_row[5]) if cand_row[5] else []
                    cert_data = json.loads(cand_row[6]) if cand_row[6] else {}
                    candidate_name = cert_data.get('candidate_name', f'Candidate #{cid}')

                    role = db.execute_query(
                        "SELECT RoleID, RoleName, MinExperience, EducationRequirements FROM JobRoles WHERE RoleID = ?",
                        (role_id,),
                        fetch_one=True
                    )
                    if not role:
                        continue

                    role_name = role[1]
                    min_exp = float(role[2] or 0)
                    edu_req = role[3] or ""

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
                        items = []
                        for e in edu_records:
                            if isinstance(e, dict):
                                deg = e.get('course') or e.get('degree') or e.get('level_of_education') or ''
                                inst = e.get('institute') or e.get('institution') or ''
                                items.append(f"{deg} ({inst})".strip())
                            else:
                                items.append(str(e))
                        education_str = ", ".join(items)
                    else:
                        education_str = str(edu_records)

                    candidate_data = {
                        'candidate_id': cid,
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

                    score_result = scoring_engine.score_candidate(candidate_data, role_data, jd_text, custom_weights=saved)
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
                            cid
                        )
                    )
                    db.execute_query(
                        "UPDATE Candidates SET TotalScore = ?, YearsExperience = ? WHERE CandidateID = ?",
                        (overall_score, years_exp, cid)
                    )
                    recalc_count += 1

        return {
            "status": "success",
            "message": f"Scoring weights updated: Skills {saved['skills']}%, Exp {saved['experience']}%, Edu {saved['education']}%, Semantic {saved['semantic']}%.",
            "weights": saved,
            "recalculated_candidates": recalc_count
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[UpdateScoringWeights] Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to update weights: {str(e)}")

