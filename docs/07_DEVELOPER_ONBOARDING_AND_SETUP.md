# 🚀 Developer Onboarding, Environment Setup & Local Installation

This guide walks new developers through setting up and running the Enterprise ATS codebase from scratch on Windows, macOS, or Linux.

---

## 1. System Prerequisites

Before starting, ensure the following software is installed on the machine:

| Prerequisite | Minimum Version | Installation Link / Notes |
| :--- | :--- | :--- |
| **Python** | `3.10+` | [python.org/downloads](https://www.python.org/downloads/) (Check "Add python.exe to PATH") |
| **Node.js & npm** | `Node 18+ / npm 9+` | [nodejs.org](https://nodejs.org/) (LTS recommended) |
| **Microsoft SQL Server** | 2019 / 2022 / Express | [SQL Server Downloads](https://www.microsoft.com/en-us/sql-server/sql-server-downloads) (Default instance: `localhost` or machine name) |
| **ODBC Driver 18** | Version 18.x | [MS ODBC Driver 18 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server) |
| **Git** | `2.30+` | [git-scm.com](https://git-scm.com/) |
| **OpenRouter API Key** | Active API Key | [openrouter.ai](https://openrouter.ai/) for Gemini 2.5 Flash access |

---

## 2. Backend Setup (FastAPI + SQL Server)

### Step 2.1: Clone the Repository & Navigate to Backend
```powershell
cd "ATS WITH AI EXTRACTION\backend"
```

### Step 2.2: Create and Activate Python Virtual Environment
* **Windows (PowerShell)**:
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  ```
* **Linux / macOS**:
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### Step 2.3: Install Python Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2.4: Configure Environment Variables (`.env`)
Create a `.env` file in the `backend/` folder (or copy from `.env.example` below):

```ini
# ==============================================================================
# DATABASE CONFIGURATION (Microsoft SQL Server)
# ==============================================================================
DB_HOST=localhost
DB_NAME=ATSSystem
DB_DRIVER=ODBC Driver 18 for SQL Server
DB_TRUST_CERTIFICATE=yes
DB_USE_WINDOWS_AUTH=true

# If using SQL Server Authentication instead of Windows Auth:
# DB_USE_WINDOWS_AUTH=false
# DB_USER=sa
# DB_PASSWORD=YourStrongPassword!

# ==============================================================================
# OPENROUTER GEMINI LLM CONFIGURATION
# ==============================================================================
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENROUTER_MODEL=google/gemini-2.5-flash
OPENROUTER_URL=https://openrouter.ai/api/v1/chat/completions

# ==============================================================================
# SERVER CONFIGURATION
# ==============================================================================
HOST=0.0.0.0
PORT=8000
DEBUG=True
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000
```

### Step 2.5: Start the Backend Server
```bash
python main.py
```
> **Self-Healing Database Note**: You **DO NOT** need to create tables manually. On startup, `db.init_database()` automatically creates the `ATSSystem` database, tables, foreign keys, and seed data.

Verify backend health by opening `http://localhost:8000/health` or `http://localhost:8000/docs` in your browser.

---

## 3. Frontend Setup (React 19 + Vite)

### Step 3.1: Navigate to Frontend Directory
Open a new terminal window:
```powershell
cd "ATS WITH AI EXTRACTION\frontend"
```

### Step 3.2: Install Node Dependencies
```bash
npm install
```

### Step 3.3: Start Frontend Development Server
```bash
npm run dev
```

* The app will start at `http://localhost:3000` (or `http://localhost:5173`).
* Vite proxy automatically routes `/api/*` requests to `http://localhost:8000`.

---

## 4. Verifying End-to-End Operation

1. Open `http://localhost:3000` in your web browser.
2. Select a target role from the header dropdown (e.g., **Data Analyst**).
3. Click the yellow **`+` (Upload Resume)** button.
4. Drag and drop a sample resume PDF from the `Resumes/` folder.
5. Verify that the **Candidate Details Preview Tab** opens with extracted details.
6. Click **"CONFIRM & SCORE CANDIDATE"**.
7. Confirm that the 4-Pillar Score Breakdown view appears with telemetry and recommendations.

---

## 5. Common Troubleshooting & FAQs

### Q1: `pyodbc.Error: ('08001', '[Microsoft][ODBC Driver 18 for SQL Server]...')`
* **Fix**: Ensure SQL Server Service is running. Open Windows Services (`services.msc`) and verify `SQL Server (MSSQLSERVER)` or `SQL Server (SQLEXPRESS)` is Started.
* In `.env`, ensure `DB_TRUST_CERTIFICATE=yes` is set.
* If using a named instance, set `DB_HOST=localhost\SQLEXPRESS`.

### Q2: `ModuleNotFoundError: No module named 'fastapi'`
* **Fix**: Ensure your virtual environment is active (`venv\Scripts\Activate.ps1`).

### Q3: `OpenRouter API 401 Unauthorized`
* **Fix**: Verify your `OPENROUTER_API_KEY` in `backend/.env` has active credits and valid permissions.

