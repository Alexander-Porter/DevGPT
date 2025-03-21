import os
import re
import argparse
import shutil
from pathlib import Path

def count_lines(file_path):
    """计算文件行数"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
        line_count = sum(1 for _ in file)
    return line_count

def process_large_file(file_path, output_path=None):
    """
    使用大文件处理技术替换文件中的{"Type"为\n{"Type"
    
    Args:
        file_path: 输入文件路径
        output_path: 输出文件路径，如果为None则覆盖原文件
    """
    # 处理 Path 对象
    file_path = Path(file_path) if not isinstance(file_path, Path) else file_path
    
    if output_path is None:
        # 使用 pathlib 的方法处理路径
        output_path = file_path.with_name(f"{file_path.name}.tmp")
        replace_original = True
    else:
        output_path = Path(output_path)
        replace_original = False
    
    # 使用缓冲区读取和写入文件
    buffer_size = 1024 * 1024  # 1MB 缓冲区
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as infile, \
         open(output_path, 'w', encoding='utf-8') as outfile:
        
        # 读取第一个缓冲区
        buffer = infile.read(buffer_size)
        previous_chunk = ""
        
        # 处理文件内容
        while buffer:
            # 处理当前缓冲区
            combined_chunk = previous_chunk + buffer
            
            # 替换操作，但需要确保不会在已经有换行符的情况下再添加换行符
            processed_chunk = re.sub(r'([^\n]){"Type"', r'\1\n{"Type"', combined_chunk)
            
            # 如果是第一次处理，并且文件开头就是{"Type"，需要特殊处理
            if previous_chunk == "" and processed_chunk.startswith('{"Type"'):
                # 不在文件开头添加额外的换行符
                pass
            
            # 保存最后100个字符用于下一次处理
            if len(buffer) >= 100:
                previous_chunk = combined_chunk[-100:]
                outfile.write(processed_chunk[:-100])
            else:
                previous_chunk = ""
                outfile.write(processed_chunk)
            
            # 读取下一个缓冲区
            buffer = infile.read(buffer_size)
        
        # 写入剩余内容
        if previous_chunk:
            outfile.write(previous_chunk)
    
    # 如果需要替换原文件
    if replace_original:
        os.replace(output_path, file_path)
        print(f"已修复并覆盖原文件: {file_path}")
    else:
        print(f"已保存修复后的文件: {output_path}")

def process_raw_folder(folder_path, dry_run=False):
    """处理raw文件夹中的所有jsonl文件"""
    folder = Path(folder_path)
    
    if not folder.exists() or not folder.is_dir():
        print(f"错误: 目录 {folder_path} 不存在")
        return
    
    jsonl_files = list(folder.glob('**/*.jsonl'))
    print(f"找到 {len(jsonl_files)} 个JSONL文件")
    
    single_line_files = []
    
    # 首先扫描所有文件，找出单行文件
    for file_path in jsonl_files:
        try:
            line_count = count_lines(file_path)
            if line_count == 1:
                single_line_files.append(file_path)
                print(f"发现单行文件: {file_path}")
        except Exception as e:
            print(f"无法处理文件 {file_path}: {str(e)}")
    
    print(f"发现 {len(single_line_files)} 个需要修复的单行文件")
    
    # 执行替换操作
    if not dry_run:
        for file_path in single_line_files:
            try:
                print(f"正在处理: {file_path}")
                process_large_file(file_path)
            except Exception as e:
                print(f"处理文件 {file_path} 失败: {str(e)}")
    else:
        print("试运行模式，未执行实际修改")

def main():
    parser = argparse.ArgumentParser(description='修复JSONL文件：将单行文件中的{"Type"替换为\\n{"Type"')
    parser.add_argument('--folder', '-f', type=str, default='raw', 
                      help='包含JSONL文件的文件夹路径 (默认: "raw")')
    parser.add_argument('--dry-run', '-d', action='store_true',
                      help='试运行模式，不进行实际修改')
    
    args = parser.parse_args()
    
    process_raw_folder(args.folder, args.dry_run)

if __name__ == "__main__":
    main()
