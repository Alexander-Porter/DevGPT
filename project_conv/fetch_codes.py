'''
GitHub Code File
Attribute	Description
Type	Source type
URL	URL to the mentioned source
ObjectSha	Sha of the source
FileName	Filename of this code file
FilePath	Filepath to this code file
Author	Author who introduced this mention
Content	Content of this code file, which can be decoded by base64
RepoName	Name of the repository that contains this code file
RepoLanguage	Primary programming language of the repository that contains this code file NOTE: it can be null when this repository does not contain any code
CommitSha	Sha of the commit that introduced this mention
CommitMessage	Message of the commit that introduced this mention
AuthorAt	When the author added this mention
CommitAt	When the author committed this mention
ChatgptSharing	List of ChatGPT link mentions. Refer to the ChatgptSharing structure for details
'''
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
from dotenv import load_dotenv
import os

# 加载.env文件
load_dotenv()

# 从环境变量获取TOKEN
TOKEN = os.getenv('GITHUB_TOKEN')

# GitHub 个人访问令牌
TOKEN = ''

RATE_LIMIT = 5000  # 每小时最大请求次数
PERIOD = 3600  # 速率限制时间窗口（秒）
RPM_LIMIT = 400  # 每分钟最大请求次数
PER_PAGE = 100  # 每页搜索结果数
REPORT_INTERVAL = 5  # 状态报告间隔时间（秒）
SIZE_STEP = 50000  # 文件大小步长（字节）
MAX_SIZE = 384000  # 文件大小限制上限（字节）

# ==================== 全局变量 ====================
lock = threading.Lock()  # 用于多线程的全局锁
results = []  # 存储爬取结果
finished = 0  # 已完成任务计数

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

def fetch_most_languages(url):
    """
    获取最流行的编程语言
    """
    data = call_github_api(url)
    for language, bytes in data.items():
        return language

def get_commit_data(item):
    """
    获取提交信息
    """
    repo_url = item['repository']['url']
    try:
        ref= item['url'].split('ref=')[1]
    except:
        ref = 'main'
    commit_url = f"{repo_url}/commits/{ref}"
    return call_github_api(commit_url)

# 文件内容处理函数
def process_code_item(item, progress):
    """
    获取文件内容并执行正则匹配
    """
    try:
        file_url = item.get('url')
        file_data = call_github_api(file_url)
        file_res = []
        if file_data:
            file_content = base64.b64decode(file_data.get('content', '')).decode('utf-8')
            pattern = r"https:\/\/chat\.openai\.com\/share\/[a-zA-Z0-9-]{36}|https:\/\/chatgpt\.com\/share\/[a-zA-Z0-9-]{36}"
            matches = re.findall(pattern, file_content)
            commit_data = get_commit_data(item)
            if matches:
                # 构造结果
                result = {
                    'Type': "gh_code",
                    'URL': item.get('html_url'),
                    'ObjectSha': item.get('sha'),
                    'FileName': item.get('name'),
                    'FilePath': item.get('path'),
                    'Author': commit_data.get('commit', {}).get('author', {}).get('name'),
                    'Content': file_data.get('content', ''),
                    'RepoName': item.get('repository', {}).get('full_name'),
                    'RepoLanguage': fetch_most_languages(item.get('repository', {}).get('languages_url')),
                    'CommitSha': commit_data.get('sha'),
                    'CommitMessage': commit_data.get('commit', {}).get('message'),
                    'AuthorAt': commit_data.get('commit', {}).get('author', {}).get('date'),
                    'CommitAt': commit_data.get('commit', {}).get('committer', {}).get('date'),
                    'ChatgptSharing': [
                        {
                            'ChatgptLink': match,
                            'MatchedText': file_content[max(0, file_content.find(match) - 30): file_content.find(match) + 30] if file_content.find(match) != -1 else ''
                        } for match in matches
                    ]
                }
                file_res.append(result)
                with lock:
                    global finished
                    finished += 1
                    results.extend(file_res)
                    print(f"已完成处理文件: {item.get('name')}")
            else:
                print(f"文件中未找到匹配项: {item.get('name')}")
        else:
            print(f"获取文件内容失败: {item.get('name')}")
    except Exception as e:
        import traceback
        print(f"处理文件内容时出错：{e}")
        print(traceback.format_exc())
    finally:
        progress.update(1)  # 更新进度条


# 搜索函数
def search_github_code(query, output_file='results.json', max_workers=3,max_pages=1):
    progress = tqdm(total=0, desc="Processing Files")  # 初始化进度条

    # 使用 ThreadPoolExecutor 管理多线程
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {}

        for size_start in range(0, MAX_SIZE, SIZE_STEP):
            size_end = size_start + SIZE_STEP
            size_query = f"size:{size_start}..{size_end}"
            full_query = f"{query} {size_query}"

            page = 1

            while page <= max_pages:
                url = f'https://api.github.com/search/code?q={full_query}&per_page={PER_PAGE}&page={page}'

                response = requests.get(url, auth=HTTPBasicAuth('username', TOKEN))

                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    progress.total += len(items)

                    for item in items:
                        future = executor.submit(process_code_item, item, progress)
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

        for future in as_completed(future_to_item):
            try:
                future.result(timeout=40000)  # 设置超时时间
            except Exception as e:
                print(f"子线程处理失败: {e}")

    with open(output_file, 'w') as f:
        for item in results:
            f.write(json.dumps(item) + '\n')
    progress.close()

# 示例调用
if __name__ == '__main__':
    date=time.strftime("%Y-%m-%d", time.localtime())
    search_query1 = 'https://chat.openai.com/share/'  # 替换为你的搜索关键词
    search_github_code(search_query1, output_file=f'{date}-code-openai_com.jsonl', max_workers=30, max_pages=1)
    search_query2 = 'https://chatgpt.com/share/'  # 替换为你的搜索关键词
    search_github_code(search_query2, output_file=f'{date}-code-chatgpt_com.jsonl', max_workers=30, max_pages=1)
