-- ====================================================================
-- Enterprise ATS System - Complete MSSQL Database Schema
-- ====================================================================

USE master;
GO

-- 1. Create Database if not exists
IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = 'ATSSystem')
BEGIN
    CREATE DATABASE ATSSystem;
END
GO

USE ATSSystem;
GO

-- ====================================================================
-- 1. JOB ROLES TABLE
-- ====================================================================
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
GO

-- ====================================================================
-- 2. SKILLS TABLE
-- ====================================================================
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
GO

-- ====================================================================
-- 3. ROLE SKILLS MAPPING TABLE
-- ====================================================================
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'RoleSkills')
BEGIN
    CREATE TABLE RoleSkills (
        RoleSkillID INT IDENTITY(1,1) PRIMARY KEY,
        RoleID INT NOT NULL FOREIGN KEY REFERENCES JobRoles(RoleID) ON DELETE CASCADE,
        SkillID INT NOT NULL FOREIGN KEY REFERENCES Skills(SkillID) ON DELETE CASCADE,
        IsRequired BIT DEFAULT 1, -- 1 = Required, 0 = Preferred
        Weight DECIMAL(5,2) DEFAULT 1.0,
        CONSTRAINT UQ_RoleSkills UNIQUE(RoleID, SkillID)
    );
END
GO

-- ====================================================================
-- 4. JOB DESCRIPTIONS TABLE
-- ====================================================================
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
GO

-- ====================================================================
-- 5. CANDIDATES TABLE
-- ====================================================================
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'Candidates')
BEGIN
    CREATE TABLE Candidates (
        CandidateID INT IDENTITY(1,1) PRIMARY KEY,
        RoleID INT NOT NULL FOREIGN KEY REFERENCES JobRoles(RoleID),
        ResumeText NVARCHAR(MAX),
        ResumeFileName NVARCHAR(255),
        ResumeFileData VARBINARY(MAX),
        ParsedSkills NVARCHAR(MAX), -- JSON array of parsed skills
        YearsExperience DECIMAL(5,2) DEFAULT 0,
        Education NVARCHAR(MAX),
        Certifications NVARCHAR(MAX),
        TotalScore DECIMAL(5,2) DEFAULT 0,
        CreatedAt DATETIME DEFAULT GETDATE(),
        UpdatedAt DATETIME DEFAULT GETDATE()
    );
END
GO

-- ====================================================================
-- 6. SCORING RESULTS TABLE (Clean 12 Columns Schema)
-- ====================================================================
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
GO

-- ====================================================================
-- 7. JD EMBEDDINGS TABLE
-- ====================================================================
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
GO

-- ====================================================================
-- 8. CANDIDATE EMBEDDINGS TABLE
-- ====================================================================
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
GO

-- ====================================================================
-- 9. CANDIDATE EDITED DETAILS TABLE (User Manual Edits)
-- ====================================================================
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
GO

-- ====================================================================
-- PERFORMANCE INDEXES
-- ====================================================================
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Candidates_RoleID' AND object_id = OBJECT_ID('Candidates'))
    CREATE INDEX IX_Candidates_RoleID ON Candidates(RoleID);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ScoringResults_CandidateID' AND object_id = OBJECT_ID('ScoringResults'))
    CREATE INDEX IX_ScoringResults_CandidateID ON ScoringResults(CandidateID);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_RoleSkills_RoleID' AND object_id = OBJECT_ID('RoleSkills'))
    CREATE INDEX IX_RoleSkills_RoleID ON RoleSkills(RoleID);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_JDEmbeddings_TextKey' AND object_id = OBJECT_ID('JDEmbeddings'))
    CREATE INDEX IX_JDEmbeddings_TextKey ON JDEmbeddings(TextKey);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CandidateEmbeddings_TextKey' AND object_id = OBJECT_ID('CandidateEmbeddings'))
    CREATE INDEX IX_CandidateEmbeddings_TextKey ON CandidateEmbeddings(TextKey);
GO

-- ====================================================================
-- SEED INITIAL DATA (Optional / Auto-inserted if empty)
-- ====================================================================

