# app/core/config.py
from pydantic_settings import SettingsConfigDict
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Default values for your application settings
    app_name: str = "AI 3D Model Generator API"
    debug_mode: bool = True
    database_url: str
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

# Create a single global instance to import across your project
settings = Settings()