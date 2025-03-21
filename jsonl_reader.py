import json
import argparse
from typing import List, Dict, Any, Optional
import sys

def read_jsonl(file_path: str, num_lines: int = 5) -> List[Dict[str, Any]]:
    """
    读取JSONL文件的前几行并解析为JSON对象列表

    Args:
        file_path (str): JSONL文件路径
        num_lines (int, optional): 要读取的行数. 默认为5.

    Returns:
        List[Dict[str, Any]]: 解析后的JSON对象列表
    """
    results = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= num_lines:
                    break
                if line.strip():  # 跳过空行
                    try:
                        json_obj = json.loads(line.strip())
                        results.append(json_obj)
                    except json.JSONDecodeError as e:
                        print(f"Error parsing line {i+1}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
    
    return results

def main():
    parser = argparse.ArgumentParser(description='Read and parse the first few lines of a JSONL file')
    parser.add_argument('file_path', type=str, help='Path to the JSONL file')
    parser.add_argument('--lines', '-n', type=int, default=5, 
                        help='Number of lines to read (default: 5)')
    parser.add_argument('--pretty', '-p', action='store_true', 
                        help='Pretty print the JSON output')
    
    args = parser.parse_args()
    
    json_objects = read_jsonl(args.file_path, args.lines)
    
    # 输出结果
    if args.pretty:
        print(json.dumps(json_objects, ensure_ascii=False, indent=2))
    else:
        print(json_objects)
    
    print(f"\n成功解析 {len(json_objects)} 行JSON数据。")

if __name__ == "__main__":
    main()
