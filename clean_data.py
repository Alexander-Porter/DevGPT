import json
import random
import re
from pygments import lex
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.token import Token
from pygments.lexers import (
    guess_lexer,
    ClassNotFound,
    get_lexer_by_name,
    _iter_lexerclasses,
)
from pygments.lexers._mapping import LEXERS
from pygments.modeline import get_filetype_from_buffer
from pygments.plugin import find_plugin_lexers
from pygments.util import ClassNotFound, guess_decode
from tqdm import tqdm
from openai import OpenAI
import tiktoken
from collections import deque
import time

# get api key from .env file
import os
import openai
from ratelimit import limits, sleep_and_retry

with open(".env", "r") as f:
    for line in f:
        key, value = line.strip().split("=")
        os.environ[key] = value

API_KEY = os.getenv("API_KEY")
LANGUAGES = ["python", "csharp", "javascript", "ruby", "go", "rust", "java", "php"]
client = OpenAI(api_key=API_KEY, base_url="https://api.siliconflow.cn/v1")
# Set up rate limiting



# Define a rate limit decorator


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

# 创建计数器实例
token_counter = TokenCounter()
available_modles=["Qwen/Qwen2.5-Coder-7B-Instruct","Qwen/Qwen2.5-7B-Instruct"]
@sleep_and_retry
@limits(calls=1000, period=60)
def call_openai_api(*args, **kwargs):
    messages = kwargs.get('messages', [])
    
    # 等待直到有足够的令牌配额
    while not token_counter.can_make_request(messages):
        time.sleep(1)
    
    try:
        response = client.chat.completions.create(*args, **kwargs)
        # 记录实际使用的令牌数
        token_counter.add_usage(response.usage.total_tokens)
        return response
    except Exception as e:
        print(f"OpenAI API call failed: {e}")
        raise


def is_snippet_has_code_block(snippet):
    #检查是否有至少2对括号
    policies=["{","}","[","]","(",")","<",">","="]
    hit=False
    for policy in policies:
        if snippet.count(policy)>1:
            hit=True
            break
    return hit


def is_test_code_block(code):
    keywords = ["assert", "expect(", "   expect(", "Errorf"]
    return any(keyword in code.lower() for keyword in keywords)





import concurrent.futures


def clean_data_multithreaded(data, max_workers=16, **kwargs):
    new_data = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {
            executor.submit(clean_data_item, item, **kwargs): item for item in data
        }
        for future in tqdm(
            concurrent.futures.as_completed(future_to_item),
            total=len(data),
            desc="Cleaning data",
        ):
            item = future_to_item[future]
            try:
                res = future.result()
                if res:
                    new_data.append(future.result())
            except Exception as exc:
                print(f"Item {item} generated an exception: {exc}")
    return new_data


def extract_text_and_code_blocks_with_llm(user_query):
    """调用自定义的api获取代码块"""
    PROMPT = """Your task is to extract **code blocks** from a plain text input.  
            You will receive a plain text input, which contains human language and programming code. And you need to extract code segments inside into distinct code blocks, where each block consists of several lines of code written in the same programming language.  
            Do not include file names in your output.  
            The input text may contain multiple code blocks. So, for your output, you must return a one-dimensional **valid** JSON array, where each element represents a single code block. The array should not contain nested structures. Use `\n` for line breaks within a code block instead of creating new array elements.  
            Do not use Markdown format. 
            Example:
            Input:
            ```
            This is a Python code block:
            def hello_world():
                print("Hello, World!")
            This is a JavaScript code block:
            function helloWorld() {
                console.log("Hello, World!");
            }
            ```
            Output:
            ["def hello_world():\n    print(\"Hello, World!\")", "function helloWorld() {\n    console.log(\"Hello, World!\")"]
            
            Explaination:
            The input contains two code blocks, one in Python and the other in JavaScript. The output is a JSON array containing two elements, each representing a code block.
            
            Tips:If no code is present, return an empty array:[]"""

    retries = 3
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=random.choice(available_modles),
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": f"'''{user_query}'''"},
                ],
                stream=False,
                response_format={"type": "json_object"},
            )

            # 检查响应结构
            if not response or not response.choices or len(response.choices) == 0:
                print("Error: No choices in response.")
                return []

            # 提取内容
            content = response.choices[0].message.content
            if not content:
                print("Error: No content in message.")
                return []

            # 尝试解析 JSON
            try:
                code_blocks = json.loads(content)
                print(code_blocks)
                return code_blocks
            except json.JSONDecodeError as e:
                print(f"JSON parsing error: {e}")
                print(f"Raw content: {content}")
                return []
        except Exception as e:
            print(f"Unhandled error: {e}")
            if attempt < retries - 1:
                continue
            else:
                return []


def clean_data_item(item):
    code_index = item.get("IndexInConv")
    item["src_code_blocks"] = []
    language = item.get("Language")
    content = item.get("Code")
    # 如果小于5行或者大于50行，直接跳过
    if content.count("\n") < 5 or content.count("\n") > 50 or language not in LANGUAGES:
        return None
    for i in range(code_index, -1, -1):
        print(i)
        conv_round = item.get("GptContent")[i]
        if "Prompt" in conv_round and conv_round.get("Prompt").count("\n") > 5:
            # code by user
            user_prompt = conv_round["Prompt"]
            user_code = extract_text_and_code_blocks_with_llm(user_prompt)
            for block in user_code:
                if not is_test_code_block(block):
                    item["src_code_blocks"].append(block)
        if i != code_index:
            # find generated code by gpt
            list_of_code = conv_round.get("ListOfCode")
            for code in list_of_code:
                if not is_test_code_block(code["Content"]):
                    item["src_code_blocks"].append(code["Content"])
    # item.pop("GptContent", None)
    for j in item["src_code_blocks"]:
        if j.count("\n") < 5 or j.count("\n") > 50:
            item["src_code_blocks"].remove(j)
    item["most_possible_src_code"] = (
        item["src_code_blocks"][0] if item["src_code_blocks"] else ""
    )
    return item
def clean_unicode(obj):
    """递归清理对象中的无效 Unicode 字符"""
    if isinstance(obj, dict):
        return {key: clean_unicode(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [clean_unicode(item) for item in obj]
    elif isinstance(obj, str):
        # 移除代理对字符
        return re.sub(r'[\ud800-\udfff]', '', obj)
    return obj

def safe_json_dump(obj, file_path):
    """安全地将对象写入 JSON 文件"""
    try:
        # 首先清理数据
        cleaned_obj = clean_unicode(obj)
        
        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_obj, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error during JSON dump: {e}")
        # 尝试使用更宽松的编码选项
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_obj, f, ensure_ascii=True, indent=2)

if __name__ == "__main__":
    with open("all_keyword_blocks_full.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    cleaned_data = clean_data_multithreaded(data, should_use_hint_language=False, max_workers=32)
    safe_json_dump(cleaned_data, "cleaned_data.json")
