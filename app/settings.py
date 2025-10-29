from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    rq_queue_name: str = "default"
    cmd_timeout: int = 5
    max_bytes: int = 200000

    class Config:
        env_file = ".env"

settings = Settings()

