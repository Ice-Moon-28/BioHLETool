#!/usr/bin/env python3
"""
筛选掉answer中分号数量>1的问题，将剩下的问题保存到新文件中
"""

import json
import os
from datetime import datetime

def count_semicolons(text):
    """计算文本中分号的数量"""
    if not text:
        return 0
    return text.count(';')

def filter_questions_by_semicolons(input_file, output_file):
    """
    筛选掉answer中分号数量>1的问题
    
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
    """
    print(f"正在读取文件: {input_file}")
    
    # 读取原始数据
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"原始问题数量: {len(data['filtered_questions'])}")
    
    # 筛选问题
    filtered_questions = []
    removed_count = 0
    
    for question in data['filtered_questions']:
        # 获取answer文本
        answer = ""
        if 'original_data' in question:
            for key, value in question['original_data'].items():
                if isinstance(value, dict) and 'answer' in value:
                    answer = value['answer']
                    break
        
        # 计算分号数量
        semicolon_count = count_semicolons(answer)
        
        if semicolon_count <= 1:
            filtered_questions.append(question)
        else:
            removed_count += 1
            if removed_count <= 5:  # 只显示前5个被移除的例子
                print(f"移除问题 (分号数量: {semicolon_count}): {answer[:100]}...")
    
    # 创建新的数据结构
    filtered_data = {
        "filtered_questions": filtered_questions,
        "filter_info": {
            "original_count": len(data['filtered_questions']),
            "filtered_count": len(filtered_questions),
            "removed_count": removed_count,
            "filter_criteria": "answer中分号数量 <= 1",
            "filter_date": datetime.now().isoformat()
        }
    }
    
    # 保存筛选后的数据
    print(f"正在保存到文件: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(filtered_data, f, ensure_ascii=False, indent=2)
    
    print(f"筛选完成!")
    print(f"原始问题数量: {len(data['filtered_questions'])}")
    print(f"筛选后问题数量: {len(filtered_questions)}")
    print(f"移除问题数量: {removed_count}")
    print(f"保留比例: {len(filtered_questions)/len(data['filtered_questions'])*100:.2f}%")

def main():
    input_file = "filtered_questions.json"
    output_file = "filtered_questions_no_multiple_semicolons.json"
    
    if not os.path.exists(input_file):
        print(f"错误: 输入文件 {input_file} 不存在!")
        return
    
    filter_questions_by_semicolons(input_file, output_file)

if __name__ == "__main__":
    main()
