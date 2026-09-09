import os
import json
import re
import math
import requests
from typing import List, Dict, Tuple, Any
from dotenv import load_dotenv

load_dotenv()

# Pre-compiled NLP Normalization Map
NLP_NORMALIZATION_MAP = {
    'ml': 'Machine Learning',
    'deep learning': 'Machine Learning',
    'ai': 'Artificial Intelligence',
    'nlp': 'Natural Language Processing',
    'react.js': 'React',
    'reactjs': 'React',
    'next.js': 'Next.js',
    'nextjs': 'Next.js',
    'node.js': 'Node.js',
    'nodejs': 'Node.js',
    'express.js': 'Express.js',
    'expressjs': 'Express.js',
    'vue.js': 'Vue.js',
    'vuejs': 'Vue.js',
    'postgres': 'PostgreSQL',
    'postgresql': 'PostgreSQL',
    'mysql': 'SQL',
    't-sql': 'SQL',
    'pl/sql': 'SQL',
    'ts': 'TypeScript',
    'js': 'JavaScript',
    'py': 'Python',
    'k8s': 'Kubernetes',
    'aws': 'Amazon Web Services',
    'gcp': 'Google Cloud Platform',
    'p&c': 'Property & Casualty',
    'l&a': 'Life & Annuities'
}

# Domain skill aliases and semantic equivalences for keyword semantic matching
SKILL_ALIASES = {
    'sql': ['mysql', 'postgresql', 'postgres', 'sqlite', 'oracle', 'sql server', 'pl/sql', 'nosql', 't-sql'],
    'react': ['react.js', 'reactjs', 'react native', 'redux', 'primereact', 'next.js', 'nextjs'],
    'javascript': ['js', 'ecmascript', 'typescript', 'ts', 'react', 'node', 'express'],
    'python': ['django', 'flask', 'fastapi', 'pandas', 'numpy', 'scipy', 'scikit-learn', 'pytorch', 'tensorflow'],
    'html css': ['html', 'css', 'html5', 'css3', 'tailwind', 'bootstrap', 'sass', 'scss'],
    'node.js': ['node', 'nodejs', 'express', 'express.js', 'nest.js', 'nestjs', 'npm', 'mern'],
    'machine learning': ['ml', 'deep learning', 'scikit-learn', 'scikit learn', 'tensorflow', 'pytorch', 'weka', 'predictive analytics', 'artificial intelligence', 'ai'],
    'data visualization': ['tableau', 'powerbi', 'power bi', 'matplotlib', 'seaborn', 'plotly', 'd3.js', 'looker'],
    'statistical analysis': ['statistics', 'statistical', 'probability', 'regression', 'hypothesis testing', 'analytics', 'predictive analytics'],
    'pandas': ['dataframe', 'data manipulation', 'numpy', 'scikit-learn'],
    'numpy': ['numerical python', 'pandas', 'scipy'],
    'docker': ['containerization', 'containers', 'kubernetes', 'k8s'],
    'aws': ['amazon web services', 'ec2', 's3', 'lambda', 'cloud'],
    'git': ['github', 'gitlab', 'version control', 'bitbucket'],
    'linux': ['unix', 'ubuntu', 'centos', 'bash', 'shell scripting'],
    'communication': ['interpersonal', 'presentation', 'writing', 'verbal communication'],
    'project management': ['agile', 'scrum', 'jira', 'kanban', 'sprint planning', 'leadership']
}

_OPENROUTER_EMBED_CACHE = {}

