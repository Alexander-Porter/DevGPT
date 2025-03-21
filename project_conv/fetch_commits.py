import requests
from requests.auth import HTTPBasicAuth
import time
import base64
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from ratelimit import limits, sleep_and_retry
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

# 加载.env文件
load_dotenv()

# ==================== 常量定义 ====================
TOKEN = os.getenv('GITHUB_TOKEN')  # 从环境变量获取TOKEN
RATE_LIMIT = 5000  # 每小时最大请求次数
PERIOD = 3600  # 速率限制时间窗口（秒）
RPM_LIMIT = 400  # 每分钟最大请求次数
PER_PAGE = 100  # 每页搜索结果数,debug
REPORT_INTERVAL = 5  # 状态报告间隔时间（秒）
DEFAULT_REF = 'main'  # 默认分支
START_DATE = datetime(2022, 12, 1)  # 起始日期
STEP_MONTHS = 3  # 日期步长（月）

# ==================== 全局变量 ====================
lock = threading.Lock()  # 用于多线程的全局锁
results = []  # 存储爬取结果


# ==================== API 调用函数 ====================
@sleep_and_retry
@limits(calls=RATE_LIMIT, period=PERIOD)
def call_github_api(url):
    """
    调用 GitHub API，处理速率限制。
    """
    def _call_api(url):
        @sleep_and_retry
        @limits(calls=RPM_LIMIT, period=60)
        def _limited_call(url):
            return requests.get(url, auth=HTTPBasicAuth('username', TOKEN))

        return _limited_call(url)

    while True:
        response = _call_api(url)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403:
            reset_time = int(response.headers.get('X-RateLimit-Reset', time.time() + 60))
            wait_time = reset_time - int(time.time())
            print(f'!速率限制已达到，等待 {wait_time} 秒...')
            time.sleep(wait_time)
        else:
            print(f'请求失败，状态码: {response.status_code}')
            return None

# ==================== 辅助函数 ====================
def fetch_repo_language(languages_url):
    """
    获取仓库的主要编程语言。
    """
    data = call_github_api(languages_url)
    if data:
        return max(data.items(), key=lambda x: x[1])[0]
    return None

def parse_commit_data(item):
    """
    解析单条提交数据，提取关键信息。
    """
    repo = item.get('repository', {})
    commit = item.get('commit', {})
    commit_author = commit.get('author', {})
    languages_url = repo.get('languages_url', '')

    return {
        "Type": "commit",
        "URL": item.get('html_url', ''),
        "Author": commit_author.get('name', ''),
        "RepoName": repo.get('full_name', ''),
        "RepoLanguage": fetch_repo_language(languages_url) if languages_url else None,
        "Sha": item.get('sha', ''),
        "Message": commit.get('message', ''),
        "AuthorAt": commit_author.get('date', ''),
        "CommitAt": commit.get('committer', {}).get('date', ''),
        "ChatgptSharing": None
    }

def extract_chatgpt_links(message):
    """
    从提交信息中提取 ChatGPT 分享链接。
    """
    pattern = r"https:\/\/chat\.openai\.com\/share\/[a-zA-Z0-9-]{36}|https:\/\/chatgpt\.com\/share\/[a-zA-Z0-9-]{36}"
    return re.findall(pattern, message)

def save_results_to_file(output_file):
    """
    将结果保存到 JSON 文件。
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
    print(f'结果已保存至 {output_file}')

# ==================== 核心逻辑函数 ====================
def process_commit_item(item, progress):
    """
    处理单条提交记录并提取信息。
    """
    commit_data = parse_commit_data(item)
    chatgpt_links = extract_chatgpt_links(commit_data['Message'])
    if chatgpt_links:
        extracted_results = {
            **commit_data,
            "ChatgptSharing": [
                {
                    "ChatgptLink": link,
                    "MatchedText": commit_data.get('Message', '')
                } for link in chatgpt_links
            ]
        }

        with lock:
            results.append(extracted_results)


    progress.update(1)

def search_github_commits_with_date(query, output_file, max_workers=10,max_page=1000):
    """
    按时间范围搜索 GitHub 提交记录并处理结果。
    """
    progress = tqdm(total=0, desc="Processing Commits")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {}
        current_date = START_DATE

        while current_date < datetime.now():
            next_date = current_date + timedelta(days=STEP_MONTHS * 30)  # 计算下一步日期
            date_range_query = f"committer-date:{current_date.strftime('%Y-%m-%d')}..{next_date.strftime('%Y-%m-%d')}"
            full_query = f"{query} {date_range_query}"

            page = 1
            while page<=max_page:
                url = f'https://api.github.com/search/commits?q={full_query}&per_page={PER_PAGE}&page={page}'
                response = requests.get(url, auth=HTTPBasicAuth('username', TOKEN))

                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    progress.total += len(items)

                    for item in items:
                        future = executor.submit(process_commit_item, item, progress)
                        future_to_item[future] = item

                    if len(items) < PER_PAGE:
                        break  # 没有更多结果

                    page += 1
                elif response.status_code == 403:
                    reset_time = int(response.headers.get('X-RateLimit-Reset', time.time() + 60))
                    wait_time = reset_time - int(time.time())
                    print(f'速率限制已达到，等待 {wait_time} 秒...')
                    time.sleep(wait_time)
                else:
                    print(f'请求失败，状态码: {response.status_code}')
                    break

            current_date = next_date

        for future in as_completed(future_to_item):
            try:
                future.result(timeout=40000)
            except Exception as e:
                print(f"处理失败: {e}")

    save_results_to_file(output_file)
    progress.close()

# ==================== 入口函数 ====================
if __name__ == '__main__':
    date = time.strftime("%Y-%m-%d", time.localtime())

    # 搜索关键词
    search_query1 = 'https://chat.openai.com/share/'
    search_query2 = 'https://chatgpt.com/share/'

    # 调用搜索函数
    search_github_commits_with_date(search_query1, output_file=f'{date}-commits-openai_com.jsonl', max_workers=10,max_page=1)
    search_github_commits_with_date(search_query2, output_file=f'{date}-commits-chatgpt_com.jsonl', max_workers=10,max_page=1)
