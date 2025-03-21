import time
from fetch_codes import search_github_code
from fetch_commits import search_github_commits_with_date
from fetch_diss import fetch_discussions
from fetch_issues import search_github_issues
from fetch_pr import search_github_prs
from fetch_hn import search_hacker_news
def grab():
    date = time.strftime("%Y-%m-%d", time.localtime())
    search_query1 = 'https://chat.openai.com/share/'  # 替换为你的搜索关键词
    search_query2 = 'https://chatgpt.com/share/'  # 替换为你的搜索关键词
    search_github_code(search_query1, output_file=f'{date}-code-openai_com.jsonl', max_workers=30, max_pages=10240)
    search_github_code(search_query2, output_file=f'{date}-code-chatgpt_com.jsonl', max_workers=30, max_pages=10240)
    search_github_commits_with_date(search_query1,output_file=f'{date}-commits-openai_com.jsonl', max_workers=30, max_pages=10240)
    search_github_commits_with_date(search_query2,output_file=f'{date}-commits-openai_com.jsonl', max_workers=30, max_pages=10240)
    fetch_discussions(search_query1,output_file=f'{date}-disscussions-openai_com.jsonl', max_workers=30)
    fetch_discussions(search_query2,output_file=f'{date}-disscussions-chatgpt_com.jsonl', max_workers=30)
    search_github_issues(search_query1, output_file=f'{date}-issues-openai_com.jsonl', max_workers=30, max_pages=10240)
    search_github_issues(search_query2, output_file=f'{date}-issues-chatgpt_com.jsonl', max_workers=30, max_pages=10240)
    search_github_prs(search_query1, output_file=f'{date}-prs-openai_com.jsonl', max_workers=30, max_pages=10240)
    search_github_prs(search_query2, output_file=f'{date}-prs-chatgpt_com.jsonl', max_workers=30, max_pages=10240)
    search_hacker_news(search_query1, output_file=f'{date}-hn-openai_com.jsonl', max_workers=30, max_pages=10240)
    search_hacker_news(search_query2, output_file=f'{date}-hn-chatgpt_com.jsonl', max_workers=30, max_pages=10240)