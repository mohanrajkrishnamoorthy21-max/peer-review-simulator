import json
import logging
import os
from typing import Any

import vertexai
from dotenv import load_dotenv
from google.adk.artifacts import GcsArtifactService, InMemoryArtifactService
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging
from vertexai.agent_engines.templates.adk import AdkApp

from app.agent import app as adk_app
from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

# Load environment variables from .env file at runtime
load_dotenv()


class FallbackLogger:
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def log_struct(self, info_dict: dict[str, Any], severity: str = "INFO") -> None:
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        level = level_map.get(severity, logging.INFO)
        self._logger.log(level, f"log_struct: {json.dumps(info_dict)}")

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.error(msg, *args, **kwargs)


class AgentEngineApp(AdkApp):
    def set_up(self) -> None:
        """Initialize the agent engine app with logging and telemetry."""
        vertexai.init()
        setup_telemetry()
        super().set_up()
        logging.basicConfig(level=logging.INFO)
        try:
            logging_client = google_cloud_logging.Client()
            self.logger = logging_client.logger(__name__)
        except Exception:
            logging.warning("Could not initialize Google Cloud logging client. Falling back to standard logging.")
            self.logger = FallbackLogger(__name__)
        if gemini_location:
            os.environ["GOOGLE_CLOUD_LOCATION"] = gemini_location

    def register_feedback(self, feedback: dict[str, Any]) -> None:
        """Collect and log feedback."""
        feedback_obj = Feedback.model_validate(feedback)
        try:
            self.logger.log_struct(feedback_obj.model_dump(), severity="INFO")
        except Exception:
            logging.warning("Could not log to Google Cloud Logging. Falling back to standard logging.")
            fallback = FallbackLogger(__name__)
            fallback.log_struct(feedback_obj.model_dump(), severity="INFO")

    def register_operations(self) -> dict[str, list[str]]:
        """Registers the operations of the Agent."""
        operations = super().register_operations()
        operations[""] = [*operations.get("", []), "register_feedback"]
        return operations

    def clone(self) -> "AgentEngineApp":
        """Returns a clone of the Agent Runtime application."""
        return self


gemini_location = os.environ.get("GOOGLE_CLOUD_LOCATION")
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

# Initialize Vertex AI. If no project is set in the environment or credentials,
# use a dummy project ID to allow local initialization without Google Cloud credentials.
project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID") or "dummy-project"
vertexai.init(project=project_id, location=gemini_location)

agent_runtime = AgentEngineApp(
    app=adk_app,
    artifact_service_builder=lambda: (
        GcsArtifactService(bucket_name=logs_bucket_name)
        if logs_bucket_name
        else InMemoryArtifactService()
    ),
)

# Create FastAPI app instance for local serving (uvicorn)
app = get_fast_api_app(agents_dir="app", web=False)


