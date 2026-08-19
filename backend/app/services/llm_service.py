# import os
# import openai from OpenAPI

# class LLMService:
#     def __init__(self):
#         self.client = openai(
#             api_key = os.getenv("OPEN_AI_KEY")
#         )
    
#     def ask(self, prompt):
#         response = self.client.responses.create(
#             model = "gpt-5-mini",
#             input = prompt
#         )
#         return response.output_text

