from collections import deque
import time
import tiktoken


class TokenCounter:
    def __init__(self, model="gpt-4", tpm_limit=90000):
        self.encoding = tiktoken.encoding_for_model(model)
        self.tpm_limit = tpm_limit
        self.token_usage = deque()  # [(timestamp, tokens), ...]
        self.window = 60  # 1分钟窗口
        
    def num_tokens_from_messages(self, messages):
        """计算消息列表的令牌数量"""
        num_tokens = 0
        for message in messages:
            num_tokens += 4  # 每条消息的开头令牌
            for key, value in message.items():
                num_tokens += len(self.encoding.encode(str(value)))
                if key == "name":  # 如果消息中包含name字段
                    num_tokens += -1  # role字段已经计入了name
        num_tokens += 2  # 对话的开头令牌
        return num_tokens

    def can_make_request(self, messages):
        """检查是否可以发送请求"""
        now = time.time()
        # 清理过期记录
        while self.token_usage and now - self.token_usage[0][0] >= self.window:
            self.token_usage.popleft()
            
        # 计算当前TPM
        current_tpm = sum(tokens for _, tokens in self.token_usage)
        estimated_tokens = self.num_tokens_from_messages(messages)
        if current_tpm + estimated_tokens > self.tpm_limit:
            return False
        else:
            self.token_usage.append((now, estimated_tokens))
            return True

    def add_usage(self, tokens):
        """记录令牌使用情况"""
        self.token_usage.append((time.time(), tokens))
