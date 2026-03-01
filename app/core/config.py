from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agora API"
    env: str = "dev"
    database_url: str = "postgresql+psycopg://agora:agora@localhost:5432/agora"
    openai_api_key: str = ""
    openai_enabled: bool = False
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model_extract: str = "gpt-4.1-mini"
    openai_model_embed: str = "text-embedding-3-small"
    openai_model_transcribe: str = "whisper-1"
    extract_provider: str = "local"  # openai | local | heuristic
    embed_provider: str = "heuristic"  # openai | heuristic
    local_llm_base_url: str = "http://host.docker.internal:11434/v1"
    local_llm_model_extract: str = "llama3.1:8b-instruct"
    local_llm_api_key: str = ""
    transcribe_provider: str = "local"  # openai | local
    local_whisper_model: str = "small"
    local_whisper_device: str = "cpu"
    local_whisper_compute_type: str = "int8"
    local_whisper_beam_size: int = 1
    local_whisper_language: str = "es"
    token_ttl_hours: int = 168
    pricing_version: str = "2026-02"
    public_base_url: str = "http://localhost:8000"
    default_place_code: str = "alameda-santiago"
    default_place_name: str = "Alameda Santiago"
    default_place_city: str = "Santiago"
    default_place_country: str = "Chile"
    admin_api_key: str = ""
    twilio_validate_signature: bool = False
    twilio_auth_token: str = ""
    meta_validate_signature: bool = False
    meta_app_secret: str = ""
    meta_webhook_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    meta_graph_api_version: str = "v23.0"
    whatsapp_single_turn_mode: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