def ensure_embedding_tables_exist():
    """Ensure JDEmbeddings and CandidateEmbeddings tables exist in SQL Server"""
    try:
        from database import db
        db.execute_query("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'JDEmbeddings')
            BEGIN
                CREATE TABLE JDEmbeddings (
                    EmbeddingID INT IDENTITY(1,1) PRIMARY KEY,
                    RoleID INT NULL,
                    SourceType VARCHAR(50) NULL,
                    TextKey VARCHAR(500) NOT NULL UNIQUE,
                    EmbeddingVector NVARCHAR(MAX) NOT NULL,
                    ModelName VARCHAR(100) NULL,
                    CreatedAt DATETIME DEFAULT GETDATE()
                );
            END
        """)
        db.execute_query("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'CandidateEmbeddings')
            BEGIN
                CREATE TABLE CandidateEmbeddings (
                    EmbeddingID INT IDENTITY(1,1) PRIMARY KEY,
                    CandidateID INT NULL,
                    SourceType VARCHAR(50) NULL,
                    TextKey VARCHAR(500) NOT NULL UNIQUE,
                    EmbeddingVector NVARCHAR(MAX) NOT NULL,
                    ModelName VARCHAR(100) NULL,
                    CreatedAt DATETIME DEFAULT GETDATE()
                );
            END
        """)
    except Exception as e:
        pass

# Ensure tables exist on module load
ensure_embedding_tables_exist()

def get_openrouter_embeddings(texts: List[str], model: str = None, source_type: str = "candidate") -> List[List[float]]:
    """
    Fetch semantic embeddings using BGE Base EN v1.5 with dedicated SQL Server DB tables:
    - JDEmbeddings for Job Description and JD Skills (source_type="jd")
    - CandidateEmbeddings for Candidate Resumes and Candidate Skills (source_type="candidate")
    """
    if not texts:
        return []
    
    target_table = "JDEmbeddings" if source_type.lower().startswith("jd") else "CandidateEmbeddings"
    target_model = model or os.getenv("SEMANTIC_EMBEDDING_MODEL", "baai/bge-base-en-v1.5").strip()
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    embed_url = os.getenv("OPENROUTER_EMBEDDING_URL", "https://openrouter.ai/api/v1/embeddings").strip()
    
    if not api_key:
        print("[EmbeddingService] Notice: OPENROUTER_API_KEY not configured, skipping semantic embeddings.")
        return [[] for _ in texts]
        
    results = [None] * len(texts)
    missing_indices = []
    missing_texts = []
    
    # 1. Level 1: In-memory caching (RAM)
    for idx, t in enumerate(texts):
        cl_text = (t or "").strip()
        if not cl_text:
            results[idx] = []
            continue
        key = f"{target_table}:{target_model}:{cl_text.lower()[:450]}"
        if key in _OPENROUTER_EMBED_CACHE:
            results[idx] = _OPENROUTER_EMBED_CACHE[key]
        else:
            missing_indices.append(idx)
            missing_texts.append(cl_text[:1500])
            
    if not missing_texts:
        return results

    # 2. Level 2: SQL Server DB Table Caching (JDEmbeddings or CandidateEmbeddings)
    still_missing_indices = []
    still_missing_texts = []
    try:
        from database import db
        for m_idx, m_txt in zip(missing_indices, missing_texts):
            db_key = f"{target_model}:{m_txt.strip().lower()[:450]}"
            row = db.execute_query(
                f"SELECT EmbeddingVector FROM {target_table} WHERE TextKey = ?",
                (db_key,),
                fetch_one=True
            )
            if row and row[0]:
                try:
                    vec = json.loads(row[0])
                    results[m_idx] = vec
                    cache_key = f"{target_table}:{target_model}:{m_txt.strip().lower()[:450]}"
                    _OPENROUTER_EMBED_CACHE[cache_key] = vec
                except Exception:
                    still_missing_indices.append(m_idx)
                    still_missing_texts.append(m_txt)
            else:
                still_missing_indices.append(m_idx)
                still_missing_texts.append(m_txt)
    except Exception as e:
        still_missing_indices = missing_indices
        still_missing_texts = missing_texts

    if not still_missing_texts:
        return [r if r is not None else [] for r in results]

    # 3. Level 3: Call OpenRouter API for un-cached items and persist to target SQL Server table
    try:
        resp = requests.post(
            embed_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": target_model,
                "input": still_missing_texts
            },
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            from database import db
            for m_idx, item in zip(still_missing_indices, data):
                emb = item.get("embedding", [])
                results[m_idx] = emb
                raw_t = texts[m_idx].strip()
                db_key = f"{target_model}:{raw_t.lower()[:450]}"
                cache_key = f"{target_table}:{target_model}:{raw_t.lower()[:450]}"
                _OPENROUTER_EMBED_CACHE[cache_key] = emb
                # Persist embedding into specific SQL Server table
                try:
                    src_tag = "JD_ITEM" if target_table == "JDEmbeddings" else "CANDIDATE_ITEM"
                    db.execute_query(
                        f"""
                        IF NOT EXISTS (SELECT 1 FROM {target_table} WHERE TextKey = ?)
                        BEGIN
                            INSERT INTO {target_table} (TextKey, EmbeddingVector, ModelName, SourceType, CreatedAt)
                            VALUES (?, ?, ?, ?, GETDATE())
                        END
                        """,
                        (db_key, db_key, json.dumps(emb), target_model, src_tag)
                    )
                except Exception as dbe:
                    print(f"[EmbeddingService] DB insert into {target_table} notice: {dbe}")
        else:
            print(f"[EmbeddingService] OpenRouter embeddings error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[EmbeddingService] Embeddings request failed: {e}")
        
    return [r if r is not None else [] for r in results]

