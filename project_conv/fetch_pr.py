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

def process_pull_request(item, progress):
    """
    处理单个 Pull Request，包括注解和讨论，提取 ChatGPT 分享链接
    """
    res = []

    # 提取 Repo 信息
    repo_url = item.get("repository_url", "")
    repo_full_name = repo_url.split("repos/")[1]

    # 获取 Repo 主要语言
    repo_language = fetch_most_languages(
        f"https://api.github.com/repos/{repo_full_name}/languages"
    )

    # 获取 Pull Request 数据
    pr_data = call_github_api(item.get("pull_request")["url"])
    if not pr_data:
        return  # 请求失败直接返回

    # 获取 Pull Request 注解和讨论
    review_comments_url = pr_data.get("review_comments_url")
    comments_url = pr_data.get("comments_url")
    review_comments = call_github_api(review_comments_url) or []
    comments = call_github_api(comments_url) or []

    # 提取需要的字段
    pr_number = pr_data.get("number")
    commits_data = call_github_api(pr_data.get("commits_url")) or []
    changed_files_data = pr_data.get("changed_files", 0)

    pattern = r"https:\/\/chat\.openai\.com\/share\/[a-zA-Z0-9-]{36}|https:\/\/chatgpt\.com\/share\/[a-zA-Z0-9-]{36}"

    # 合并 ChatGPT 链接来源
    chatgpt_links = []

    # PR 主体链接
    body_links = re.findall(pattern, pr_data.get("body", "")) if pr_data.get("body") else []
    for link in body_links:
        chatgpt_links.append({
            "ChatgptLink": link,
            "MentionedProperty": "body",
            "MentionedAuthor": pr_data.get("user", {}).get("login", ""),
            "MentionedText": pr_data.get("body", ""),
            "MentionedPath": None,
            "MentionedIsAnswer": None,
            "MentionedUpvoteCount": None
        })

    # 注解和讨论链接
    for comment in review_comments + comments:
        body = comment.get("body", "")
        mentioned_links = re.findall(pattern, body)
        for link in mentioned_links:
            chatgpt_links.append({
                "ChatgptLink": link,
                "MentionedProperty": "review_comment" if comment in review_comments else "comment",
                "MentionedAuthor": comment.get("user", {}).get("login", ""),
                "MentionedText": body,
                "MentionedPath": comment.get("path", None),
                "MentionedIsAnswer": comment.get("is_answer", None),
                "MentionedUpvoteCount": comment.get("upvote_count", None)
            })

    # 去重处理
    chatgpt_links = [dict(t) for t in {tuple(d.items()) for d in chatgpt_links}]

    # 提取 Commit 信息
    commit_shas = [commit.get("sha") for commit in commits_data]
    additions = sum(commit.get("stats", {}).get("additions", 0) for commit in commits_data)
    deletions = sum(commit.get("stats", {}).get("deletions", 0) for commit in commits_data)

    # 构造结果
    if chatgpt_links:
        this_result = {
            "Type": "pull_request",
            "URL": pr_data.get("html_url", ""),
            "Author": pr_data.get("user", {}).get("login", ""),
            "RepoName": repo_full_name,
            "RepoLanguage": repo_language,
            "Number": pr_number,
            "Title": pr_data.get("title", ""),
            "Body": pr_data.get("body", ""),
            "CreatedAt": pr_data.get("created_at", ""),
            "ClosedAt": pr_data.get("closed_at", ""),
            "MergedAt": pr_data.get("merged_at", ""),
            "UpdatedAt": pr_data.get("updated_at", ""),
            "State": pr_data.get("state", "").upper(),
            "Additions": additions,
            "Deletions": deletions,
            "ChangedFiles": changed_files_data,
            "CommitsTotalCount": len(commits_data),
            "CommitSha": commit_shas,
            "ChatgptSharing": chatgpt_links,
        }
        res.append(this_result)

        with lock:
            global finished
            results.extend(res)
            finished += 1

    progress.update(1)  # 更新进度条


def search_github_prs(query, output_file="results_pr.json", max_workers=10, max_pages=1):
    """
    搜索 GitHub Pull Requests
    """
    per_page = 10  # 每页结果数
    page = 1
    progress = tqdm(total=0, desc="Processing PRs")  # 初始化进度条

    # 使用 ThreadPoolExecutor 管理多线程
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {}

        current_date = START_DATE

        while current_date < dt.now():
            next_date = current_date + datetime.timedelta(days=STEP_MONTHS * 30)
            date_range_query = f"updated:{current_date.strftime('%Y-%m-%d')}..{next_date.strftime('%Y-%m-%d')}"
            full_query = f"{query} {date_range_query}"

            while page <= max_pages:
                # 构建搜索 API URL
                headers = {"Accept": "application/vnd.github.text-match+json"}
                url = f"https://api.github.com/search/issues?q={full_query} is:pr&per_page={per_page}&page={page}"
                response = requests.get(url, auth=HTTPBasicAuth("username", TOKEN), headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", [])
                    total_count = data.get("total_count", 0)
                    print(f"第 {page} 页 for {date_range_query}，共 {total_count} 个结果")

                    progress.total += len(items)  # 更新进度条总量

                    if not items:
                        break  # 没有更多结果，退出循环

                    for item in items:
                        future = executor.submit(process_pull_request, item, progress)
                        future_to_item[future] = item

                    if "next" in response.links:
                        page += 1
                    else:
                        break
                elif response.status_code == 403:
                    reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                    wait_time = reset_time - int(time.time())
                    print(f"速率限制已达到，等待 {wait_time} 秒...")
                    time.sleep(wait_time)
                else:
                    print(f"请求失败，状态码: {response.status_code}")
                    break
            current_date = next_date

            for future in as_completed(future_to_item):
                try:
                    future.result(timeout=30000)
                except Exception as e:
                    print(f"子线程处理失败：{e}")

    # 保存结果为 JSON 文件
    with open(output_file, "w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(f"爬取完成，结果已保存至 {output_file}")
    progress.close()


# 示例调用
if __name__ == "__main__":
    date = time.strftime("%Y-%m-%d", time.localtime())
    search_query = "https://chat.openai.com/share/"
    search_github_prs(
        search_query,
        output_file=f"{date}-prs-openai_com.jsonl",
        max_workers=6,
        max_pages=1,
    )
