"""
DeepSeek API configuration.

This module loads configuration from environment variables for secure API key management.
"""

import os
from pathlib import Path
from typing import Optional


class DeepSeekConfig:
    """DeepSeek API configuration class."""

    # Default values
    BASE_URL: str = "https://api.deepseek.com"
    MODEL: str = "deepseek-chat"
    DEFAULT_TEMPERATURE: float = 0.3
    DEFAULT_MAX_TOKENS: int = 4000
    DEFAULT_MAX_RETRIES: int = 3
    DEFAULT_TIMEOUT: int = 120

    # Runtime values (loaded from environment)
    API_KEY: Optional[str] = None
    TEMPERATURE: float = DEFAULT_TEMPERATURE
    MAX_TOKENS: int = DEFAULT_MAX_TOKENS
    MAX_RETRIES: int = DEFAULT_MAX_RETRIES
    TIMEOUT: int = DEFAULT_TIMEOUT

    @classmethod
    def load_from_env(cls, env_file: Optional[Path] = None) -> None:
        """
        Load configuration from environment variables.

        Args:
            env_file: Optional path to .env file. If not provided, uses .env in current directory.
        """
        # Try to load from .env file if it exists
        if env_file is None:
            env_file = Path(__file__).parent / ".env"

        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        os.environ[key] = value

        # Required: Load API key
        cls.API_KEY = os.getenv("DEEPSEEK_API_KEY")

        # Optional: API configuration
        base_url = os.getenv("DEEPSEEK_BASE_URL")
        if base_url:
            cls.BASE_URL = base_url

        model = os.getenv("DEEPSEEK_MODEL")
        if model:
            cls.MODEL = model

        # Optional: Runtime parameters
        temperature = os.getenv("DEEPSEEK_TEMPERATURE")
        if temperature:
            try:
                cls.TEMPERATURE = float(temperature)
            except ValueError:
                pass  # Keep default if invalid

        max_tokens = os.getenv("DEEPSEEK_MAX_TOKENS")
        if max_tokens:
            try:
                cls.MAX_TOKENS = int(max_tokens)
            except ValueError:
                pass  # Keep default if invalid

        max_retries = os.getenv("DEEPSEEK_MAX_RETRIES")
        if max_retries:
            try:
                cls.MAX_RETRIES = int(max_retries)
            except ValueError:
                pass  # Keep default if invalid

        timeout = os.getenv("DEEPSEEK_TIMEOUT")
        if timeout:
            try:
                cls.TIMEOUT = int(timeout)
            except ValueError:
                pass  # Keep default if invalid

    @classmethod
    def validate(cls) -> None:
        """
        Validate that all required configuration is present.

        Raises:
            ValueError: If required configuration is missing.
        """
        if not cls.API_KEY:
            raise ValueError(
                "DEEPSEEK_API_KEY is not set. "
                "Please set it in your .env file or as an environment variable."
            )

        if not cls.BASE_URL:
            raise ValueError("DEEPSEEK_BASE_URL is not configured.")

        if not cls.MODEL:
            raise ValueError("DEEPSEEK_MODEL is not configured.")

    @classmethod
    def get_api_key(cls) -> str:
        """
        Get the API key, loading from environment if not already loaded.

        Returns:
            The API key.

        Raises:
            ValueError: If API key is not configured.
        """
        if cls.API_KEY is None:
            cls.load_from_env()

        if not cls.API_KEY:
            raise ValueError(
                "DEEPSEEK_API_KEY is not set. "
                "Please set it in your .env file or as an environment variable."
            )

        return cls.API_KEY