def vector_cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes exact cosine similarity between two float vectors in pure Python math (0 CPU)"""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    return (dot / (n1 * n2)) if n1 > 0 and n2 > 0 else 0.0

def normalize_nlp_term(term: str) -> str:
    """Standardizes technical acronyms and terms using NLP normalization rules"""
    t_clean = term.strip().lower()
    return NLP_NORMALIZATION_MAP.get(t_clean, term.strip())

DEFAULT_SCORING_WEIGHTS = {
    'skills': 40.0,
    'experience': 30.0,
    'education': 15.0,
    'semantic': 15.0
}

_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scoring_settings.json')

def get_scoring_weights() -> dict:
    """Retrieve active scoring weights from JSON config or default to (40, 30, 15, 15)"""
    if os.path.exists(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                weights = data.get('weights', data)
                s = float(weights.get('skills', 40.0))
                e = float(weights.get('experience', 30.0))
                ed = float(weights.get('education', 15.0))
                sem = float(weights.get('semantic', 15.0))
                total = s + e + ed + sem
                if total > 0:
                    return {
                        'skills': round(s, 1),
                        'experience': round(e, 1),
                        'education': round(ed, 1),
                        'semantic': round(sem, 1)
                    }
        except Exception as err:
            print(f"[ScoringSettings] Error reading weights file: {err}")
    return dict(DEFAULT_SCORING_WEIGHTS)

def save_scoring_weights(skills: float, experience: float, education: float, semantic: float) -> dict:
    """Persist custom scoring weights to JSON configuration file"""
    s = float(skills)
    e = float(experience)
    ed = float(education)
    sem = float(semantic)
    total = s + e + ed + sem
    if total <= 0:
        raise ValueError("Sum of weights must be greater than 0.")
    
    weights = {
        'skills': round(s, 1),
        'experience': round(e, 1),
        'education': round(ed, 1),
        'semantic': round(sem, 1)
    }
    try:
        with open(_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'weights': weights}, f, indent=2)
        print(f"[ScoringSettings] Saved new scoring weights: {weights}")
    except Exception as err:
        print(f"[ScoringSettings] Error saving weights: {err}")
    return weights

class ScoringEngine:
    def __init__(self):
        self.stop_words = {
            'a', 'an', 'the', 'and', 'or', 'but', 'for', 'nor', 'on', 'at', 'to', 'by',
            'of', 'with', 'without', 'about', 'after', 'before', 'during', 'through',
            'between', 'among', 'within', 'without', 'from', 'into', 'over', 'under',
            'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'shall', 'should', 'can', 'could',
            'may', 'might', 'must', 'that', 'this', 'these', 'those', 'as', 'if'
        }

    def calculate_keyword_semantic_skills_match(
        self, 
        candidate_skills: List[str], 
        required_skills: List[str],
        resume_text: str = ""
    ) -> Tuple[float, List[str], List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
        if not required_skills:
            return 1.0, [], [], [], []
        
        # 1. NLP Normalization
        cand_skills_clean = [normalize_nlp_term(s) for s in candidate_skills if s and s.strip()]
        cand_skills_lower = [s.lower() for s in cand_skills_clean]
        resume_text_lower = resume_text.lower() if resume_text else ""
        
        # Pre-fetch candidate embeddings via OpenRouter BGE Base EN v1.5 (Stored in CandidateEmbeddings table)
        cand_embeddings = []
        if cand_skills_clean:
            cand_embeddings = get_openrouter_embeddings(cand_skills_clean, source_type="candidate")
        
        matched_exact = []
        matched_details = []
        missing = []
        total_score_sum = 0.0

        for req in required_skills:
            req_clean = normalize_nlp_term(req)
            req_lower = req_clean.lower()
            
            # Step A: Exact Normalized Match in Candidate Skills List
            if req_lower in cand_skills_lower or req.strip().lower() in [s.strip().lower() for s in candidate_skills]:
                matched_exact.append(req.strip())
                matched_details.append({
                    "skill": req.strip(),
                    "matched_with": req.strip(),
                    "source": "Skills Section",
                    "display": f'{req.strip()} = "{req.strip()}" (Skills Section)',
                    "type": "exact"
                })
                total_score_sum += 1.0
                continue
            
            # Step B: Substring / Compound Match in Candidate Skills List
            found_sub = False
            for cs_low, cs_orig in zip(cand_skills_lower, cand_skills_clean):
                if req_lower in cs_low or cs_low in req_lower:
                    matched_exact.append(req.strip())
                    matched_details.append({
                        "skill": req.strip(),
                        "matched_with": cs_orig,
                        "source": "Skills Section",
                        "display": f'{req.strip()} = "{cs_orig}" (Skills Section)',
                        "type": "substring"
                    })
                    total_score_sum += 1.0
                    found_sub = True
                    break
            if found_sub:
                continue

            # Step C: Direct Word Boundary Match in Resume Body Text
            if resume_text_lower and (re.search(r'\b' + re.escape(req_lower) + r'\b', resume_text_lower) or re.search(r'\b' + re.escape(req.strip().lower()) + r'\b', resume_text_lower)):
                matched_exact.append(req.strip())
                matched_details.append({
                    "skill": req.strip(),
                    "matched_with": req.strip(),
                    "source": "Resume Text",
                    "display": f'{req.strip()} = "{req.strip()}" (in Resume Text)',
                    "type": "body_text"
                })
                total_score_sum += 1.0
                continue

            # Step D: Domain Keyword Semantic Aliases Match
            found_alias = False
            aliases = SKILL_ALIASES.get(req_lower, []) or SKILL_ALIASES.get(req.strip().lower(), [])
            for alias in aliases:
                if alias in cand_skills_lower or any(alias in cs for cs in cand_skills_lower):
                    matched_exact.append(req.strip())
                    matched_details.append({
                        "skill": req.strip(),
                        "matched_with": alias.title(),
                        "source": "Domain Synonym",
                        "display": f'{req.strip()} = "{alias.title()}" (Domain Synonym)',
                        "type": "alias"
                    })
                    total_score_sum += 1.0
                    found_alias = True
                    break
                elif resume_text_lower and re.search(r'\b' + re.escape(alias) + r'\b', resume_text_lower):
                    matched_exact.append(req.strip())
                    matched_details.append({
                        "skill": req.strip(),
                        "matched_with": alias.title(),
                        "source": "Resume Context Synonym",
                        "display": f'{req.strip()} = "{alias.title()}" (Resume Context Synonym)',
                        "type": "context"
                    })
                    total_score_sum += 1.0
                    found_alias = True
                    break
                    
            if found_alias:
                continue

            # Step E: OpenRouter BGE Semantic Embeddings Match with Cosine Similarity (Stored in JDEmbeddings table)
            if cand_embeddings and len(cand_embeddings) == len(cand_skills_clean):
                try:
                    req_embs = get_openrouter_embeddings([req_clean], source_type="jd")
                    if req_embs and req_embs[0]:
                        req_emb = req_embs[0]
                        best_sim = 0.0
                        best_idx = -1
                        for idx, c_emb in enumerate(cand_embeddings):
                            if c_emb:
                                sim = vector_cosine_similarity(req_emb, c_emb)
                                if sim > best_sim:
                                    best_sim = sim
                                    best_idx = idx
                        if best_sim >= 0.70 and best_idx != -1:
                            best_cand_skill = cand_skills_clean[best_idx]
                            matched_exact.append(req.strip())
                            matched_details.append({
                                "skill": req.strip(),
                                "matched_with": best_cand_skill,
                                "source": f"BGE Cosine: {best_sim:.2f}",
                                "display": f'{req.strip()} = "{best_cand_skill}" (BGE Cosine: {best_sim:.2f})',
                                "type": "embedding_similarity"
                            })
                            total_score_sum += 1.0
                            continue
                except Exception as e:
                    pass

            missing.append(req.strip())

        # Exact ratio matching: e.g. 4 matched out of 5 required = 4/5 = 80% (0.80)
        final_skill_score = total_score_sum / len(required_skills) if required_skills else 1.0
        return min(1.0, final_skill_score), matched_exact, [], missing, matched_details

    def calculate_experience_match(self, candidate_exp: float, required_exp: float) -> Tuple[float, str]:
        if required_exp <= 0:
            return 1.0, "No experience requirement (100% match)"
        
        if candidate_exp >= required_exp:
            return 1.0, f"Candidate meets or exceeds requirement (+{candidate_exp - required_exp:.1f} yrs)"
        elif candidate_exp > 0:
            ratio = candidate_exp / required_exp
            return min(1.0, max(0.0, ratio)), f"Candidate has ~{candidate_exp:.1f} yrs (Required: {required_exp:.0f} yrs)"
        return 0.0, f"No relevant work experience detected (Required: {required_exp:.0f} yrs)"

    def calculate_education_match(self, candidate_education: Any, required_education: str) -> Tuple[float, str, int, int]:
        if not required_education:
            return 1.0, "No specific education requirement (100% match)", 2, 2

        # Robust text extraction whether input is string, JSON string, or list of dicts
        edu_text = ""
        if isinstance(candidate_education, list):
            items = []
            for e in candidate_education:
                if isinstance(e, dict):
                    deg = e.get('course') or e.get('degree') or e.get('level_of_education') or ''
                    inst = e.get('institute') or e.get('institution') or ''
                    items.append(f"{deg} {inst}".strip())
                else:
                    items.append(str(e))
            edu_text = " ".join(items)
        elif isinstance(candidate_education, str):
            c_str = candidate_education.strip()
            if c_str.startswith('[') or c_str.startswith('{'):
                try:
                    parsed = json.loads(c_str)
                    if isinstance(parsed, list):
                        items = []
                        for e in parsed:
                            if isinstance(e, dict):
                                deg = e.get('course') or e.get('degree') or e.get('level_of_education') or ''
                                inst = e.get('institute') or e.get('institution') or ''
                                items.append(f"{deg} {inst}".strip())
                            else:
                                items.append(str(e))
                        edu_text = " ".join(items)
                    else:
                        edu_text = c_str
                except Exception:
                    edu_text = c_str
            else:
                edu_text = c_str
        else:
            edu_text = str(candidate_education or '')

        if not edu_text.strip():
            return 0.0, "No education qualifications listed in resume", 0, 2
        
        degree_hierarchy = [
            (4, "Doctorate / Ph.D", re.compile(r'\b(?:ph\.?d|doctorate|dr\b)\b', re.IGNORECASE)),
            (3, "Master's Degree", re.compile(r'\b(?:master(?:\s+of\s+[A-Za-z]+|\s+degree)?|m\.?sc|m\.?s\b|m\.?tech|m\.?e\b|mba|mca|m\.?com|post\s+graduate|pg\b|pg\s*diploma)\b', re.IGNORECASE)),
            (2, "Bachelor's Degree", re.compile(r'\b(?:bachelor(?:\s+of\s+[A-Za-z]+|\s+degree)?|b\.?sc|b\.?s\b|b\.?tech|b\.?e\b|bba|bca|b\.?com|under\s*graduate|ug\b|graduate|degree)\b', re.IGNORECASE)),
            (1, "Diploma / Associate", re.compile(r'\b(?:diploma|associate(?:\s+degree)?|polytechnic)\b', re.IGNORECASE)),
            (0, "High School / Secondary", re.compile(r'\b(?:hsc|sslc|higher\s+secondary|secondary\s+school|10th|12th|matriculation|schooling)\b', re.IGNORECASE))
        ]
        
        cand_rank = 0
        cand_label = "High School / Unspecified"
        for rk, label, pat in degree_hierarchy:
            if pat.search(edu_text):
                cand_rank = rk
                cand_label = label
                break
                
        req_rank = 2
        req_label = "Bachelor's Degree"
        for rk, label, pat in degree_hierarchy:
            if pat.search(required_education):
                req_rank = rk
                req_label = label
                break
                
        if cand_rank >= req_rank:
            score = 1.0
            insight = f"Candidate qualification ({cand_label}) meets or exceeds required {req_label}."
        elif cand_rank == req_rank - 1 and cand_rank > 0:
            score = 0.70
            insight = f"Candidate has {cand_label} (Required: {req_label})."
        elif cand_rank == 1 and req_rank == 2:
            score = 0.40
            insight = f"Candidate has {cand_label} (Required: {req_label})."
        else:
            score = 0.0
            insight = f"Candidate has only {cand_label} (HSC/SSLC), does not meet {req_label} requirement."
            
        return score, insight, cand_rank, req_rank

    def extract_keywords_comparison(self, resume_text: str, jd_text: str) -> Tuple[float, List[str], List[str], int]:
        stop_words = self.stop_words.union({
            'and', 'the', 'for', 'with', 'that', 'this', 'from', 'have', 'been', 'will', 'your',
            'about', 'more', 'into', 'some', 'than', 'them', 'these', 'were', 'what', 'when',
            'where', 'which', 'who', 'how', 'why', 'are', 'was', 'is', 'a', 'an', 'in', 'on',
            'at', 'to', 'by', 'of', 'or', 'but', 'not', 'can', 'all', 'any', 'their', 'there',
            'work', 'using', 'used', 'years', 'experience', 'candidate', 'role', 'team', 'skills',
            'requirements', 'job', 'description', 'must', 'ability', 'responsible', 'building',
            'strong', 'working', 'knowledge', 'plus', 'including', 'such', 'well', 'etc',
            'responsibilities', 'qualifications', 'required', 'preferred', 'good', 'ideal', 'looking',
            'opportunity', 'company', 'join', 'successful', 'seeking', 'environment', 'high', 'level'
        })
        
        jd_tokens = [w for w in re.findall(r'\b[a-zA-Z]{3,}\b', jd_text.lower()) if w not in stop_words and len(w) > 2]
        jd_freq = {}
        for t in jd_tokens:
            jd_freq[t] = jd_freq.get(t, 0) + 1
        top_jd_keywords = sorted(jd_freq.keys(), key=lambda k: jd_freq[k], reverse=True)[:10]
        
        resume_lower = resume_text.lower()
        matched = []
        missing = []
        for kw in top_jd_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', resume_lower):
                matched.append(kw)
            else:
                missing.append(kw)
                
        total = len(top_jd_keywords) if top_jd_keywords else 1
        score = len(matched) / total
        return min(1.0, score), matched, missing, total, top_jd_keywords

    def calculate_semantic_jd_match(self, resume_text: str, jd_text: str) -> Tuple[float, List[str], List[str], int, List[str]]:
        kw_score, matched_keywords, missing_keywords, total_kw_count, top_jd_keywords = self.extract_keywords_comparison(resume_text, jd_text)
        
        if resume_text and jd_text:
            try:
                cand_embs = get_openrouter_embeddings([resume_text[:2000]], source_type="candidate")
                jd_embs = get_openrouter_embeddings([jd_text[:2000]], source_type="jd")
                if cand_embs and jd_embs and cand_embs[0] and jd_embs[0]:
                    emb_sim = max(0.0, min(1.0, vector_cosine_similarity(cand_embs[0], jd_embs[0])))
                    # Blend keyword density (50%) and BGE sentence embedding cosine similarity (50%)
                    combined_score = (kw_score * 0.5) + (emb_sim * 0.5)
                    return round(combined_score, 3), matched_keywords, missing_keywords, total_kw_count, top_jd_keywords
            except Exception as e:
                print(f"[EmbeddingService] Semantic JD match error: {e}")
                
        return kw_score, matched_keywords, missing_keywords, total_kw_count, top_jd_keywords

    def score_candidate(self, candidate_data: dict, role_data: dict, jd_text: str, custom_weights: dict = None) -> dict:
        required_skills = role_data.get('required_skills', [])
        candidate_skills = candidate_data.get('parsed_skills', [])
        resume_text = candidate_data.get('resume_text', '')

        # Active weights (from custom_weights parameter, persisted JSON settings, or defaults)
        active_weights = custom_weights or get_scoring_weights()
        w_skill = float(active_weights.get('skills', 40.0))
        w_exp = float(active_weights.get('experience', 30.0))
        w_edu = float(active_weights.get('education', 15.0))
        w_sem = float(active_weights.get('semantic', 15.0))
        w_total = (w_skill + w_exp + w_edu + w_sem) or 100.0
        
        # 1. PILLAR 1: Keyword Semantic Skills Match
        skill_score, matched_exact, matched_semantic, missing_skills, matched_details = self.calculate_keyword_semantic_skills_match(
            candidate_skills, required_skills, resume_text
        )
        
        # 2. PILLAR 2: Experience Match
        cand_exp = float(candidate_data.get('years_experience', 0.0) or 0.0)
        req_exp = float(role_data.get('min_experience', 0) or 0)
        exp_score, exp_insight = self.calculate_experience_match(cand_exp, req_exp)
        
        # 3. PILLAR 3: Education Match
        cand_edu = candidate_data.get('education', '')
        req_edu = role_data.get('education_requirements', '')
        edu_score, edu_insight, cand_rank, req_rank = self.calculate_education_match(cand_edu, req_edu)
        
        # 4. PILLAR 4: Keyword & Neural Embedding Semantic Match
        kw_score, matched_keywords, missing_keywords, total_kw_count, top_jd_keywords = self.calculate_semantic_jd_match(resume_text, jd_text)
        
        # Exact Custom Dynamic Weights Formula: (w_skill% + w_exp% + w_edu% + w_sem% = 100%)
        overall_score = (
            skill_score * (w_skill / w_total) +
            exp_score * (w_exp / w_total) +
            edu_score * (w_edu / w_total) +
            kw_score * (w_sem / w_total)
        ) * 100
        
        overall_score = round(overall_score, 1)
        skill_pct = round(skill_score * 100, 1)
        exp_pct = round(exp_score * 100, 1)
        edu_pct = round(edu_score * 100, 1)
        kw_pct = round(kw_score * 100, 1)
        
        # Recommendation
        if overall_score >= 80:
            recommendation = "Strong Match"
        elif overall_score >= 60:
            recommendation = "Consider"
        else:
            recommendation = "Not Recommended"
            
        # Actionable recommendations
        actionable_recs = []
        if missing_skills:
            actionable_recs.append(f"[1] Add missing required skills: {', '.join(missing_skills[:4])}.")
        else:
            actionable_recs.append(f"[1] Skills criteria fully satisfied ({len(required_skills)}/{len(required_skills)} matched).")
            
        if cand_exp < req_exp:
            actionable_recs.append(f"[2] Candidate has ~{cand_exp:.1f} yrs experience; role requires {req_exp:.0f} yrs.")
        else:
            actionable_recs.append(f"[2] Experience tenure meets role requirement ({cand_exp:.1f} yrs vs {req_exp:.0f} yrs).")
            
        if missing_keywords:
            actionable_recs.append(f"[3] Incorporate missing domain keywords from JD: {', '.join(missing_keywords[:5])}.")
        else:
            actionable_recs.append(f"[3] Keyword density strongly aligns with target job description.")
            
        # Summary description
        if overall_score >= 80:
            summary_desc = "Strong candidate profile with high competency match across technical skills, experience tenure, and domain keywords."
        elif overall_score >= 60:
            summary_desc = "Good candidate potential with partial qualification alignment and minor experience or keyword gaps."
        else:
            summary_desc = "Significant gaps in required skills, experience tenure, or target keywords."

        # Rank names
        rank_names = {
            4: "Doctorate / Ph.D (Rank 4)",
            3: "Master's Degree (Rank 3)",
            2: "Bachelor's Degree (Rank 2)",
            1: "Associate / Diploma / School (Rank 1)"
        }

        matched_weight = len(matched_exact) * 1.0
        total_weight = len(required_skills) * 1.0 if required_skills else 1.0

        # Dynamic Formula String
        w_sk_factor = w_skill / w_total
        w_ex_factor = w_exp / w_total
        w_ed_factor = w_edu / w_total
        w_se_factor = w_sem / w_total
        formula_str = f"Formula: ({w_sk_factor:.2f} * {skill_pct}) + ({w_ex_factor:.2f} * {exp_pct}) + ({w_ed_factor:.2f} * {edu_pct}) + ({w_se_factor:.2f} * {kw_pct}) = {overall_score}%"

        return {
            'overall_score': overall_score,
            'skill_match': skill_pct,
            'experience_match': exp_pct,
            'education_match': edu_pct,
            'semantic_match': kw_pct,
            'matched_skills': matched_exact,
            'matched_skills_details': matched_details,
            'missing_skills': missing_skills,
            'top_jd_keywords': top_jd_keywords,
            'matched_keywords': matched_keywords,
            'missing_keywords': missing_keywords,
            'exp_insight': exp_insight,
            'edu_insight': edu_insight,
            'recommendation': recommendation,
            'summary_desc': summary_desc,
            'actionable_recs': actionable_recs,
            'formula_str': formula_str,
            'weights': {
                'skills': round(w_skill, 1),
                'experience': round(w_exp, 1),
                'education': round(w_edu, 1),
                'semantic': round(w_sem, 1)
            },
            'telemetry': {
                'pillar1': {
                    'title': f"SKILLS MATCHING (Weight: {w_skill:.0f}%)",
                    'score': skill_pct,
                    'extracted_skills': candidate_skills,
                    'required_skills': [{'name': s, 'weight': 1} for s in required_skills],
                    'matched_details': matched_details,
                    'missing_skills': missing_skills,
                    'calc_str': f"Calculation: ({matched_weight:.1f} matched weight / {total_weight:.1f} total weight) * 100 = {skill_pct}%"
                },
                'pillar2': {
                    'title': f"EXPERIENCE MATCHING (Weight: {w_exp:.0f}%)",
                    'score': exp_pct,
                    'candidate_years': cand_exp,
                    'required_years': req_exp,
                    'requirement_met': cand_exp >= req_exp,
                    'calc_str': f"Calculation: min(100, ({cand_exp:.1f} candidate years / {req_exp:.0f} required years) * 100) = {exp_pct}%" if req_exp > 0 else "Calculation: 100% (No experience requirement)"
                },
                'pillar3': {
                    'title': f"EDUCATION MATCHING (Weight: {w_edu:.0f}%)",
                    'score': edu_pct,
                    'candidate_rank_name': rank_names.get(cand_rank, f"Rank {cand_rank}"),
                    'required_rank_name': rank_names.get(req_rank, f"Rank {req_rank}"),
                    'jd_requirement': req_edu or "Bachelor in Computer Science / Technical Field",
                    'calc_str': f"Calculation: Candidate Rank {cand_rank} >= Required Rank {req_rank} -> {edu_pct}% match" if cand_rank >= req_rank else f"Calculation: Candidate Rank {cand_rank} < Required Rank {req_rank} -> {edu_pct}% match"
                },
                'pillar4': {
                    'title': f"SEMANTIC & DOMAIN KEYWORDS MATCHING (Weight: {w_sem:.0f}%)",
                    'score': kw_pct,
                    'top_jd_keywords': top_jd_keywords,
                    'matched_keywords': matched_keywords,
                    'missing_keywords': missing_keywords,
                    'total_keywords': total_kw_count,
                    'calc_str': f"Calculation: ({len(matched_keywords)} matched / {total_kw_count} target JD keywords) + BGE Semantic Embedding Cosine Alignment = {kw_pct}%"
                }
            }
        }

scoring_engine = ScoringEngine()