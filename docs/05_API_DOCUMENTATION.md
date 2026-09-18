# 📡 REST API Reference & Integration Guide

The Enterprise ATS exposes a high-performance RESTful API built on **FastAPI**. Interactive Swagger UI documentation is available at `http://localhost:8000/docs` and Redoc at `http://localhost:8000/redoc`.

---

## 1. Base URL & Common Headers

* **Base URL**: `http://localhost:8000` (or `http://<server-ip>:8000`)
* **Standard Headers**:
  - `Content-Type: application/json`
  - `Accept: application/json`

---

## 2. System & Health Check Endpoints

### 2.1 Get System Status
* **Endpoint**: `GET /`
* **Description**: Returns ATS system health, database connection info, and active LLM configuration.
* **Response `200 OK`**:
```json
{
  "message": "Enterprise ATS System",
  "version": "1.0.0",
  "status": "operational",
  "database": "ATSSystem",
  "server": "REXA",
  "llm_provider": "OpenRouter Gemini"
}
```

### 2.2 Health Check
* **Endpoint**: `GET /health`
* **Description**: Liveness and readiness probe for load balancers and container orchestrators.
* **Response `200 OK`**:
```json
{
  "status": "healthy",
  "openrouter_gemini_configured": true,
  "database_configured": true
}
```

---

## 3. Job Roles & Requirements API (`/api/roles`)

### 3.1 List All Active Roles
* **Endpoint**: `GET /api/roles`
* **Response `200 OK`**:
```json
[
  {
    "role_id": 6,
    "role_name": "Data Analyst",
    "description": "Analyze data and create visualizations to support business decisions",
    "min_experience": 2,
    "education_requirements": "Bachelor in Statistics or related field",
    "candidate_count": 8,
    "required_skills": ["Python", "SQL", "Pandas", "Statistical Analysis", "Data Visualization"],
    "preferred_skills": ["Tableau", "PowerBI"]
  }
]
```

### 3.2 Get Role Details & Job Description
* **Endpoint**: `GET /api/roles/{role_id}`
* **Path Parameter**: `role_id` (`int`)
* **Response `200 OK`**:
```json
{
  "role_id": 6,
  "role_name": "Data Analyst",
  "min_experience": 2,
  "education_requirements": "Bachelor in Statistics or related field",
  "job_description": {
    "title": "Data Analyst",
    "description": "Transform data into actionable business intelligence.",
    "responsibilities": "Create KPI dashboards, write SQL queries, statistical modelling."
  },
  "skills": [
    {"name": "Python", "is_required": true, "weight": 1.0},
    {"name": "SQL", "is_required": true, "weight": 1.0}
  ]
}
```

---

## 4. Candidate Ingestion & Scoring API (`/api/candidates`)

### 4.1 Step 1: Extract Resume Preview (Zero-Scoring)
* **Endpoint**: `POST /api/candidates/extract-preview`
* **Content-Type**: `multipart/form-data`
* **Form Parameters**:
  - `file`: Resume document binary (`.pdf`, `.docx`, `.txt`)
  - `role_id`: `int` (e.g. `6`)
* **cURL Example**:
```bash
curl -X POST "http://localhost:8000/api/candidates/extract-preview" \
  -F "file=@resume.pdf" \
  -F "role_id=6"
```
* **Response `200 OK`**:
```json
{
  "success": true,
  "candidate_name": "Ajay H",
  "email": "ajayhofc@gmail.com",
  "phone": "+91 9361968178",
  "summary": "Web Development (Full-Stack), Data Structures & Algorithms, Machine Learning.",
  "experience_records": [
    {
      "company": "Lakshmi Corporate Services Coimbatore",
      "designation": "Frontend Developer Intern",
      "joining_date": "Dec 2025",
      "relieved_date": "",
      "work_duration": "",
      "employment_type": "Full Time",
      "currently_working": false,
      "bullets": ["Built UI components with React."]
    }
  ],
  "project_records": [
    {
      "title": "Smart Water Pressure Management System — Flask, ML",
      "organization": "Independent Project",
      "period": "Jan 2026 – Apr 2026",
      "bullets": ["Real-time monitoring and anomaly detection."]
    }
  ],
  "education_records": [
    {
      "level_of_education": "Postgraduate",
      "course": "M.Sc. Data Science",
      "institute": "Thiagarajar College of Engineering Madurai",
      "from_year": "2023",
      "to_year": "2028",
      "score_type": "CGPA",
      "score": "7.50",
      "currently_pursuing": true
    }
  ],
  "skills_list": ["Python", "SQL", "Pandas", "NumPy", "React.js"],
  "certifications": [],
  "role_id": 6,
  "raw_text": "...",
  "filename": "resume.pdf"
}
```

---

