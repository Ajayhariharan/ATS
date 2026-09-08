from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# Auth Models
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: str

class UserResponse(BaseModel):
    user_id: int
    username: str
    email: str
    full_name: str
    role: str
    token: Optional[str] = None

# Role Models
class RoleResponse(BaseModel):
    role_id: int
    role_name: str
    description: str
    min_experience: int
    education_requirements: str
    required_skills: List[str]
    preferred_skills: List[str]
    job_description: Optional[str] = None

# Candidate Models
class CandidateUploadRequest(BaseModel):
    role_id: int

class CandidateResponse(BaseModel):
    candidate_id: int
    role_name: str
    resume_file_name: str
    years_experience: float
    total_score: float
    uploaded_at: str
    overall_score: float
    recommendation: str
    skill_match: float
    experience_match: float
    education_match: float
    semantic_match: float

# Score Models
class ScoreResponse(BaseModel):
    candidate_id: int
    candidate_name: str
    role_name: str
    overall_score: float
    skill_match: float
    experience_match: float
    education_match: float
    semantic_match: float
    preferred_skills_match: float
    certifications_score: float
    strengths: List[str]
    gaps: List[str]
    recommendation: str

# Admin Models
class AdminStatsResponse(BaseModel):
    total_users: int
    total_candidates: int
    total_roles: int
    average_score: float
    recent_activities: List[dict]