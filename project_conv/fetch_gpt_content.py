from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import asyncio
import datetime
import json
import random
import re
from bs4 import BeautifulSoup
import cloudscraper
import tiktoken

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.94 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36 Edge/17.17134",
    # 添加更多用户代理
]

@dataclass
class CodeBlock:
    replace_string: str
    type: Optional[str]
    content: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "replace_string": self.replace_string,
            "type": self.type,
            "content": self.content
        }

@dataclass
class Conversation:
    prompt: str
    answer: str
    list_of_code: List[CodeBlock]
    conv_index: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "answer": self.answer,
            "list_of_code": [code_block.to_dict() for code_block in self.list_of_code],
            "conv_index": self.conv_index
        }

@dataclass
class ChatGPTResponse:
    url: str
    mention: Dict
    status: int
    date_of_conversation: Optional[str] = None
    title: Optional[str] = None
    number_of_prompts: Optional[int] = None
    tokens_of_prompts: Optional[int] = None
    tokens_of_answers: Optional[int] = None
    model: Optional[str] = None
    conversations: List[Conversation] = None
    html_content: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "mention": self.mention,
            "status": self.status,
            "date_of_conversation": self.date_of_conversation,
            "title": self.title,
            "number_of_prompts": self.number_of_prompts,
            "tokens_of_prompts": self.tokens_of_prompts,
            "tokens_of_answers": self.tokens_of_answers,
            "model": self.model,
            "conversations": [conv.to_dict() for conv in self.conversations],
            "html_content": self.html_content
        }

def get_num_tokens_from_string(text: str, model: str = 'gpt-4') -> int:
    if model=="text-davinci-002-render-sha":
        model='gpt-3.5'
    return len(tiktoken.encoding_for_model(model).encode(text))

def fetch_page(url: str) -> Any:
    scraper = cloudscraper.create_scraper()
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    response = scraper.get(url, headers=headers)
    return response.status_code if response.status_code != 200 else response.text

def extract_code_blocks(answer: str) -> tuple[str, List[CodeBlock]]:
    code_blocks = []
    code_contents = re.findall(r'```[\s\S]*?```', answer, re.DOTALL)
    for index, code_content in enumerate(code_contents):
        code_type = code_content.split('\n')[0][3:] or None
        answer = answer.replace(code_content, f"[CODE_BLOCK_{index}]")
        content = '\n'.join(code_content.split('\n')[1:-1])
        code_blocks.append(CodeBlock(
            replace_string=f"[CODE_BLOCK_{index}]",
            type=code_type,
            content=content
        ))
    return answer, code_blocks

def process_conversation_data(values: List[Dict]) -> tuple[List[Conversation], List[str], int, Optional[str]]:
    conversations = []
    prompts = []
    answer_tokens = 0
    model = None
    turn = 0
    current_prompt = None
    current_answer = None
    
    for mapping in values:
        if 'message' not in mapping:
            continue
            
        message = mapping['message']
        if 'model_slug' in message.get('metadata', {}) and model is None:
            model = message['metadata']['model_slug']
            
        if message.get('content', {}).get('content_type') == 'code':
            continue
            
        role = message['author']['role']
        if role == 'user':
            if current_answer and current_prompt:
                turn += 1
                answer, code_blocks = extract_code_blocks(current_answer)
                conversations.append(Conversation(
                    prompt=current_prompt,
                    answer=answer,
                    list_of_code=code_blocks,
                    conv_index=turn
                ))
            current_prompt = message['content']['parts'][0]
            prompts.append(current_prompt)
            
        elif role == 'assistant' and 'parts' in message.get('content', {}):
            answer_text = message['content']['parts'][0]
            answer_tokens += get_num_tokens_from_string(answer_text, model or 'gpt-4')
            if current_answer:
                current_answer += '\n' + answer_text
            else:
                current_answer = answer_text

    # Handle last conversation
    if current_answer and current_prompt:
        turn += 1
        answer, code_blocks = extract_code_blocks(current_answer)
        conversations.append(Conversation(
            prompt=current_prompt,
            answer=answer,
            list_of_code=code_blocks,
            conv_index=turn
        ))

    return conversations, prompts, answer_tokens, model

async def obtain_from_chatgpt_sharing(url: str, mention: Dict) -> ChatGPTResponse:
    revised_url = url.replace('https://chat.openai.com/share/', 'https://chatgpt.com/share/')
    content = fetch_page(revised_url)
    
    if isinstance(content, int):
        return ChatGPTResponse(url=url, mention=mention, status=content)
        
    try:
        pattern = r"window\.__remixContext\s*=\s*({.*});__remixContext\.p"
        data = json.loads(re.search(pattern, content).group(1))
    except (json.JSONDecodeError, AttributeError):
        return ChatGPTResponse(url=url, mention=mention, status=404)

    soup = BeautifulSoup(content, "html.parser")
    server_response = data['state']['loaderData']['routes/share.$shareId.($action)']['serverResponse']['data']
    values = list(server_response['mapping'].values())
    values.reverse()
    
    conversations, prompts, answer_tokens, model = process_conversation_data(values)
    
    return ChatGPTResponse(
        url=url,
        mention=mention,
        status=200,
        date_of_conversation=datetime.datetime.fromtimestamp(server_response['create_time']).strftime('%d/%m/%Y, %H:%M:%S'),
        title=server_response['title'],
        number_of_prompts=len(prompts),
        tokens_of_prompts=sum(get_num_tokens_from_string(prompt) for prompt in prompts),
        tokens_of_answers=answer_tokens,
        model=model,
        conversations=conversations,
        html_content=str(soup)
    )

if __name__ == "__main__":
    print(asyncio.run(obtain_from_chatgpt_sharing(
        "https://chatgpt.com/share/677e74af-da44-800f-b3ad-ebc704aeb9aa",
        {}
    )))