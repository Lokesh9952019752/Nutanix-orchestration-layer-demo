from functools import lru_cache
from typing import Dict

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PrismEnvironmentConfig(BaseSettings):
    """Connection settings for one Prism Central environment."""

    key: str
    label: str
    base_url: AnyHttpUrl
    username: str
    password: str


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(extra="ignore")

    app_admin_username: str = Field(default="admin", alias="APP_ADMIN_USERNAME")
    app_admin_password: str = Field(default="admin", alias="APP_ADMIN_PASSWORD")
    session_secret: str = Field(default="local-demo-only-change-me", alias="SESSION_SECRET")
    prism_verify_ssl: bool = Field(default=True, alias="PRISM_VERIFY_SSL")

    prism_onprem_url: AnyHttpUrl = Field(
        default="https://onprem-prism-central.example.com", alias="PRISM_ONPREM_URL"
    )
    prism_onprem_username: str = Field(default="placeholder-user", alias="PRISM_ONPREM_USERNAME")
    prism_onprem_password: str = Field(default="placeholder-password", alias="PRISM_ONPREM_PASSWORD")

    prism_nc2_aws_url: AnyHttpUrl = Field(
        default="https://nc2-aws-prism-central.example.com", alias="PRISM_NC2_AWS_URL"
    )
    prism_nc2_aws_username: str = Field(default="placeholder-user", alias="PRISM_NC2_AWS_USERNAME")
    prism_nc2_aws_password: str = Field(default="placeholder-password", alias="PRISM_NC2_AWS_PASSWORD")

    @property
    def environments(self) -> Dict[str, PrismEnvironmentConfig]:
        return {
            "on_prem": PrismEnvironmentConfig(
                key="on_prem",
                label="On-Prem Prism Central",
                base_url=self.prism_onprem_url,
                username=self.prism_onprem_username,
                password=self.prism_onprem_password,
            ),
            "nc2_aws": PrismEnvironmentConfig(
                key="nc2_aws",
                label="NC2 AWS Prism Central",
                base_url=self.prism_nc2_aws_url,
                username=self.prism_nc2_aws_username,
                password=self.prism_nc2_aws_password,
            ),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
