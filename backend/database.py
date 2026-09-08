import pyodbc
from fastapi import HTTPException
from config import config
from typing import List, Dict, Any, Optional
from decimal import Decimal

class Database:
    # Simple connection pooling
    _connection_pool = []
    _max_pool_size = 10
    _first_connection = True
    
    @staticmethod
    def get_connection():
        try:
            # Check if we have an existing connection in the pool
            if Database._connection_pool:
                conn = Database._connection_pool.pop()
                try:
                    # Test if connection is still alive
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.close()
                    return conn
                except:
                    # Connection is dead, create new one
                    pass
            
            conn_str = config.get_db_connection_string()
            conn = pyodbc.connect(conn_str)
            
            # Only show connection message once
            if Database._first_connection:
                print("[DB] Connected successfully to SQL Server")
                Database._first_connection = False
            
            return conn
        except Exception as e:
            print(f"[DB] Connection failed: {e}")
            raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")
    
    @staticmethod
    def return_connection(conn):
        """Return connection to pool"""
        if conn and len(Database._connection_pool) < Database._max_pool_size:
            Database._connection_pool.append(conn)
        elif conn:
            conn.close()
    
    @staticmethod
    def execute_query(query: str, params: tuple = (), fetch_one: bool = False, return_identity: bool = False):
        conn = None
        cursor = None
        try:
            conn = Database.get_connection()
            cursor = conn.cursor()
            
            if 'OUTPUT' in query.upper() and return_identity:
                cursor.execute(query, params)
                result = cursor.fetchone()
                conn.commit()
                return result[0] if result else None
            
            cursor.execute(query, params)
            
            if query.strip().upper().startswith('SELECT'):
                if fetch_one:
                    result = cursor.fetchone()
                    return result
                else:
                    result = cursor.fetchall()
                    return result
            else:
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"[DB] Query error: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                Database.return_connection(conn)
    
    @staticmethod
    def get_last_insert_id():
        conn = None
        cursor = None
        try:
            conn = Database.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT @@IDENTITY AS ID")
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            print(f"[DB] Get ID error: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                Database.return_connection(conn)
    
    @staticmethod
    def init_database():
        """
        Automatically ensure database and all required ATS tables exist.
        Runs seamlessly on new PCs or existing environments without manual SQL steps.
        """
        # Step 1: Ensure ATSSystem database exists
        try:
            master_conn_str = config.get_db_connection_string(db_name="master")
            master_conn = pyodbc.connect(master_conn_str, autocommit=True)
            master_cursor = master_conn.cursor()
            master_cursor.execute(f"""
                IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = '{config.DB_NAME}')
                BEGIN
                    CREATE DATABASE [{config.DB_NAME}];
                END
            """)
            master_cursor.close()
            master_conn.close()
            print(f"[DB Init] Database [{config.DB_NAME}] verified/ready.")
        except Exception as e:
            print(f"[DB Init] Note on master db connection: {e}")

        # Step 2: Ensure all tables and clean schemas exist in ATSSystem
        try:
            conn = Database.get_connection()
            cursor = conn.cursor()

            # Clean up Users table and UserID foreign key if migrating from legacy schema
            try:
                cursor.execute("""
                    DECLARE @sql NVARCHAR(MAX) = N'';
                    SELECT @sql += N'ALTER TABLE ' + QUOTENAME(OBJECT_SCHEMA_NAME(parent_object_id))
                        + '.' + QUOTENAME(OBJECT_NAME(parent_object_id)) 
                        + ' DROP CONSTRAINT ' + QUOTENAME(name) + ';'
                    FROM sys.foreign_keys
                    WHERE referenced_object_id = OBJECT_ID('Users');
                    
                    IF @sql <> N''
                    BEGIN
                        EXEC sp_executesql @sql;
                    END
                """)
                cursor.execute("""
                    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Candidates_UserID' AND object_id = OBJECT_ID('Candidates'))
                    BEGIN
                        DROP INDEX IX_Candidates_UserID ON Candidates;
                    END
                """)
                cursor.execute("""
                    IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Candidates' AND COLUMN_NAME = 'UserID')
                    BEGIN
                        ALTER TABLE Candidates DROP COLUMN UserID;
                    END
                """)
                cursor.execute("""
                    IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'Users')
                    BEGIN
                        DROP TABLE Users;
                    END
                """)
            except Exception:
                pass

            # 1. JobRoles
            cursor.execute("""
                IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'JobRoles')
                BEGIN
                    CREATE TABLE JobRoles (
                        RoleID INT IDENTITY(1,1) PRIMARY KEY,
                        RoleName NVARCHAR(100) UNIQUE NOT NULL,
                        Description NVARCHAR(1000),
                        MinExperience INT DEFAULT 0,
                        EducationRequirements NVARCHAR(500),
                        CreatedAt DATETIME DEFAULT GETDATE(),
                        IsActive BIT DEFAULT 1
                    );
                END
            """)

            # 2. Skills
            cursor.execute("""
                IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'Skills')
                BEGIN
                    CREATE TABLE Skills (
                        SkillID INT IDENTITY(1,1) PRIMARY KEY,
                        SkillName NVARCHAR(100) UNIQUE NOT NULL,
                        Category NVARCHAR(50),
                        IsTechnical BIT DEFAULT 1,
                        CreatedAt DATETIME DEFAULT GETDATE()
                    );
                END
            """)

            # 3. RoleSkills
            cursor.execute("""
                IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'RoleSkills')
                BEGIN
                    CREATE TABLE RoleSkills (
                        RoleSkillID INT IDENTITY(1,1) PRIMARY KEY,
                        RoleID INT NOT NULL FOREIGN KEY REFERENCES JobRoles(RoleID) ON DELETE CASCADE,
                        SkillID INT NOT NULL FOREIGN KEY REFERENCES Skills(SkillID) ON DELETE CASCADE,
                        IsRequired BIT DEFAULT 1,
                        Weight DECIMAL(5,2) DEFAULT 1.0,
                        CONSTRAINT UQ_RoleSkills UNIQUE(RoleID, SkillID)
                    );
                END
            """)

            # 4. JobDescriptions
            cursor.execute("""
                IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'JobDescriptions')
                BEGIN
                    CREATE TABLE JobDescriptions (
                        JDID INT IDENTITY(1,1) PRIMARY KEY,
                        RoleID INT NOT NULL FOREIGN KEY REFERENCES JobRoles(RoleID) ON DELETE CASCADE,
                        Title NVARCHAR(200),
                        Description NVARCHAR(MAX),
                        Responsibilities NVARCHAR(MAX),
                        Benefits NVARCHAR(MAX),
                        Location NVARCHAR(200),
                        EmploymentType NVARCHAR(50),
                        SalaryRange NVARCHAR(100),
                        CreatedAt DATETIME DEFAULT GETDATE(),
                        UpdatedAt DATETIME DEFAULT GETDATE()
                    );
                END
            """)

            # 5. Candidates
            cursor.execute("""
                IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'Candidates')
                BEGIN
                    CREATE TABLE Candidates (
                        CandidateID INT IDENTITY(1,1) PRIMARY KEY,
                        RoleID INT NOT NULL FOREIGN KEY REFERENCES JobRoles(RoleID),
                        ResumeText NVARCHAR(MAX),
                        ResumeFileName NVARCHAR(255),
                        ResumeFileData VARBINARY(MAX),
                        ParsedSkills NVARCHAR(MAX),
                        YearsExperience DECIMAL(5,2) DEFAULT 0,
                        Education NVARCHAR(MAX),
                        Certifications NVARCHAR(MAX),
                        TotalScore DECIMAL(5,2) DEFAULT 0,
                        CreatedAt DATETIME DEFAULT GETDATE(),
                        UpdatedAt DATETIME DEFAULT GETDATE()
                    );
                END
            """)

            # 7. ScoringResults
            cursor.execute("""
                IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'ScoringResults')
                BEGIN
                    CREATE TABLE ScoringResults (
                        ScoreID INT IDENTITY(1,1) PRIMARY KEY,
                        CandidateID INT NOT NULL FOREIGN KEY REFERENCES Candidates(CandidateID) ON DELETE CASCADE,
                        RoleID INT NOT NULL FOREIGN KEY REFERENCES JobRoles(RoleID),
                        SkillMatchScore DECIMAL(5,2) DEFAULT 0,
                        ExperienceMatchScore DECIMAL(5,2) DEFAULT 0,
                        EducationMatchScore DECIMAL(5,2) DEFAULT 0,
                        SemanticMatchScore DECIMAL(5,2) DEFAULT 0,
                        OverallScore DECIMAL(5,2) DEFAULT 0,
                        Strengths NVARCHAR(MAX),
                        Gaps NVARCHAR(MAX),
                        Recommendation NVARCHAR(50),
                        ScoreDate DATETIME DEFAULT GETDATE()
                    );
                END
            """)

            # Clean any legacy unwanted columns from ScoringResults if present
            for col in ['PreferredSkillsScore', 'CertificationsScore', 'Layer1KeywordMatch', 'Layer2SemanticMatch', 'Layer3StructuralScore', 'StructuralIssues']:
                try:
                    cursor.execute(f"""
                        IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'ScoringResults' AND COLUMN_NAME = '{col}')
                        BEGIN
                            ALTER TABLE ScoringResults DROP COLUMN [{col}];
                        END
                    """)
                except Exception:
                    pass

            # 8. JDEmbeddings
            cursor.execute("""
                IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'JDEmbeddings')
                BEGIN
                    CREATE TABLE JDEmbeddings (
                        EmbeddingID INT IDENTITY(1,1) PRIMARY KEY,
                        RoleID INT NULL,
                        SourceType NVARCHAR(50) DEFAULT 'JD_ITEM',
                        TextKey NVARCHAR(500) NOT NULL UNIQUE,
                        EmbeddingVector NVARCHAR(MAX) NOT NULL,
                        ModelName NVARCHAR(100) DEFAULT 'baai/bge-base-en-v1.5',
                        CreatedAt DATETIME DEFAULT GETDATE()
                    );
                END
            """)

            # 9. CandidateEmbeddings
            cursor.execute("""
                IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'CandidateEmbeddings')
                BEGIN
                    CREATE TABLE CandidateEmbeddings (
                        EmbeddingID INT IDENTITY(1,1) PRIMARY KEY,
                        CandidateID INT NULL,
                        SourceType NVARCHAR(50) DEFAULT 'CANDIDATE_ITEM',
                        TextKey NVARCHAR(500) NOT NULL UNIQUE,
                        EmbeddingVector NVARCHAR(MAX) NOT NULL,
                        ModelName NVARCHAR(100) DEFAULT 'baai/bge-base-en-v1.5',
                        CreatedAt DATETIME DEFAULT GETDATE()
                    );
                END
            """)

            # 10. CandidateEditedDetails
            cursor.execute("""
                IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'CandidateEditedDetails')
                BEGIN
                    CREATE TABLE CandidateEditedDetails (
                        EditID INT IDENTITY(1,1) PRIMARY KEY,
                        CandidateID INT NOT NULL UNIQUE FOREIGN KEY REFERENCES Candidates(CandidateID) ON DELETE CASCADE,
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
            conn.commit()

            # Step 3: Insert default seed data if database is empty
            cursor.execute("SELECT COUNT(*) FROM JobRoles")
            role_count = cursor.fetchone()[0]
            if role_count == 0:
                print("[DB Init] Seeding initial JobRoles, Skills, RoleSkills, and JobDescriptions...")

                # Insert Roles
                roles_data = [
                    ('Data Scientist', 'Build machine learning models and analyze data to drive business decisions', 3, 'Master in Data Science or related field'),
                    ('Full Stack Developer', 'Develop web applications using modern technologies and frameworks', 4, 'Bachelor in Computer Science'),
                    ('Product Manager', 'Lead product development, strategy, and cross-functional teams', 5, 'MBA or equivalent experience'),
                    ('DevOps Engineer', 'Manage cloud infrastructure, CI/CD pipelines, and system reliability', 3, 'Bachelor in Computer Science or related'),
                    ('UX/UI Designer', 'Design user-centered interfaces and improve user experience', 2, 'Bachelor in Design or related field'),
                    ('Data Analyst', 'Analyze data and create visualizations to support business decisions', 2, 'Bachelor in Statistics or related field')
                ]
                for r_name, r_desc, r_exp, r_edu in roles_data:
                    cursor.execute("""
                        INSERT INTO JobRoles (RoleName, Description, MinExperience, EducationRequirements)
                        VALUES (?, ?, ?, ?)
                    """, (r_name, r_desc, r_exp, r_edu))

                # Insert Skills
                skills_data = [
                    ('Python', 'Programming', 1), ('SQL', 'Database', 1), ('Machine Learning', 'AI/ML', 1),
                    ('TensorFlow', 'AI/ML', 1), ('PyTorch', 'AI/ML', 1), ('Scikit-learn', 'AI/ML', 1),
                    ('Pandas', 'Data Analysis', 1), ('NumPy', 'Data Analysis', 1), ('Statistical Analysis', 'Data Science', 1),
                    ('Data Visualization', 'Data Science', 1), ('React', 'Frontend', 1), ('Angular', 'Frontend', 1),
                    ('Vue.js', 'Frontend', 1), ('JavaScript', 'Programming', 1), ('TypeScript', 'Programming', 1),
                    ('Node.js', 'Backend', 1), ('Java', 'Programming', 1), ('C#', 'Programming', 1),
                    ('PHP', 'Programming', 1), ('HTML/CSS', 'Frontend', 1), ('AWS', 'Cloud', 1),
                    ('Azure', 'Cloud', 1), ('GCP', 'Cloud', 1), ('Docker', 'Containerization', 1),
                    ('Kubernetes', 'Containerization', 1), ('Jenkins', 'CI/CD', 1), ('Git', 'Version Control', 1),
                    ('Linux', 'OS', 1), ('Terraform', 'Infrastructure', 1), ('Ansible', 'Infrastructure', 1),
                    ('PostgreSQL', 'Database', 1), ('MongoDB', 'Database', 1), ('Redis', 'Database', 1),
                    ('MySQL', 'Database', 1), ('FastAPI', 'Backend', 1), ('Django', 'Backend', 1),
                    ('Flask', 'Backend', 1), ('Spring Boot', 'Backend', 1), ('Communication', 'Soft Skills', 0),
                    ('Leadership', 'Soft Skills', 0), ('Teamwork', 'Soft Skills', 0), ('Problem Solving', 'Soft Skills', 0),
                    ('Project Management', 'Soft Skills', 0), ('UI/UX Design', 'Design', 0), ('Figma', 'Design', 1),
                    ('Adobe XD', 'Design', 1)
                ]
                for s_name, s_cat, s_tech in skills_data:
                    cursor.execute("""
                        IF NOT EXISTS (SELECT 1 FROM Skills WHERE SkillName = ?)
                        BEGIN
                            INSERT INTO Skills (SkillName, Category, IsTechnical) VALUES (?, ?, ?);
                        END
                    """, (s_name, s_name, s_cat, s_tech))

                # RoleSkills mappings
                mappings = [
                    ('Data Scientist', [('Python', 1), ('SQL', 1), ('Machine Learning', 1), ('Scikit-learn', 1), ('Pandas', 1), ('NumPy', 1), ('Statistical Analysis', 1), ('Data Visualization', 1), ('TensorFlow', 0), ('PyTorch', 0), ('AWS', 0), ('Docker', 0)]),
                    ('Full Stack Developer', [('JavaScript', 1), ('React', 1), ('Python', 1), ('SQL', 1), ('HTML/CSS', 1), ('TypeScript', 0), ('Node.js', 0), ('AWS', 0), ('Docker', 0), ('PostgreSQL', 0)]),
                    ('Product Manager', [('Communication', 1), ('Leadership', 1), ('Project Management', 1), ('Problem Solving', 1), ('Teamwork', 1)]),
                    ('DevOps Engineer', [('AWS', 1), ('Docker', 1), ('Kubernetes', 1), ('Jenkins', 1), ('Linux', 1), ('Git', 1), ('Terraform', 0), ('Ansible', 0), ('Azure', 0), ('GCP', 0)]),
                    ('UX/UI Designer', [('UI/UX Design', 1), ('Figma', 1), ('Communication', 1), ('Problem Solving', 1), ('HTML/CSS', 0), ('JavaScript', 0), ('Adobe XD', 0)]),
                    ('Data Analyst', [('SQL', 1), ('Python', 1), ('Data Visualization', 1), ('Statistical Analysis', 1), ('Pandas', 1), ('Machine Learning', 0), ('AWS', 0)])
                ]
                for r_name, sk_list in mappings:
                    for sk_name, req in sk_list:
                        cursor.execute("""
                            INSERT INTO RoleSkills (RoleID, SkillID, IsRequired, Weight)
                            SELECT r.RoleID, s.SkillID, ?, ?
                            FROM JobRoles r, Skills s
                            WHERE r.RoleName = ? AND s.SkillName = ?
                        """, (req, 1.0 if req == 1 else 0.5, r_name, sk_name))

                # Job Descriptions
                jds = [
                    ('Data Scientist', 'Senior Data Scientist', 'We are looking for an experienced Data Scientist to join our AI team. You will be responsible for building and deploying machine learning models to solve complex business problems.', 'Develop machine learning models for predictive analytics; Collaborate with cross-functional teams; Deploy models to production; Analyze large datasets; Present findings to stakeholders.', 'Competitive salary, Health insurance, Remote work, Learning budget, Stock options', 'Remote/New York', 'Full-time', '$120,000 - $180,000'),
                    ('Full Stack Developer', 'Senior Full Stack Developer', 'Join our engineering team to build scalable web applications using modern technologies. You will work on both frontend and backend development.', 'Design and develop web applications; Write clean, maintainable code; Review code and mentor juniors; Optimize application performance; Collaborate with product team.', 'Competitive salary, Health insurance, Flexible hours, Professional development, 401k matching', 'San Francisco/Remote', 'Full-time', '$130,000 - $190,000'),
                    ('Product Manager', 'Product Manager', 'Lead product strategy and development for our flagship SaaS product. Work with engineering, design, and business teams to deliver value to customers.', 'Define product vision and roadmap; Gather and prioritize requirements; Coordinate with engineering teams; Analyze market trends; Drive product adoption.', 'Competitive salary, Health insurance, Equity, Annual bonus, Wellness program', 'New York/Remote', 'Full-time', '$140,000 - $200,000'),
                    ('DevOps Engineer', 'DevOps Engineer', 'Manage and scale our cloud infrastructure, implement CI/CD pipelines, and ensure system reliability and security.', 'Design and implement CI/CD pipelines; Manage AWS infrastructure; Implement monitoring and alerting; Ensure security compliance; Optimize system performance.', 'Competitive salary, Health insurance, Remote work, Training budget, Gym membership', 'Austin/Remote', 'Full-time', '$115,000 - $165,000'),
                    ('UX/UI Designer', 'Senior UX/UI Designer', 'Design user-centered interfaces for our enterprise products. Create beautiful, intuitive experiences that solve user problems.', 'Conduct user research; Create wireframes and prototypes; Design high-fidelity interfaces; Collaborate with product and engineering; Maintain design systems.', 'Competitive salary, Health insurance, Remote work, Creative budget, Learning opportunities', 'Remote/Chicago', 'Full-time', '$100,000 - $150,000'),
                    ('Data Analyst', 'Data Analyst', 'Analyze business data and create actionable insights. Build dashboards and reports to support decision-making across the organization.', 'Extract and analyze data; Create dashboards and reports; Present insights to stakeholders; Identify trends and patterns; Support business intelligence initiatives.', 'Competitive salary, Health insurance, Remote work, Professional development, Stock options', 'Remote/Austin', 'Full-time', '$85,000 - $125,000')
                ]
                for r_name, title, desc, resp, ben, loc, emp, sal in jds:
                    cursor.execute("""
                        INSERT INTO JobDescriptions (RoleID, Title, Description, Responsibilities, Benefits, Location, EmploymentType, SalaryRange)
                        SELECT RoleID, ?, ?, ?, ?, ?, ?, ?
                        FROM JobRoles WHERE RoleName = ?
                    """, (title, desc, resp, ben, loc, emp, sal, r_name))
                conn.commit()

            cursor.close()
            Database.return_connection(conn)
            print("[DB Init] All tables and schemas verified successfully.")
        except Exception as e:
            print(f"[DB Init] Table initialization error: {e}")

    @staticmethod
    def row_to_dict(row, columns):
        if not row:
            return None
        
        result = {}
        for i, col in enumerate(columns):
            val = row[i]
            if isinstance(val, Decimal):
                val = float(val)
            elif hasattr(val, 'isoformat'):
                val = str(val)
            result[col] = val
        return result
    
    @staticmethod
    def rows_to_dict(rows, columns):
        if not rows:
            return []
        return [Database.row_to_dict(row, columns) for row in rows]

db = Database()