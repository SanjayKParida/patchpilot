import os

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

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
        response = self.client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )
        return response.output_text