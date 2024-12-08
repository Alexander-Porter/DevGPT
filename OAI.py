from token_count import TokenCounter
from ratelimit import limits, sleep_and_retry
from openai import OpenAI
import functools

class FlowControlOpenAIClient(OpenAI):
    def __init__(self, model="gpt-4", tpm_limit=90000, rpm_limit=300, **kwargs):
        super().__init__(**kwargs)
        self.token_counter = TokenCounter(tpm_limit=tpm_limit)
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        
        # 动态应用装饰器
        self.call_openai_api = self._apply_rate_limits(self.call_openai_api)

    def _apply_rate_limits(self, func):
        """动态应用速率限制装饰器"""
        decorated = sleep_and_retry(func)  # 先应用 sleep_and_retry
        decorated = limits(calls=self.rpm_limit, period=60)(decorated)  # 再应用 limits
        return decorated

    def call_openai_api(self, *args, **kwargs):
        messages = kwargs.get('messages', [])
        
        while not self.token_counter.can_make_request(messages):
            self.time.sleep(1)
        
        try:
            response = self.chat.completions.create(*args, **kwargs)
            self.token_counter.add_usage(response.usage.total_tokens)
            return response
        except Exception as e:
            print(f"OpenAI API call failed: {e}")
            raise
