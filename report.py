import json

def json_to_markdown(json_file, output_file):
    # 读取JSON文件
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 创建markdown内容
    markdown_content = []
    count = 0
    has_most_possible_src_code = 0
    for item in data:
        # 获取需要的字段
        title = item.get('GptTitle', 'No Title')
        test_code = item.get('Code', 'No Code')
        language = item.get('Language', 'Unknown')
        prompt = item.get('LastUerPrompt', 'No Prompt')
        main_code = item.get('most_possible_src_code', '')
        code_blocks = item.get('src_code_blocks', [])[1:3]  # 只取前三条
        if main_code:
            has_most_possible_src_code += 1
        count += 1

        # 格式化为markdown
        section = f"""
## {title}

### Language
{language}

### Last User Prompt
{prompt}

### Most Possible Source Code
```
{main_code}
```

### Test Code
```{language}
{test_code}
```
"""
        if code_blocks:
            section += "### Other Code Blocks\n"
            for code_block in code_blocks:
                section += f"""```{language}
{code_block}
```
"""
        markdown_content.append(section)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(markdown_content))
    print(f"Total items: {count}")
    print(f"Items with most possible source code: {has_most_possible_src_code}")

if __name__ == '__main__':
    json_to_markdown('cleaned_data.json', 'candidates.md')