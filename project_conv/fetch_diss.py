import time
import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from ratelimit import limits, sleep_and_retry
import json
from dotenv import load_dotenv
import os

# 加载.env文件
load_dotenv()

# 从环境变量获取TOKEN
TOKEN = os.getenv('GITHUB_TOKEN')

# API 速率限制设置
RATE_LIMIT = 5000  # 每小时调用限制
PERIOD = 3600  # 秒
RPM_LIMIT = 400  # 每分钟调用限制


@sleep_and_retry
@limits(calls=RATE_LIMIT, period=PERIOD)
def call_github_api(qu, var):
    """
    调用 GitHub API，处理速率限制。
    """

    def _call_api(query, variables=None):
        @sleep_and_retry
        @limits(calls=RPM_LIMIT, period=60)
        def _limited_call(qu, var):
            url = "https://api.github.com/graphql"
            headers = {
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            }
            return requests.post(
                url,
                headers=headers,
                json={"query": qu, "variables": var},
            )

        return _limited_call(query, variables)

    while True:
        response = _call_api(qu, var)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403:
            reset_time = int(
                response.headers.get("X-RateLimit-Reset", time.time() + 60)
            )
            wait_time = reset_time - int(time.time())
            if wait_time > 0:
                print(f"!速率限制已达到，等待 {wait_time} 秒...")
                time.sleep(wait_time)
        else:
            print(f"请求失败，状态码: {response.status_code}")
            return None


def process_discussion(node):
    """
    处理单个讨论节点，提取信息。
    """
    pattern = r"https:\/\/chat\.openai\.com\/share\/[a-zA-Z0-9-]{36}|https:\/\/chatgpt\.com\/share\/[a-zA-Z0-9-]{36}"
    chatgpt_links = []

    # 提取讨论正文中的链接
    if node.get("bodyText"):
        chatgpt_links.extend(re.findall(pattern, node["bodyText"]))

    # 提取评论中的链接
    for comment in node.get("comments", {}).get("nodes", []):
        if comment.get("bodyText"):
            chatgpt_links.extend(re.findall(pattern, comment["bodyText"]))

    # 提取答案中的链接
    if node.get("answer") and node["answer"].get("bodyText"):
        chatgpt_links.extend(re.findall(pattern, node["answer"]["bodyText"]))
    try:
        language=node.get("repository", {}).get("primaryLanguage", {}).get("name",None)
    except:
        language=None
    # 构建结果
    result = {
        "Type": "discussion",
        "URL": node.get("url"),
        "Author": node.get("author", {}).get("login"),
        "RepoName": node.get("repository", {}).get("nameWithOwner"),
        "RepoLanguage": language,
        "Number": node.get("number"),
        "Title": node.get("title"),
        "Body": node.get("bodyText"),
        "AuthorAt": node.get("createdAt"),
        "ClosedAt": node.get("closedAt"),
        "UpdatedAt": node.get("updatedAt"),
        "IsAnswered": node.get("isAnswered"),
        "AnswerChosenAt": node.get("answerChosenAt"),
        "UpvoteCount": node.get("upvoteCount"),
        "ChatgptSharing": [{"ChatgptLink": link} for link in set(chatgpt_links)],
    }
    return result


def fetch_discussions(query, output_file="discussions_results.jsonl", max_workers=5, max_pages=None):
    """
    使用分页支持提取讨论内容并保存为 JSONL 格式。
    
    Args:
        query: 搜索查询字符串
        output_file: 输出文件路径
        max_workers: 线程池最大工作线程数
        max_pages: 最大获取页数,None表示无限制
    """
    cursor = None
    current_page = 0
    progress = tqdm(total=0, desc="Fetching Discussions")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_result = {}
        with open(output_file, "w", encoding="utf-8") as f:
            while True:
                if max_pages and current_page >= max_pages:
                    print(f"已达到最大页数限制: {max_pages}")
                    break
                
                current_page += 1
                discussion_query = (
                    """query ($cursor: String) {
  search(query: "%s", type: DISCUSSION, first: 30, after: $cursor) {
    pageInfo {
      endCursor
      hasNextPage
    }
    edges {
      node {
        ... on Discussion {
          url
          title
          bodyText
          createdAt
          closedAt
          updatedAt
          isAnswered
          answerChosenAt
          upvoteCount
          number
          repository {
            nameWithOwner
            primaryLanguage {
              name
            }
          }
          author {
            login
          }
          comments(first: 100) {
            nodes {
              bodyText
            }
          }
          answer {
            bodyText
          }
        }
      }
    }
  }
}
                """ % query
                )
                variables = {"cursor": cursor}
                data = call_github_api(discussion_query, variables)

                # 检查响应数据
                if not data or "data" not in data or "search" not in data["data"]:
                    print(f"API 响应缺少预期数据：{json.dumps(data, indent=4)}")
                    break

                discussions = data["data"]["search"].get("edges", [])
                progress.total += len(discussions)
                progress.refresh()

                for edge in discussions:
                    node = edge.get("node", {})
                    if not node:
                        print(f"跳过无效的讨论节点：{json.dumps(edge, indent=4)}")
                        continue
                    future = executor.submit(process_discussion, node)
                    future_to_result[future] = node

                # 保存每个处理结果到 JSONL 文件
                for future in as_completed(future_to_result):
                    try:
                        result = future.result()
                        f.write(json.dumps(result, ensure_ascii=False) + "\n")
                        progress.update(1)
                    except Exception as e:
                        import traceback

                        print(f"处理失败：{e}")
                        traceback.print_exc()
                page_info = data["data"]["search"].get("pageInfo", {})
                if not page_info["hasNextPage"]:
                    break
                if not page_info.get("hasNextPage"):
                    break

    progress.close()
    print(f"所有结果已保存到 {output_file}")


if __name__ == "__main__":
    search_query = "https://chat.openai.com/share/"
    fetch_discussions(search_query, output_file="openai_com_discussions.jsonl", max_pages=10)  # 设置最大获取10页
