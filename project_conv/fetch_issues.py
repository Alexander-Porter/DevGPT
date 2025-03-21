import datetime
from datetime import datetime as dt
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

# 全局锁，用于多线程访问共享数据
lock = threading.Lock()

# 结果存储列表
results = []
finished = 0

RATE_LIMIT = 5000  # 次
PERIOD = 3600  # 秒
START_DATE = dt(2022, 12, 1)  # 起始日期
STEP_MONTHS = 3  # 日期步长（月）
RPM_LIMIT = 400  # 次

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
            if wait_time > 0:
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
    repo_url = item["repository"]["url"]
    try:
        ref = item["url"].split("ref=")[1]
    except:
        ref = "main"
    commit_url = f"{repo_url}/commits/{ref}"
    return call_github_api(commit_url)


def process_content(item, progress):
    res = []

    repo_url = item.get("repository_url", "")
    repo_full_name = repo_url.split("repos/")[1]

    repo_language = fetch_most_languages(
        f"https://api.github.com/repos/{repo_full_name}/languages"
    )
    issues_data = call_github_api(item.get("url"))
    comments_data = call_github_api(item.get("comments_url"))
    pattern = r"https:\/\/chat\.openai\.com\/share\/[a-zA-Z0-9-]{36}|https:\/\/chatgpt\.com\/share\/[a-zA-Z0-9-]{36}"

    chatgpt_sharing = []

    # 处理 issue body
    if issues_data.get("body", ""):
        matches = re.findall(pattern, issues_data.get("body", ""))
        for match in matches:
            chatgpt_sharing.append({
                "ChatgptLink": match,
                "MentionedProperty": "body",
                "MentionedBy": issues_data.get("user", {}).get("login", ""),
                "MentionedText": issues_data.get("body", "")
            })

    # 处理 issue comments
    for comment in comments_data:
        if comment.get("body", ""):
            matches = re.findall(pattern, comment.get("body", ""))
            for match in matches:
                chatgpt_sharing.append({
                    "ChatgptLink": match,
                    "MentionedProperty": "comment",
                    "MentionedBy": comment.get("user", {}).get("login", ""),
                    "MentionedText": comment.get("body", "")
                })

    # 构造结果
    if chatgpt_sharing:
        myres = {
            "Type": "issue",
            "URL": item.get("html_url", ""),
            "RepoName": repo_full_name,
            "RepoLanguage": repo_language,
            "Title": issues_data.get("title", ""),
            "Body": issues_data.get("body", ""),
            "CreatedAt": issues_data.get("created_at", ""),
            "UpdatedAt": issues_data.get("updated_at", ""),
            "ClosedAt": issues_data.get("closed_at", ""),
            "State": issues_data.get("state", ""),
            "Author": issues_data.get("user", {}).get("login", ""),
            "ChatgptSharing": chatgpt_sharing
        }

        res.append(myres)

        with lock:
            global finished
            results.extend(res)


    progress.update(1)  # 更新进度条



# 搜索函数
def search_github_issues(
    query, output_file="results.json", max_workers=10,max_pages=1
):
    per_page = 100  # 每页结果数
    page = 1
    progress = tqdm(total=0, desc="Processing Files")  # 初始化进度条

    # 使用 ThreadPoolExecutor 管理多线程
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {}

        current_date = START_DATE

        while current_date < dt.now():
            next_date = current_date + datetime.timedelta(days=STEP_MONTHS * 30)  # 计算下一步日期
            date_range_query = f"updated:{current_date.strftime('%Y-%m-%d')}..{next_date.strftime('%Y-%m-%d')}"
            full_query = f"{query} {date_range_query}"

            page = 1
            while page <= max_pages:
                # 构建搜索 API URL
                headers = {"Accept": "application/vnd.github.text-match+json"}
                url = f"https://api.github.com/search/issues?q={full_query} is:issue&per_page={per_page}&page={page}"
                response = requests.get(url, auth=HTTPBasicAuth("username", TOKEN), headers=headers)

                # 检查响应状态码
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", [])
                    total_count = data.get("total_count", 0)
                    print(f"第 {page} 页 for{date_range_query}，共 {total_count} 个结果")
                    #debug 

                    progress.total += len(items)  # 更新进度条总量

                    if not items:
                        # 如果没有更多结果，退出循环
                        break

                    for item in items:
                        # 提交任务到线程池
                        future = executor.submit(process_content, item, progress)
                        future_to_item[future] = item

                    # 检查是否有下一页
                    if "next" in response.links:
                        page += 1
                    else:
                        break
                elif response.status_code == 403:
                    # 处理速率限制
                    reset_time = int(
                        response.headers.get("X-RateLimit-Reset", time.time() + 60)
                    )
                    wait_time = reset_time - int(time.time())
                    print(f"速率限制已达到，等待 {wait_time} 秒...")
                    time.sleep(wait_time)
                else:
                    print(f"请求失败，状态码: {response.status_code}")
                    print(response.text)
                    break
            current_date=next_date
            # 等待所有任务完成
            for future in as_completed(future_to_item):
                try:
                    future.result(timeout=30000)  # 设置超时时间
                except Exception as e:
                    print(f"子线程处理失败：{e}")
                    import traceback

                    traceback.print_exc()

    # 保存结果为 JSON 文件
    with open(output_file, "w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(f"爬取完成，结果已保存至 {output_file}")
    progress.close()


# 示例调用
if __name__ == "__main__":
    date = time.strftime("%Y-%m-%d", time.localtime())
    search_query1 = "https://chat.openai.com/share/"  # 替换为你的搜索关键词
    search_github_issues(
        search_query1,
        output_file=f"{date}-issues-openai_com.jsonl",
        max_workers=6,
        report_interval=5,
        max_pages=1,
    )
    search_query2 = "https://chatgpt.com/share/"  # 替换为你的搜索关键词
    search_github_issues(
        search_query2,
        output_file=f"{date}-issues-chatgpt_com.jsonl",
        max_workers=6,
        report_interval=5,
        max_pages=1,
    )
