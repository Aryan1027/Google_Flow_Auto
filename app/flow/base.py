from abc import ABC, abstractmethod
from typing import Optional


class FlowAuthenticationError(Exception):
    """Raised when user authentication is required to access Google Flow."""
    pass


class FlowGenerationError(Exception):
    """Raised when generation fails or encounters rate limits/quota exhaustion."""
    pass


class FlowDownloadError(Exception):
    """Raised when video downloading fails or file validation fails."""
    pass


class BaseFlowBot(ABC):
    """Abstract interface for Google Flow browser automation."""

    @abstractmethod
    async def initialize(self) -> None:
        """Launch browser session and navigate to Google Flow."""
        pass

    @abstractmethod
    async def check_authenticated(self) -> bool:
        """Verify whether the user is logged into their Google account on Flow."""
        pass

    @abstractmethod
    async def submit_prompt(self, prompt: str) -> None:
        """Input prompt text and trigger generation."""
        pass

    @abstractmethod
    async def wait_for_generation_started(self, timeout: float = 30.0) -> bool:
        """Wait until generation has visibly begun."""
        pass

    @abstractmethod
    async def wait_for_generation_completed(self, timeout: float = 300.0, polling_interval: float = 2.0) -> str:
        """Poll until generation is complete and video is ready. Returns asset reference."""
        pass

    @abstractmethod
    async def download_generated_video(self, target_path: str, timeout: float = 120.0) -> str:
        """Download the latest generated video into target_path."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close browser resources cleanly."""
        pass
