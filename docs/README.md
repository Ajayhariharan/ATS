# 🏢 Enterprise ATS (Applicant Tracking System) with AI Extraction & 4-Pillar Scoring

Welcome to the **Enterprise ATS** developer and engineering documentation. This system is a high-throughput, enterprise-grade Applicant Tracking System built with **FastAPI (Python 3.10+)**, **React 19 + Vite**, **Microsoft SQL Server (pyodbc)**, and **OpenRouter Gemini 2.5 Flash / Sentence-Embeddings**.

---

## 📑 Documentation Index

| File | Document | Description |
| :--- | :--- | :--- |
| [`01_SYSTEM_ARCHITECTURE.md`](./01_SYSTEM_ARCHITECTURE.md) | **System Architecture** | High-level architecture, module breakdown, sequence diagrams, and end-to-end data flow. |
| [`02_DATABASE_SCHEMA_AND_MODELS.md`](./02_DATABASE_SCHEMA_AND_MODELS.md) | **Database Schema & Models** | Complete MSSQL schema, tables, foreign keys, auto-migration logic, and vector storage. |
| [`03_AI_EXTRACTION_AND_PARSING.md`](./03_AI_EXTRACTION_AND_PARSING.md) | **AI Extraction & Parsing** | Two-stage extraction pipeline (Deterministic Layout + LLM Refinement), degree normalization, tenure math. |
| [`04_ATS_SCORING_ENGINE.md`](./04_ATS_SCORING_ENGINE.md) | **4-Pillar ATS Scoring Engine** | Mathematical formulation for Skills, Experience, Education, and Semantic Vector Matching. |
| [`05_API_DOCUMENTATION.md`](./05_API_DOCUMENTATION.md) | **REST API Reference** | Comprehensive FastAPI endpoint documentation with request/response schemas and curl examples. |
| [`06_FRONTEND_ARCHITECTURE.md`](./06_FRONTEND_ARCHITECTURE.md) | **Frontend Architecture** | React 19 component hierarchy, state flow, Neo-Brutalist UI system, and real-time modal/toast telemetry. |
| [`07_DEVELOPER_ONBOARDING_AND_SETUP.md`](./07_DEVELOPER_ONBOARDING_AND_SETUP.md) | **Developer Onboarding & Setup** | Step-by-step setup on a fresh PC, ODBC drivers, `.env` configuration, and running servers. |
| [`08_HANDOVER_AND_MAINTENANCE_GUIDE.md`](./08_HANDOVER_AND_MAINTENANCE_GUIDE.md) | **Handover & Production Runbook** | Production deployment, security standards, Docker deployment, troubleshooting, and runbooks. |

---

## 🌟 Key Capabilities & Highlights

1. **Two-Stage Intelligent Resume Ingestion**:
   - **Stage 1 (Deterministic Extraction)**: Extracts raw text, layout blocks, emails, phones, and structural sections from PDF, DOCX, and TXT files with zero external API calls.
   - **Stage 2 (Gemini LLM Extraction & Structuring)**: Utilizes Google Gemini 2.5 Flash via OpenRouter for high-accuracy JSON parsing of experience, projects, education records, and skills.

2. **Zero-Loss Candidate Preview & Verification**:
   - Extracted candidate details are presented to recruiters in a structured preview tab before scoring.
   - Recruiters can verify, edit, add, or correct fields (degrees, companies, dates, skills) prior to committing and running ATS scoring.

3. **Deterministic 4-Pillar ATS Scoring Engine**:
   - **Pillar 1: Technical & Soft Skills Match (Default 40%)**: Exact token match + contextual synonym matching.
   - **Pillar 2: Experience Tenure Match (Default 30%)**: Fractional tenure parsing (single-month internships to multi-year careers).
   - **Pillar 3: Education Level Match (Default 15%)**: 5-Tier Degree Hierarchy ranking (Ph.D > Master's > Bachelor's > Diploma > High School).
   - **Pillar 4: Semantic Vector & Keyword Match (Default 15%)**: Blended keyword density and cosine similarity embeddings.

4. **Zero-LLM Instant Dynamic Weight Recalculation**:
   - Recalculates scores across thousands of candidates in milliseconds without costly LLM API re-runs.
   - Configurable custom weights stored in persistent configuration.

5. **Self-Healing MSSQL Database Initialization**:
   - Automatically detects, creates, seeds, and verifies the `ATSSystem` MSSQL database and 8 core tables on first launch without requiring manual SQL script execution.

---

## ⚡ Quick Start Overview

```bash
# 1. Backend Setup
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
# Configure backend/.env
python main.py

# 2. Frontend Setup
cd ../frontend
npm install
npm run dev
```

* **Frontend URL**: `http://localhost:3000` (or `http://localhost:5173`)
* **Backend API**: `http://localhost:8000`
* **Swagger API Docs**: `http://localhost:8000/docs`

