import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    GROQ_API_KEY: str    = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str      = os.getenv("GROQ_MODEL",      "llama-3.3-70b-versatile")
    GROQ_FAST_MODEL: str = os.getenv("GROQ_FAST_MODEL", "llama-3.1-8b-instant")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    VECTOR_DIM: int      = 384
    GITHUB_TOKEN: str    = os.getenv("GITHUB_TOKEN",    "")
    REPOS_DIR: str       = os.getenv("REPOS_DIR", os.path.join(os.path.expanduser("~"), "repo_lens_repos"))

settings = Settings()
