# 生物医学题目生成Pipeline使用说明

## 功能概述

这个Pipeline实现了生物医学题目的自动生成，包括：
1. 从原始题目中提取知识
2. 重写题目
3. 搜索相关新事实
4. 基于新事实生成题目
5. 基于混合事实生成题目

## 新增功能

### 1. Debug模式
- 使用 `--debug` 参数启用调试模式
- 调试模式下只处理第一条数据，便于测试和调试
- 可以指定 `--sample-index` 来选择处理哪条数据

### 2. 多线程并发处理
- 非debug模式下，默认使用10个线程并发处理
- 可以通过 `--workers` 参数调整线程数
- 通过 `--batch-size` 参数调整批处理大小

### 3. 中断保存机制
- 支持Ctrl+C中断程序
- 中断时自动保存已处理的结果
- 使用文件锁确保多线程写入安全

### 4. 结果暂存和批量保存
- 所有生成结果暂存到内存列表中
- 每批次完成后自动保存到文件
- 支持增量保存，避免数据丢失

## 使用方法

### 调试模式
```bash
# 处理第一条数据
python main_agent.py --debug

# 处理指定索引的数据
python main_agent.py --debug --sample-index 5
```

### 生产模式（批量处理）
```bash
# 使用默认参数（10线程，批处理大小10）
python main_agent.py

# 自定义参数
python main_agent.py --workers 5 --batch-size 20 --output my_results.json

# 指定数据集路径
python main_agent.py --dataset path/to/your/dataset.json
```

### 命令行参数说明

- `--debug`: 启用调试模式，只处理第一条数据
- `--sample-index`: 调试模式下使用的样例索引（默认0）
- `--dataset`: 数据集路径（默认：dataset/hle/train.json）
- `--output`: 输出文件路径（默认：pipeline_results.json）
- `--workers`: 并发线程数（默认：10）
- `--batch-size`: 批处理大小（默认：10）

## 输出文件格式

结果保存为JSON格式，包含以下结构：
```json
[
  {
    "original": {
      "question": "原始题目",
      "rationale": "原始解答"
    },
    "analysis": {
      "subdomain": "子领域",
      "supporting_facts": ["支撑事实列表"],
      "error_prone_points": ["易错点列表"]
    },
    "rewritten": {
      "question": "重写后的题目",
      "rationale": "重写后的解答"
    },
    "new_fact_question": {
      "question": "基于新事实的题目",
      "rationale": "解答",
      "supporting_facts": ["使用的事实"]
    },
    "mixed_fact_question": {
      "question": "基于混合事实的题目",
      "rationale": "解答",
      "supporting_facts": ["所有使用的事实"],
      "original_facts_used": ["使用的原始事实"],
      "new_facts_used": ["使用的新事实"]
    },
    "original_data": {
      "id": "题目ID",
      "category": "类别",
      "raw_subject": "主题"
    },
    "pipeline_metadata": {
      "model_used": "使用的模型",
      "tools_available": "可用工具数量",
      "new_facts_discovered": "发现的新事实数量"
    }
  }
]
```

## 日志文件

程序会生成两种日志文件：
- `logs/pipeline_info_YYYYMMDD_HHMMSS.log`: INFO级别日志
- `logs/pipeline_debug_YYYYMMDD_HHMMSS.log`: DEBUG级别日志

## 注意事项

1. 确保有足够的API调用额度，因为每个题目会进行多次LLM调用
2. 多线程模式下，注意API调用频率限制
3. 中断程序时会自动保存已处理的结果，不会丢失数据
4. 建议先用debug模式测试，确认无误后再进行批量处理
