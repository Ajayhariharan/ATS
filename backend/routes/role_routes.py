from fastapi import APIRouter, HTTPException
from database import db

router = APIRouter(prefix="/api/roles", tags=["Roles"])

@router.get("")
@router.get("/")
async def get_roles():
    """Get all active job roles with their required and preferred skills"""
    try:
        roles = db.execute_query(
            """
            SELECT RoleID, RoleName, Description, MinExperience, EducationRequirements
            FROM JobRoles WHERE IsActive = 1
            ORDER BY RoleName ASC
            """
        )
        
        result = []
        for row in roles:
            role_id = row[0]
            
            # Get required skills
            required = db.execute_query(
                """
                SELECT s.SkillName FROM RoleSkills rs
                JOIN Skills s ON rs.SkillID = s.SkillID
                WHERE rs.RoleID = ? AND rs.IsRequired = 1
                """,
                (role_id,)
            )
            required_skills = [r[0] for r in required]
            
            # Get preferred skills
            preferred = db.execute_query(
                """
                SELECT s.SkillName FROM RoleSkills rs
                JOIN Skills s ON rs.SkillID = s.SkillID
                WHERE rs.RoleID = ? AND rs.IsRequired = 0
                """,
                (role_id,)
            )
            preferred_skills = [r[0] for r in preferred]
            
            result.append({
                'role_id': row[0],
                'role_name': row[1],
                'description': row[2],
                'min_experience': row[3],
                'education_requirements': row[4],
                'required_skills': required_skills,
                'preferred_skills': preferred_skills
            })
        
        return result
    except Exception as e:
        print(f"[Roles] Error fetching roles: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{role_id}")
async def get_role(role_id: int):
    """Get single job role details"""
    try:
        row = db.execute_query(
            """
            SELECT RoleID, RoleName, Description, MinExperience, EducationRequirements
            FROM JobRoles WHERE RoleID = ? AND IsActive = 1
            """,
            (role_id,),
            fetch_one=True
        )
        
        if not row:
            raise HTTPException(status_code=404, detail="Role not found")
        
        # Get skills
        required = db.execute_query(
            """
            SELECT s.SkillName FROM RoleSkills rs
            JOIN Skills s ON rs.SkillID = s.SkillID
            WHERE rs.RoleID = ? AND rs.IsRequired = 1
            """,
            (role_id,)
        )
        required_skills = [r[0] for r in required]
        
        preferred = db.execute_query(
            """
            SELECT s.SkillName FROM RoleSkills rs
            JOIN Skills s ON rs.SkillID = s.SkillID
            WHERE rs.RoleID = ? AND rs.IsRequired = 0
            """,
            (role_id,)
        )
        preferred_skills = [r[0] for r in preferred]
        
        # Get JD
        jd = db.execute_query(
            """
            SELECT Title, Description, Responsibilities, Benefits
            FROM JobDescriptions WHERE RoleID = ?
            """,
            (role_id,),
            fetch_one=True
        )
        
        return {
            'role_id': row[0],
            'role_name': row[1],
            'description': row[2],
            'min_experience': row[3],
            'education_requirements': row[4],
            'required_skills': required_skills,
            'preferred_skills': preferred_skills,
            'job_description': jd[1] if jd else ''
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Roles] Error fetching role: {e}")
        raise HTTPException(status_code=500, detail=str(e))