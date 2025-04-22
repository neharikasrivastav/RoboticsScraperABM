from assets import get_api_key
from litellm import completion
from litellm.exceptions import RateLimitError
import os

class MyLLMClient:
    def __init__(self):
        self.primary_model = "gpt-4o"
        self.fallback_model = "gpt-4o-mini"
        self.model = self.primary_model

    def send_prompt(self, prompt):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]

        # First try with primary
        try:
            os.environ["OPENAI_API_KEY"] = get_api_key(self.primary_model)
            response = completion(model=self.primary_model, messages=messages, seed=42)
        except RateLimitError:
            print(f"[⚠️] Rate limit hit for {self.primary_model}, retrying with {self.fallback_model}...")
            self.model = self.fallback_model
            os.environ["OPENAI_API_KEY"] = get_api_key(self.fallback_model)
            response = completion(model=self.fallback_model, messages=messages, seed=42)

        return response.choices[0].message.content.strip()
