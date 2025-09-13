#!/usr/bin/env python3
"""
去重filtered_questions.json文件中的重复问题
"""

import json
import hashlib
from typing import List, Dict, Any, Set
from datetime import datetime


def get_question_hash(question_data: Dict[str, Any]) -> str:
    """
    生成问题的唯一哈希值（基于test_results）
    
    Args:
        question_data: 问题数据
        
    Returns:
        问题的哈希值
    """
    # 提取关键信息用于生成哈希
    question_type = question_data.get('question_type', '')
    test_results = question_data.get('test_results', {})
    
    # 从test_results中提取测试结果
    without_facts = test_results.get('without_facts', {})
    with_facts = test_results.get('with_facts', {})
    
    # 构建用于哈希的内容：问题类型 + 无事实答案 + 有事实答案
    without_facts_answer = without_facts.get('answer', '')
    with_facts_answer = with_facts.get('answer', '')
    
    content_to_hash = f"{question_type}:{without_facts_answer}:{with_facts_answer}"
    
    # 生成MD5哈希
    return hashlib.md5(content_to_hash.encode('utf-8')).hexdigest()


def clean_original_data(question: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据question_type精简original_data，只保留对应类型的词典
    
    Args:
        question: 问题数据
        
    Returns:
        精简后的问题数据
    """
    question_type = question.get('question_type', '')
    original_data = question.get('original_data', {})
    
    # 创建精简后的original_data
    cleaned_original_data = {}
    
    # 根据question_type只保留对应的词典
    if question_type in original_data:
        cleaned_original_data[question_type] = original_data[question_type]
    
    # 创建精简后的问题数据
    cleaned_question = question.copy()
    cleaned_question['original_data'] = cleaned_original_data
    
    return cleaned_question


def deduplicate_questions(input_file: str, output_file: str = None) -> Dict[str, Any]:
    """
    去重filtered_questions.json文件
    
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径，如果为None则覆盖原文件
        
    Returns:
        去重统计信息
    """
    if output_file is None:
        output_file = input_file
    
    print(f"开始处理文件: {input_file}")
    
    # 读取原始数据
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 提取问题列表
    if isinstance(data, dict) and "filtered_questions" in data:
        questions = data["filtered_questions"]
        original_stats = data.get("statistics", {})
    elif isinstance(data, list):
        questions = data
        original_stats = {}
    else:
        raise ValueError("无法识别的文件格式")
    
    print(f"原始问题数量: {len(questions)}")
    
    # 去重逻辑
    seen_hashes: Set[str] = set()
    unique_questions: List[Dict[str, Any]] = []
    duplicate_count = 0
    
    for i, question in enumerate(questions):
        question_hash = get_question_hash(question)
        
        if question_hash not in seen_hashes:
            seen_hashes.add(question_hash)
            # 精简original_data
            cleaned_question = clean_original_data(question)
            unique_questions.append(cleaned_question)
        else:
            duplicate_count += 1
            if duplicate_count <= 10:  # 只打印前10个重复的例子
                question_type = question.get('question_type', 'unknown')
                original_question = question.get('original_data', {}).get('original', {}).get('question', '')[:100]
                print(f"发现重复问题 {duplicate_count}: {question_type} - {original_question}...")
    
    print(f"去重后问题数量: {len(unique_questions)}")
    print(f"删除重复问题数量: {duplicate_count}")
    
    # 更新统计信息
    updated_stats = original_stats.copy()
    if "filtered" in updated_stats:
        updated_stats["filtered"] = len(unique_questions)
    
    # 按问题类型统计
    type_stats = {
        "rewritten": 0,
        "new_fact_question": 0,
        "mixed_fact_question": 0
    }
    
    for question in unique_questions:
        question_type = question.get('question_type', 'unknown')
        if question_type in type_stats:
            type_stats[question_type] += 1
    
    print(f"\n按类型统计:")
    for question_type, count in type_stats.items():
        print(f"  {question_type}: {count}")
    
    # 构建输出数据
    if isinstance(data, dict):
        output_data = {
            "filtered_questions": unique_questions,
            "statistics": updated_stats,
            "deduplication_info": {
                "original_count": len(questions),
                "unique_count": len(unique_questions),
                "duplicate_count": duplicate_count,
                "deduplication_date": datetime.now().isoformat(),
                "original_data_cleaned": True
            },
            "last_updated": datetime.now().isoformat()
        }
    else:
        output_data = unique_questions
    
    # 保存去重后的数据
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n去重完成！结果已保存到: {output_file}")
    
    # 返回统计信息
    return {
        "original_count": len(questions),
        "unique_count": len(unique_questions),
        "duplicate_count": duplicate_count,
        "type_stats": type_stats,
        "output_file": output_file
    }


def analyze_duplicates(input_file: str) -> None:
    """
    分析重复问题的详细情况
    
    Args:
        input_file: 输入文件路径
    """
    print(f"分析文件: {input_file}")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, dict) and "filtered_questions" in data:
        questions = data["filtered_questions"]
    elif isinstance(data, list):
        questions = data
    else:
        raise ValueError("无法识别的文件格式")
    
    # 统计每个哈希值出现的次数
    hash_counts = {}
    hash_examples = {}
    
    for question in questions:
        question_hash = get_question_hash(question)
        hash_counts[question_hash] = hash_counts.get(question_hash, 0) + 1
        
        # 保存第一个例子
        if question_hash not in hash_examples:
            test_results = question.get('test_results', {})
            without_facts_answer = test_results.get('without_facts', {}).get('answer', '')[:100]
            with_facts_answer = test_results.get('with_facts', {}).get('answer', '')[:100]
            
            hash_examples[question_hash] = {
                "question_type": question.get('question_type', 'unknown'),
                "without_facts_answer": without_facts_answer,
                "with_facts_answer": with_facts_answer,
                "count": 0
            }
        hash_examples[question_hash]["count"] = hash_counts[question_hash]
    
    # 找出重复的问题
    duplicates = {h: count for h, count in hash_counts.items() if count > 1}
    
    print(f"\n重复分析结果:")
    print(f"总问题数: {len(questions)}")
    print(f"唯一问题数: {len(hash_counts)}")
    print(f"重复问题数: {len(duplicates)}")
    print(f"总重复次数: {sum(duplicates.values()) - len(duplicates)}")
    
    # 显示重复最多的前10个
    sorted_duplicates = sorted(duplicates.items(), key=lambda x: x[1], reverse=True)
    print(f"\n重复最多的前10个问题:")
    for i, (hash_val, count) in enumerate(sorted_duplicates[:10], 1):
        example = hash_examples[hash_val]
        print(f"{i}. 重复{count}次 - {example['question_type']}")
        print(f"   无事实答案: {example['without_facts_answer']}...")
        print(f"   有事实答案: {example['with_facts_answer']}...")
        print()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='去重filtered_questions.json文件')
    parser.add_argument('--input', '-i', default='filtered_questions.json', 
                       help='输入文件路径 (默认: filtered_questions.json)')
    parser.add_argument('--output', '-o', default=None,
                       help='输出文件路径 (默认: 覆盖原文件)')
    parser.add_argument('--analyze', '-a', action='store_true',
                       help='只分析重复情况，不进行去重')
    parser.add_argument('--backup', '-b', action='store_true',
                       help='去重前创建备份文件')
    
    args = parser.parse_args()
    
    try:
        if args.analyze:
            # 只分析重复情况
            analyze_duplicates(args.input)
        else:
            # 进行去重
            if args.backup:
                backup_file = f"{args.input}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                import shutil
                shutil.copy2(args.input, backup_file)
                print(f"已创建备份文件: {backup_file}")
            
            stats = deduplicate_questions(args.input, args.output)
            
            print(f"\n=== 去重完成 ===")
            print(f"原始问题数: {stats['original_count']}")
            print(f"去重后问题数: {stats['unique_count']}")
            print(f"删除重复数: {stats['duplicate_count']}")
            print(f"输出文件: {stats['output_file']}")
            
    except Exception as e:
        print(f"处理失败: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
