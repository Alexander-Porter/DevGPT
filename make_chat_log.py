import json


def make_chat_log(details):
    markdown_content = ""


    for item in details:
        markdown_content += f"## Title: {item.get('GptTitle', 'No Title')}\n"
        markdown_content += f"- **Source**: {item.get('Source', 'No Source')}\n"
        markdown_content += f"- **GptUrl**: {item.get('GptUrl', 'No URL')}\n\n"
        
        for content in item.get('GptContent', []):
            markdown_content += f"### Prompt: {content.get('Prompt', 'No Prompt')}\n\n"
            markdown_content += f"**Answer:**\n\n{content.get('Answer', 'No Answer')}\n\n"
            for code_block in content.get('ListOfCode', []):
                markdown_content += f"```{code_block.get('Type', 'text')}\n"
                markdown_content += f"{code_block.get('Content', 'No Code')}\n"
                markdown_content += "```\n\n"
    return markdown_content

if __name__=="__main__":
    with open("gpt_url_duplicates_ranking.json", "r") as f:
        data = json.load(f)
    details = data.get("details", [])
    details=[i[-1] for i in details]
    markdown_content = make_chat_log(details)

    with open("chat_log.md", "w",encoding="utf-8") as f:
        f.write(markdown_content)
    print("chat_log.md has been updated.")
    input("Press Enter to update again.")