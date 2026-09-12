from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EnvironmentKey = Literal["onprem", "nc2_aws"]


class PrismEnvironmentSettings(BaseSettings):
    """Connection details for one Prism Central environment."""

    key: EnvironmentKey
    label: str
    base_url: str
    username: str
    password: str
    verify_ssl: bool = True

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_admin_username: str = Field(default="admin", alias="APP_ADMIN_USERNAME")
    app_admin_password: str = Field(default="admin", alias="APP_ADMIN_PASSWORD")
    session_secret: str = Field(default="dev-session-secret-change-me", alias="SESSION_SECRET")
    session_cookie_name: str = Field(default="prism_demo_session", alias="SESSION_COOKIE_NAME")
    prism_verify_ssl: bool = Field(default=True, alias="PRISM_VERIFY_SSL")

    prism_onprem_url: str = Field(default="https://onprem-prism.example.com:9440", alias="PRISM_ONPREM_URL")
    prism_onprem_username: str = Field(default="prism-user", alias="PRISM_ONPREM_USERNAME")
    prism_onprem_password: str = Field(default="prism-password", alias="PRISM_ONPREM_PASSWORD")

    prism_nc2_aws_url: str = Field(default="https://nc2-aws-prism.example.com:9440", alias="PRISM_NC2_AWS_URL")
    prism_nc2_aws_username: str = Field(default="prism-user", alias="PRISM_NC2_AWS_USERNAME")
    prism_nc2_aws_password: str = Field(default="prism-password", alias="PRISM_NC2_AWS_PASSWORD")

    def configured_environments(self) -> list[PrismEnvironmentSettings]:
        return [
            PrismEnvironmentSettings(
                key="onprem",
                label="On-prem Prism Central",
                base_url=self.prism_onprem_url,
                username=self.prism_onprem_username,
                password=self.prism_onprem_password,
                verify_ssl=self.prism_verify_ssl,
            ),
            PrismEnvironmentSettings(
                key="nc2_aws",
                label="NC2 AWS Prism Central",
                base_url=self.prism_nc2_aws_url,
                username=self.prism_nc2_aws_username,
                password=self.prism_nc2_aws_password,
                verify_ssl=self.prism_verify_ssl,
            ),
        ]

    def environment_by_key(self, key: str) -> PrismEnvironmentSettings:
        for environment in self.configured_environments():
            if environment.key == key:
                return environment
        raise KeyError(f"Unknown Prism environment: {key}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
