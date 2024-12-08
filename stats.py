import os
import ijson
import json
keywords = ['assert', 'expect(', '   expect(', 'Errorf']
def process_large_json(file_path, keywords):
    total_items = 0
    total_code_blocks = 0
    items_with_code_blocks = 0
    items_with_keywords = 0
    filtered_items = []
    keyword_blocks = []
    with open(file_path, 'r', encoding='utf-8') as f:
        # 使用 ijson 流式解析 Sources 数组
        for item in ijson.items(f, 'Sources.item'):
            total_items += 1
            has_code_block = False
            has_keyword = False
            
            # 检查是否有对话和代码块
            if 'ChatgptSharing' in item and isinstance(item['ChatgptSharing'], list):
                for sharing in item['ChatgptSharing']:
                    if 'Conversations' in sharing and isinstance(sharing['Conversations'], list):
                        index=0
                        for conversation in sharing['Conversations']:
                            if 'ListOfCode' in conversation and isinstance(conversation['ListOfCode'], list):
                                has_code_block = True
                                for code in conversation['ListOfCode']:
                                    if 'Content' in code and any(keyword in code['Content'].lower() for keyword in keywords):
                                        data={
                                            'Type':item['Type'],
                                            'Source':item['URL'],
                                            'GptUrl':sharing['URL'],
                                            'GptTitle':sharing['Title'],
                                            'GptContent':sharing['Conversations'],
                                            'Code':code['Content'],
                                            'Language':code['Type'],
                                            'LastUerPrompt':conversation['Prompt'],
                                            'FullResp':conversation['Answer'],
                                            'IndexInConv':index
                                        }
                                        has_keyword = True
                                        keyword_blocks.append(data)
                            index+=1
            
            # 统计包含代码块的 item
            if has_code_block:
                items_with_code_blocks += 1
                total_code_blocks += len(conversation['ListOfCode'])

            # 如果包含关键字，保存此项
            if has_keyword:
                items_with_keywords += 1
                filtered_items.append(item)

    # 返回统计信息和筛选结果
    return {
        "total_items": total_items,
        "total_code_blocks": total_code_blocks,
        "items_with_code_blocks": items_with_code_blocks,
        "items_with_keywords": items_with_keywords,
        "filtered_items": filtered_items,
        "keyword_blocks": keyword_blocks
    }

if __name__ == '__main__':
    dir_name = 'snapshot_20231012'
    #stats for this directory
    total_items_dir = 0
    total_code_blocks_dir = 0
    items_with_code_blocks_dir = 0
    items_with_keywords_dir = 0
    all_keyword_blocks = []
    for file_name in os.listdir(dir_name):
        if file_name.endswith('.json'):
            file_path = os.path.join(dir_name, file_name)
            print(f"正在处理 {file_path} ...")
            result = process_large_json(file_path, keywords)
            print(f"总项数: {result['total_items']}")
            print(f"总代码块数: {result['total_code_blocks']}")
            print(f"包含代码块的项数: {result['items_with_code_blocks']}")
            print(f"包含关键字的项数: {result['items_with_keywords']}")
            with open(f'{file_name}_filtered.json', 'w', encoding='utf-8') as f:
                json.dump(result['filtered_items'], f, ensure_ascii=False, indent=2)
            all_keyword_blocks.extend(result['keyword_blocks'])
            total_items_dir += result['total_items']
            total_code_blocks_dir += result['total_code_blocks']
            items_with_code_blocks_dir += result['items_with_code_blocks']
            items_with_keywords_dir += result['items_with_keywords']
    print(f"总项数: {total_items_dir}")
    print(f"总代码块数: {total_code_blocks_dir}")
    print(f"包含代码块的项数: {items_with_code_blocks_dir}")
    print(f"包含关键字的项数: {items_with_keywords_dir}")
    with open('all_keyword_blocks_full.json', 'w', encoding='utf-8') as f:
        json.dump(all_keyword_blocks, f, ensure_ascii=False, indent=2)
