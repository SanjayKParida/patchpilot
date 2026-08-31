import logging
import os
import time

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class LLMService:

    def __init__(self):
        api_key = os.getenv(
            "OPEN_AI_KEY"
        )
        if not api_key:
            raise RuntimeError(
                "OPEN_AI_KEY is not set"
            )
        self.client = OpenAI(
            api_key=api_key
        )

    def ask(self, prompt):
        started = time.monotonic()
        logger.info("openai_request_start")
        try:
            response = self.client.responses.create(
                model="gpt-5-mini",
                input=prompt
            )
            logger.info(
                "openai_request_end elapsed_ms=%s",
                int((time.monotonic() - started) * 1000),
            )
            return response.output_text
        except Exception:
            logger.info(
                "openai_request_end elapsed_ms=%s error=1",
                int((time.monotonic() - started) * 1000),
            )
            raise