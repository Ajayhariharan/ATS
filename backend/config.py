import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Database Configuration (SQL Server)
    DB_HOST: str = os.getenv("DB_HOST", "REXA")
    DB_NAME: str = os.getenv("DB_NAME", "ATSSystem")
    DB_DRIVER: str = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    DB_TRUST_CERTIFICATE: str = os.getenv("DB_TRUST_CERTIFICATE", "yes")
    DB_USE_WINDOWS_AUTH: bool = os.getenv("DB_USE_WINDOWS_AUTH", "true").lower() == "true"
    
    # OpenRouter Gemini Configuration (Exclusive LLM Provider)
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    OPENROUTER_URL: str = os.getenv("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
    
    # Semantic Scoring Embedding Model (Local NLP / SentenceTransformer)
    SEMANTIC_EMBEDDING_MODEL: str = os.getenv("SEMANTIC_EMBEDDING_MODEL", "nbk-ats-semantic-v1-en")
    
    # Server Configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8000))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    ALLOWED_ORIGINS: list = os.getenv(
        "ALLOWED_ORIGINS", 
        "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000"
    ).split(",")

    def get_db_connection_string(self, db_name: str = None) -> str:
        target_db = db_name if db_name is not None else self.DB_NAME
        driver = f"{{{self.DB_DRIVER}}}" if not self.DB_DRIVER.startswith("{") else self.DB_DRIVER
        if self.DB_USE_WINDOWS_AUTH:
            return f"DRIVER={driver};SERVER={self.DB_HOST};DATABASE={target_db};Trusted_Connection=yes;TrustServerCertificate={self.DB_TRUST_CERTIFICATE};"
        else:
            db_user = os.getenv("DB_USER", "sa")
            db_pass = os.getenv("DB_PASSWORD", "")
            return f"DRIVER={driver};SERVER={self.DB_HOST};DATABASE={target_db};UID={db_user};PWD={db_pass};TrustServerCertificate={self.DB_TRUST_CERTIFICATE};"

config = Config()