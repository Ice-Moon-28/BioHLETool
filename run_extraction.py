#!/usr/bin/env python3
"""
批量提取训练数据中的信息的脚本
"""

from extract_fact_agent import ExtractFactAgent
import argparse
import os


def main():
    parser = argparse.ArgumentParser(description='从HLE训练数据中提取信息')
    parser.add_argument('--input', '-i', 
                       default='/Users/liyihang/code/cursor/BioHLETool/dataset/hle/train.json',
                       help='输入文件路径')
    parser.add_argument('--output', '-o',
                       default='/Users/liyihang/code/cursor/BioHLETool/extracted_facts.json',
                       help='输出文件路径')
    parser.add_argument('--start', '-s', type=int, default=0,
                       help='开始索引')
    parser.add_argument('--batch-size', '-b', type=int, default=10,
                       help='批次大小')
    parser.add_argument('--model', '-m', default='gpt-4o-mini',
                       help='使用的模型')
    
    args = parser.parse_args()
    
    # 检查输入文件是否存在
    if not os.path.exists(args.input):
        print(f"错误: 输入文件 {args.input} 不存在")
        return
    
    # 创建输出目录
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    print(f"输入文件: {args.input}")
    print(f"输出文件: {args.output}")
    print(f"开始索引: {args.start}")
    print(f"批次大小: {args.batch_size}")
    print(f"使用模型: {args.model}")
    print("-" * 50)
    
    # 创建agent并运行
    agent = ExtractFactAgent(model=args.model)
    agent.run(
        input_file=args.input,
        output_file=args.output,
        start_idx=args.start,
        batch_size=args.batch_size
    )


if __name__ == "__main__":
    main()
