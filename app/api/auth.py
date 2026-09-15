"""API authentication helper (Section 64). Tokens come from the environment,
never from source control or config.yaml -- see ApiConfig.token_env_var.
"""
from __future__ import annotations

from app.config.loader import ApiConfig
from app.domain.exceptions import ConfigurationError


def require_token(api_config: ApiConfig) -> str:
    token = api_config.token
    if not token:
        raise ConfigurationError(
            f"API token not set. Export the {api_config.token_env_var} environment variable."
        )
    return token
