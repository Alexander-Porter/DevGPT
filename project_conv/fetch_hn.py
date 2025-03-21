import threading
import time
import requests
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from ratelimit import limits, sleep_and_retry

# 全局变量
results = []
lock = threading.Lock()

RATE_LIMIT = 1000  # 次
PERIOD = 3600  # 秒

@sleep_and_retry
@limits(calls=RATE_LIMIT, period=PERIOD)
def call_hacker_news_api(query, page):
    """
    调用 Hacker News API。
    """
    url = f"http://hn.algolia.com/api/v1/search?query={query}&page={page}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"API 请求失败，状态码: {response.status_code}")
        return None

def process_hacker_news_item(item):
    """
    处理单条 Hacker News 数据。
    """
    try:
        pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        story_text = item.get("story_text", "")
        matches = re.findall(pattern, story_text) if story_text else []

        chatgpt_sharing = [
            {
                "ChatgptLink": f"https://chatgpt.com/share/{match}",
                "MentionedProperty": "story_text",
                "MentionedBy": item.get("author"),
                "MentionedText": story_text
            } for match in matches
        ]
        if chatgpt_sharing:
            result = {
                "Type": "hacker_news",
                "ID": item.get("objectID"),
                "URL": item.get("url"),
                "Author": item.get("author"),
                "Points": item.get("points"),
                "AttachedURL": item.get("url"),
                "Title": item.get("title"),
                "StoryText": story_text,
                "CreatedAt": item.get("created_at"),
                "CommentsTotalCount": item.get("num_comments"),
                "ChatgptSharing": chatgpt_sharing
            }

            return result
        return None
    except Exception as e:
        print(f"处理 Hacker News 数据时出错：{e}")
        return None

def search_hacker_news(query, output_file="hacker_news_results.json", max_pages=10, max_workers=5):
    """
    搜索 Hacker News 数据。
    """
    progress = tqdm(total=0, desc="Processing Hacker News Stories")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_page = {executor.submit(call_hacker_news_api, query, page): page for page in range(max_pages)}
        for future in as_completed(future_to_page):
            try:
                page_data = future.result()
                if page_data and "hits" in page_data:
                    items = page_data["hits"]
                    progress.total += len(items)
                    with open("data1.json","w") as f:
                        f.write(json.dumps(page_data))
                    for item in items:
                        result = process_hacker_news_item(item)
                        if result:
                            with lock:
                                results.append(result)

            except Exception as e:
                print(f"处理页面数据时出错：{e}")

    # 保存结果到文件
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"爬取完成，结果已保存至 {output_file}")
    progress.close()

# 示例调用
if __name__ == "__main__":
    date=time.strftime("%Y-%m-%d", time.localtime())
    search_query = "chatgpt.com" 
    search_hacker_news(search_query, output_file=f"{date}-hacker_news_chatgpt_com_results.json", max_pages=50, max_workers=6)
    search_query2 = "chat.openai.com" 
    search_hacker_news(search_query2, output_file=f"{date}-hacker_news_openai_com_results.json", max_pages=50, max_workers=6)