-- 1. Insert Default Job Roles
IF NOT EXISTS (SELECT 1 FROM JobRoles WHERE RoleName = 'Data Scientist')
BEGIN
    INSERT INTO JobRoles (RoleName, Description, MinExperience, EducationRequirements)
    VALUES 
    ('Data Scientist', 'Build machine learning models and analyze data to drive business decisions', 3, 'Master in Data Science or related field'),
    ('Full Stack Developer', 'Develop web applications using modern technologies and frameworks', 4, 'Bachelor in Computer Science'),
    ('Product Manager', 'Lead product development, strategy, and cross-functional teams', 5, 'MBA or equivalent experience'),
    ('DevOps Engineer', 'Manage cloud infrastructure, CI/CD pipelines, and system reliability', 3, 'Bachelor in Computer Science or related'),
    ('UX/UI Designer', 'Design user-centered interfaces and improve user experience', 2, 'Bachelor in Design or related field'),
    ('Data Analyst', 'Analyze data and create visualizations to support business decisions', 2, 'Bachelor in Statistics or related field');
END
GO

-- 2. Insert Skills
IF NOT EXISTS (SELECT 1 FROM Skills WHERE SkillName = 'Python')
BEGIN
    INSERT INTO Skills (SkillName, Category, IsTechnical)
    VALUES 
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
    ('Adobe XD', 'Design', 1);
END
GO

-- 3. Map Skills to Roles
IF NOT EXISTS (SELECT 1 FROM RoleSkills)
BEGIN
    DECLARE @DS_ID INT = (SELECT RoleID FROM JobRoles WHERE RoleName = 'Data Scientist');
    DECLARE @FS_ID INT = (SELECT RoleID FROM JobRoles WHERE RoleName = 'Full Stack Developer');
    DECLARE @PM_ID INT = (SELECT RoleID FROM JobRoles WHERE RoleName = 'Product Manager');
    DECLARE @DO_ID INT = (SELECT RoleID FROM JobRoles WHERE RoleName = 'DevOps Engineer');
    DECLARE @UX_ID INT = (SELECT RoleID FROM JobRoles WHERE RoleName = 'UX/UI Designer');
    DECLARE @DA_ID INT = (SELECT RoleID FROM JobRoles WHERE RoleName = 'Data Analyst');

    -- Data Scientist
    INSERT INTO RoleSkills (RoleID, SkillID, IsRequired, Weight)
    SELECT @DS_ID, SkillID, 1, 1.0 FROM Skills WHERE SkillName IN ('Python', 'SQL', 'Machine Learning', 'Scikit-learn', 'Pandas', 'NumPy', 'Statistical Analysis', 'Data Visualization');
    INSERT INTO RoleSkills (RoleID, SkillID, IsRequired, Weight)
    SELECT @DS_ID, SkillID, 0, 0.5 FROM Skills WHERE SkillName IN ('TensorFlow', 'PyTorch', 'AWS', 'Docker');

    -- Full Stack Developer
    INSERT INTO RoleSkills (RoleID, SkillID, IsRequired, Weight)
    SELECT @FS_ID, SkillID, 1, 1.0 FROM Skills WHERE SkillName IN ('JavaScript', 'React', 'Python', 'SQL', 'HTML/CSS');
    INSERT INTO RoleSkills (RoleID, SkillID, IsRequired, Weight)
    SELECT @FS_ID, SkillID, 0, 0.6 FROM Skills WHERE SkillName IN ('TypeScript', 'Node.js', 'AWS', 'Docker', 'PostgreSQL');

    -- Product Manager
    INSERT INTO RoleSkills (RoleID, SkillID, IsRequired, Weight)
    SELECT @PM_ID, SkillID, 1, 1.0 FROM Skills WHERE SkillName IN ('Communication', 'Leadership', 'Project Management', 'Problem Solving', 'Teamwork');

    -- DevOps Engineer
    INSERT INTO RoleSkills (RoleID, SkillID, IsRequired, Weight)
    SELECT @DO_ID, SkillID, 1, 1.0 FROM Skills WHERE SkillName IN ('AWS', 'Docker', 'Kubernetes', 'Jenkins', 'Linux', 'Git');
    INSERT INTO RoleSkills (RoleID, SkillID, IsRequired, Weight)
    SELECT @DO_ID, SkillID, 0, 0.5 FROM Skills WHERE SkillName IN ('Terraform', 'Ansible', 'Azure', 'GCP');

    -- UX/UI Designer
    INSERT INTO RoleSkills (RoleID, SkillID, IsRequired, Weight)
    SELECT @UX_ID, SkillID, 1, 1.0 FROM Skills WHERE SkillName IN ('UI/UX Design', 'Figma', 'Communication', 'Problem Solving');

    -- Data Analyst
    INSERT INTO RoleSkills (RoleID, SkillID, IsRequired, Weight)
    SELECT @DA_ID, SkillID, 1, 1.0 FROM Skills WHERE SkillName IN ('SQL', 'Python', 'Data Visualization', 'Statistical Analysis', 'Pandas');