### 4.2 Step 2: Confirm, Store & Score Candidate
* **Endpoint**: `POST /api/candidates/submit-and-score`
* **Description**: Commits verified candidate details into SQL Server and runs the 4-Pillar Scoring evaluation.
* **Request Body (JSON)**:
```json
{
  "candidate_name": "Ajay H",
  "email": "ajayhofc@gmail.com",
  "phone": "+91 9361968178",
  "summary": "Full stack and Data science candidate.",
  "experience_records": [
    {
      "company": "Lakshmi Corporate Services Coimbatore",
      "designation": "Frontend Developer Intern",
      "joining_date": "Dec 2025",
      "relieved_date": "",
      "work_duration": "",
      "currently_working": false
    }
  ],
  "education_records": [
    {
      "level_of_education": "Postgraduate",
      "course": "M.Sc. Data Science",
      "institute": "Thiagarajar College of Engineering Madurai",
      "from_year": "2023",
      "to_year": "2028"
    }
  ],
  "skills_list": ["Python", "SQL", "Pandas", "NumPy", "Statistical Analysis"],
  "role_id": 6,
  "raw_text": "...",
  "filename": "resume.pdf"
}
```
* **Response `200 OK`**:
```json
{
  "message": "Candidate submitted and scored successfully",
  "candidate_id": 1154,
  "candidate_name": "Ajay H",
  "role_name": "Data Analyst",
  "overall_score": 62.1,
  "skill_match": 80.0,
  "experience_match": 5.0,
  "education_match": 100.0,
  "semantic_match": 31.8,
  "recommendation": "Consider",
  "matched_skills": ["Pandas", "Python", "SQL", "Statistical Analysis"],
  "missing_skills": ["Data Visualization"],
  "actionable_recs": [
    "[1] Add missing required skills: Data Visualization.",
    "[2] Candidate has ~0.1 yrs experience; role requires 2 yrs.",
    "[3] Incorporate missing domain keywords from JD: analyze, business, dashboards."
  ]
}
```

---

### 4.3 Get Candidates Leaderboard for Role
* **Endpoint**: `GET /api/candidates/role/{role_id}`
* **Response `200 OK`**:
```json
[
  {
    "candidate_id": 1154,
    "candidate_name": "Ajay H",
    "total_score": 62.1,
    "years_experience": 0.1,
    "recommendation": "Consider",
    "skill_match": 80.0,
    "experience_match": 5.0,
    "education_match": 100.0,
    "semantic_match": 31.8,
    "created_at": "2026-09-09T11:55:27"
  }
]
```

---

### 4.4 Get Full Candidate Breakdown & Telemetry
* **Endpoint**: `GET /api/candidates/{candidate_id}`
* **Response `200 OK`**:
```json
{
  "candidate": {
    "candidate_id": 1154,
    "full_name": "Ajay H",
    "email": "ajayhofc@gmail.com",
    "phone": "+91 9361968178",
    "total_years_experience": 0.1,
    "experience_records": [...],
    "education_records": [...],
    "skills_list": [...]
  },
  "scoring": {
    "overall_score": 62.1,
    "skill_match": 80.0,
    "experience_match": 5.0,
    "education_match": 100.0,
    "semantic_match": 31.8,
    "recommendation": "Consider",
    "formula_str": "Formula: (0.40 * 80.0) + (0.30 * 5.0) + (0.15 * 100.0) + (0.15 * 31.8) = 62.1%",
    "telemetry": {
      "pillar1": {
        "title": "SKILLS MATCHING (Weight: 40%)",
        "calc_str": "Calculation: (4.0 matched / 5.0 total) * 100 = 80.0%"
      },
      "pillar2": {
        "title": "EXPERIENCE MATCHING (Weight: 30%)",
        "candidate_years": 0.1,
        "required_years": 2.0,
        "calc_str": "Calculation: min(100, (0.1 candidate years / 2.0 required years) * 100) = 5.0%"
      },
      "pillar3": {
        "title": "EDUCATION MATCHING (Weight: 15%)",
        "insight": "Candidate qualification (Master's Degree) meets or exceeds required Bachelor's Degree."
      },
      "pillar4": {
        "title": "SEMANTIC & DOMAIN KEYWORDS MATCHING (Weight: 15%)",
        "calc_str": "Calculation: 50% Keyword Density + 50% BGE Embedding Cosine Similarity = 31.8%"
      }
    }
  }
}
```

---

### 4.5 Recalculate Candidate Score (Zero-LLM)
* **Endpoint**: `POST /api/candidates/{candidate_id}/recalculate`
* **Description**: Recalculates all 4 pillars and overall score for a candidate in `< 5ms`.
* **Response `200 OK`**:
```json
{
  "message": "Score recalculated successfully (Zero LLM used)",
  "candidate_id": 1154,
  "overall_score": 62.1,
  "recommendation": "Consider"
}
```

---

### 4.6 Delete Candidate
* **Endpoint**: `DELETE /api/candidates/{candidate_id}`
* **Response `200 OK`**:
```json
{
  "message": "Candidate #1154 deleted successfully."
}
```

---

## 5. Settings & Scoring Weights API (`/api/settings`)

### 5.1 Get Active Weights
* **Endpoint**: `GET /api/settings/scoring-weights`
* **Response `200 OK`**:
```json
{
  "weights": {
    "skills": 40.0,
    "experience": 30.0,
    "education": 15.0,
    "semantic": 15.0
  }
}
```

### 5.2 Update Active Weights & Batch Recalculate
* **Endpoint**: `POST /api/settings/scoring-weights`
* **Request Body (JSON)**:
```json
{
  "weights": {
    "skills": 35.0,
    "experience": 35.0,
    "education": 15.0,
    "semantic": 15.0
  }
}
```
* **Response `200 OK`**:
```json
{
  "message": "Scoring weights updated and 42 candidate scores recalculated successfully.",
  "weights": {
    "skills": 35.0,
    "experience": 35.0,
    "education": 15.0,
    "semantic": 15.0
  },
  "recalculated_candidates_count": 42
}
```

