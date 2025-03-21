import json
import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # 为flash消息设置密钥

# 数据文件路径
DATA_FILE = 'cleaned_data.json'
OUTPUT_FILE = 'labeled_data.jsonl'

def load_data():
    """从JSON文件加载数据"""
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_decision(item, decision):
    """将标记决定保存到JSONL文件"""
    item['labeled'] = decision
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')

def get_processed_ids():
    """获取已处理的数据ID列表"""
    processed_ids = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    item = json.loads(line.strip())
                    if 'Source' in item:
                        processed_ids.add(item['Source'])
                except json.JSONDecodeError:
                    continue
    return processed_ids

@app.route('/')
def index():
    """主页面，显示待标记的数据"""
    data = load_data()
    processed_ids = get_processed_ids()
    
    # 过滤出未处理的数据
    remaining_data = [item for item in data if item['Source'] not in processed_ids]
    
    if not remaining_data:
        return render_template('complete.html')
    
    # 获取第一个未处理的数据
    current_item = remaining_data[0]
    
    # 格式化代码以便于显示
    code = current_item.get('most_possible_src_code', '')
    language = current_item.get('Language', 'plaintext')
    test_code= current_item.get('Code', '')
    # 统计信息
    total = len(data)
    processed = len(processed_ids)
    remaining = total - processed
    
    return render_template('index.html', 
                          item=current_item, 
                          code=code, 
                          language=language,
                            test_code=test_code,
                          total=total,
                          processed=processed,
                          remaining=remaining)

@app.route('/label', methods=['POST'])
def label():
    """处理标记决定"""
    data = load_data()
    source = request.form.get('source')
    decision = request.form.get('decision') == 'true'
    # 获取用户编辑后的源代码
    edited_code = request.form.get('edited_code', '')
    
    # 找到对应的数据项
    for item in data:
        if item['Source'] == source:
            # 更新源代码字段
            if edited_code:
                item['most_possible_src_code'] = edited_code
            save_decision(item, decision)
            flash('数据已标记并保存！', 'success')
            break
    
    return redirect(url_for('index'))

@app.route('/stats')
def stats():
    """显示标记统计信息"""
    processed_ids = get_processed_ids()
    
    accepted = 0
    rejected = 0
    
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    item = json.loads(line.strip())
                    if item.get('labeled'):
                        accepted += 1
                    else:
                        rejected += 1
                except json.JSONDecodeError:
                    continue
    
    return jsonify({
        'processed': len(processed_ids),
        'accepted': accepted,
        'rejected': rejected
    })

if __name__ == '__main__':
    app.run(debug=True)