END
GO

-- 4. Insert Sample Job Descriptions
IF NOT EXISTS (SELECT 1 FROM JobDescriptions)
BEGIN
    INSERT INTO JobDescriptions (RoleID, Title, Description, Responsibilities, Benefits, Location, EmploymentType, SalaryRange)
    SELECT RoleID, 'Senior Data Scientist',
    'We are looking for an experienced Data Scientist to join our AI team. You will be responsible for building and deploying machine learning models to solve complex business problems.',
    'Develop machine learning models for predictive analytics; Collaborate with cross-functional teams; Deploy models to production; Analyze large datasets; Present findings to stakeholders.',
    'Competitive salary, Health insurance, Remote work, Learning budget, Stock options',
    'Remote/New York', 'Full-time', '$120,000 - $180,000'
    FROM JobRoles WHERE RoleName = 'Data Scientist';

    INSERT INTO JobDescriptions (RoleID, Title, Description, Responsibilities, Benefits, Location, EmploymentType, SalaryRange)
    SELECT RoleID, 'Senior Full Stack Developer',
    'Join our engineering team to build scalable web applications using modern technologies. You will work on both frontend and backend development.',
    'Design and develop web applications; Write clean, maintainable code; Review code and mentor juniors; Optimize application performance; Collaborate with product team.',
    'Competitive salary, Health insurance, Flexible hours, Professional development, 401k matching',
    'San Francisco/Remote', 'Full-time', '$130,000 - $190,000'
    FROM JobRoles WHERE RoleName = 'Full Stack Developer';

    INSERT INTO JobDescriptions (RoleID, Title, Description, Responsibilities, Benefits, Location, EmploymentType, SalaryRange)
    SELECT RoleID, 'Product Manager',
    'Lead product strategy and development for our flagship SaaS product. Work with engineering, design, and business teams to deliver value to customers.',
    'Define product vision and roadmap; Gather and prioritize requirements; Coordinate with engineering teams; Analyze market trends; Drive product adoption.',
    'Competitive salary, Health insurance, Equity, Annual bonus, Wellness program',
    'New York/Remote', 'Full-time', '$140,000 - $200,000'
    FROM JobRoles WHERE RoleName = 'Product Manager';

    INSERT INTO JobDescriptions (RoleID, Title, Description, Responsibilities, Benefits, Location, EmploymentType, SalaryRange)
    SELECT RoleID, 'DevOps Engineer',
    'Manage and scale our cloud infrastructure, implement CI/CD pipelines, and ensure system reliability and security.',
    'Design and implement CI/CD pipelines; Manage AWS infrastructure; Implement monitoring and alerting; Ensure security compliance; Optimize system performance.',
    'Competitive salary, Health insurance, Remote work, Training budget, Gym membership',
    'Austin/Remote', 'Full-time', '$115,000 - $165,000'
    FROM JobRoles WHERE RoleName = 'DevOps Engineer';

    INSERT INTO JobDescriptions (RoleID, Title, Description, Responsibilities, Benefits, Location, EmploymentType, SalaryRange)
    SELECT RoleID, 'Senior UX/UI Designer',
    'Design user-centered interfaces for our enterprise products. Create beautiful, intuitive experiences that solve user problems.',
    'Conduct user research; Create wireframes and prototypes; Design high-fidelity interfaces; Collaborate with product and engineering; Maintain design systems.',
    'Competitive salary, Health insurance, Remote work, Creative budget, Learning opportunities',
    'Remote/Chicago', 'Full-time', '$100,000 - $150,000'
    FROM JobRoles WHERE RoleName = 'UX/UI Designer';

    INSERT INTO JobDescriptions (RoleID, Title, Description, Responsibilities, Benefits, Location, EmploymentType, SalaryRange)
    SELECT RoleID, 'Data Analyst',
    'Analyze business data and create actionable insights. Build dashboards and reports to support decision-making across the organization.',
    'Extract and analyze data; Create dashboards and reports; Present insights to stakeholders; Identify trends and patterns; Support business intelligence initiatives.',
    'Competitive salary, Health insurance, Remote work, Professional development, Stock options',
    'Remote/Austin', 'Full-time', '$85,000 - $125,000'
    FROM JobRoles WHERE RoleName = 'Data Analyst';
END
GO