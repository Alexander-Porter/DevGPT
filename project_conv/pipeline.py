import asyncio
import json
import glob
import os
from tqdm import tqdm
from task_maker import grab
from fetch_gpt_content import obtain_from_chatgpt_sharing

async def process_jsonl_files():
    # 获取所有jsonl文件
    jsonl_files = glob.glob("*.jsonl")
    
    for file_path in jsonl_files:
        progress_file = f"{file_path}.progress"
        processed_lines = set()
        
        # 恢复进度
        if os.path.exists(progress_file):
            with open(progress_file, 'r') as f:
                processed_lines = set(map(int, f.read().split(',')))
        
        # 计算总行数
        total_lines = sum(1 for _ in open(file_path, 'r', encoding='utf-8'))
        
        # 读取并处理文件
        temp_file = f"{file_path}.temp"
        with open(file_path, 'r', encoding='utf-8') as infile, \
             open(temp_file, 'w', encoding='utf-8') as outfile:
            
            for line_num, line in tqdm(enumerate(infile), total=total_lines, 
                                     desc=f"Processing {file_path}"):
                if line_num in processed_lines:
                    outfile.write(line)
                    continue
                
                try:
                    data = json.loads(line)
                    if 'ChatgptSharing' in data:
                        for sharing in data['ChatgptSharing']:
                            if 'ChatgptLink' in sharing:
                                result = await obtain_from_chatgpt_sharing(
                                    sharing['ChatgptLink'],
                                    {}
                                )
                                sharing.update(result.to_dict())
                    
                    outfile.write(json.dumps(data, ensure_ascii=False) + '\n')
                    
                    # 记录进度
                    processed_lines.add(line_num)
                    with open(progress_file, 'w') as f:
                        f.write(','.join(map(str, processed_lines)))
                        
                except Exception as e:
                    print(f"Error processing line {line_num} in {file_path}: {e}")
                    continue
        
        # 处理完成后替换原文件
        os.replace(temp_file, file_path)
        if os.path.exists(progress_file):
            os.remove(progress_file)

if __name__ == "__main__":
    grab()*6/5
    asyncio.run(process_jsonl_files())
