import os
import json

keywords = ['assert', 'expect(', '   expect(', 'Errorf']
has_met_links_and_their_index={}
def process_jsonl_file(file_path, keywords):
    total_items = 0
    total_code_blocks = 0
    items_with_code_blocks = 0
    items_with_keywords = 0
    filtered_items = []
    keyword_blocks = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        # 逐行读取 JSONL 文件
        for line in f:
            try:
                item = json.loads(line.strip())
                total_items += 1
                has_code_block = False
                has_keyword = False
                
                # 检查是否有对话和代码块
                if 'ChatgptSharing' in item and isinstance(item['ChatgptSharing'], list):

                    for sharing in item['ChatgptSharing']:
                        if 'conversations' in sharing and isinstance(sharing['conversations'], list):
                            index = 0
                            for conversation in sharing['conversations']:
                                if 'list_of_code' in conversation and isinstance(conversation['list_of_code'], list):
                                    has_code_block = True
                                    total_code_blocks += len(conversation['list_of_code'])
                                    for code in conversation['list_of_code']:
                                        if 'content' in code and any(keyword in code['content'].lower() for keyword in keywords):
                                            if item.get("URL","") in has_met_links_and_their_index.keys() and has_met_links_and_their_index[item.get("URL","")]>=index:
                                                continue
                                            
                                            has_met_links_and_their_index[item.get("URL","")]=index
                                            data = {
                                                'Type': item.get('Type', ''),
                                                'Source': item.get('URL', ''),
                                                'GptUrl': sharing.get('url', ''),
                                                'GptTitle': sharing.get('title', ''),
                                                'GptContent': sharing['conversations'],
                                                'Code': code['content'],
                                                'Language': code.get('type', ''),
                                                'LastUerPrompt': conversation.get('prompt', ''),
                                                'FullResp': conversation.get('answer', ''),
                                                'IndexInConv': index
                                            }
                                            has_keyword = True
                                            keyword_blocks.append(data)
                                index += 1
                
                # 统计包含代码块的 item
                if has_code_block:
                    items_with_code_blocks += 1

                # 如果包含关键字，保存此项
                if has_keyword:
                    items_with_keywords += 1
                    filtered_items.append(item)
            except json.JSONDecodeError as e:
                print(f"无法解析行: {line[:50]}... 错误: {e}")

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
    dir_name = 'raw'  # 更改为指定的目录名
    
    # 目录统计
    total_items_dir = 0
    total_code_blocks_dir = 0
    items_with_code_blocks_dir = 0
    items_with_keywords_dir = 0
    all_keyword_blocks = []
    
    for file_name in os.listdir(dir_name):
        if file_name.endswith('.jsonl'):  # 更改为 .jsonl 扩展名
            file_path = os.path.join(dir_name, file_name)
            print(f"正在处理 {file_path} ...")
            result = process_jsonl_file(file_path, keywords)
            print(f"总项数: {result['total_items']}")
            print(f"总代码块数: {result['total_code_blocks']}")
            print(f"包含代码块的项数: {result['items_with_code_blocks']}")
            print(f"包含关键字的项数: {result['items_with_keywords']}")
            
            # 保存筛选结果
            output_filename = f'{file_name}_filtered.json'
            with open(output_filename, 'w', encoding='utf-8') as f:
                json.dump(result['filtered_items'], f, ensure_ascii=False, indent=2)
                
            all_keyword_blocks.extend(result['keyword_blocks'])
            total_items_dir += result['total_items']
            total_code_blocks_dir += result['total_code_blocks']
            items_with_code_blocks_dir += result['items_with_code_blocks']
            items_with_keywords_dir += result['items_with_keywords']
    
    # 输出总结统计
    print(f"目录总项数: {total_items_dir}")
    print(f"目录总代码块数: {total_code_blocks_dir}")
    print(f"目录包含代码块的项数: {items_with_code_blocks_dir}")
    print(f"目录包含关键字的项数: {items_with_keywords_dir}")
    
    # 保存所有包含关键字的代码块
    # Save all keyword blocks as JSON
    with open('all_keyword_blocks_full.json', 'w', encoding='utf-8') as f:
        json.dump(all_keyword_blocks, f, ensure_ascii=False, indent=2)
    
    # Save all keyword blocks as JSONL
    with open('all_keyword_blocks_full_title.jsonl', 'w', encoding='utf-8') as f:
        for block in all_keyword_blocks:
            f.write(json.dumps(block, ensure_ascii=False) + '\n')