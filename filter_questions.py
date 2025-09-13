import json
import time
import logging
import threading
import signal
import sys
import os
from datetime import datetime
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from tools.llm_call import call_qwen_chat


class ThreadSafeResultSaver:
    """线程安全的结果保存器"""
    
    def __init__(self, output_file: str, logger: logging.Logger):
        self.output_file = output_file
        self.logger = logger
        self.file_lock = threading.Lock()
        self.results_lock = threading.Lock()
        self.filtered_questions = []
        self.stats = {
            "total_questions": 0,
            "processed": 0,
            "without_facts_wrong": 0,
            "with_facts_correct": 0,
            "filtered": 0,
            "errors": 0,
            "by_type": {
                "rewritten": {"processed": 0, "filtered": 0},
                "new_fact_question": {"processed": 0, "filtered": 0},
                "mixed_fact_question": {"processed": 0, "filtered": 0}
            }
        }
        self.interrupted = False
        
        # 设置中断信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """处理Ctrl+C中断信号"""
        self.logger.info("接收到中断信号，正在保存已处理的结果...")
        print("\n接收到中断信号，正在保存已处理的结果...")
        self.interrupted = True
        self.save_results()
        sys.exit(0)
    
    def add_results(self, filtered_questions: List[Dict[str, Any]], question_stats: Dict[str, Any]):
        """线程安全地添加结果"""
        with self.results_lock:
            self.filtered_questions.extend(filtered_questions)
            
            # 合并统计信息
            self.stats["processed"] += question_stats["processed"]
            self.stats["without_facts_wrong"] += question_stats["without_facts_wrong"]
            self.stats["with_facts_correct"] += question_stats["with_facts_correct"]
            self.stats["filtered"] += question_stats["filtered"]
            self.stats["errors"] += question_stats["errors"]
            
            # 合并按类型的统计
            for question_type in ["rewritten", "new_fact_question", "mixed_fact_question"]:
                if question_type in question_stats["by_type"]:
                    self.stats["by_type"][question_type]["processed"] += question_stats["by_type"][question_type]["processed"]
                    self.stats["by_type"][question_type]["filtered"] += question_stats["by_type"][question_type]["filtered"]
    
    def set_total_questions(self, total: int):
        """设置总问题数"""
        with self.results_lock:
            self.stats["total_questions"] = total
    
    def save_results(self):
        """线程安全地保存结果到文件"""
        with self.file_lock:
            try:
                # 读取现有结果
                existing_results = []
                if os.path.exists(self.output_file):
                    with open(self.output_file, 'r', encoding='utf-8') as f:
                        loaded_data = json.load(f)
                        if isinstance(loaded_data, dict) and "filtered_questions" in loaded_data:
                            existing_results = loaded_data["filtered_questions"]
                        elif isinstance(loaded_data, list):
                            existing_results = loaded_data
                
                # 合并新结果（避免重复）
                with self.results_lock:
                    # 记录新结果数量
                    new_results_count = len(self.filtered_questions)
                    # 只保存新添加的结果，避免重复
                    all_filtered_questions = existing_results + self.filtered_questions
                    final_stats = self.stats.copy()
                    # 清空已保存的结果，避免下次重复保存
                    self.filtered_questions = []
                
                # 写入文件
                result = {
                    "filtered_questions": all_filtered_questions,
                    "statistics": final_stats,
                    "last_updated": datetime.now().isoformat(),
                    "interrupted": self.interrupted
                }
                
                with open(self.output_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                self.logger.info(f"已保存 {len(existing_results)} 个现有结果 + {new_results_count} 个新结果到 {self.output_file}")
                print(f"已保存 {len(existing_results)} 个现有结果 + {new_results_count} 个新结果到 {self.output_file}")
                
            except Exception as e:
                self.logger.error(f"保存结果时出错: {e}")
                print(f"保存结果时出错: {e}")
    
    def is_interrupted(self) -> bool:
        """检查是否被中断"""
        return self.interrupted
    
    def should_save(self, completed_count: int) -> bool:
        """判断是否应该保存（基于数量）"""
        # 每50个问题保存一次
        return completed_count % 50 == 0
    
    def smart_save(self, completed_count: int):
        """智能保存：根据数量决定是否保存"""
        if self.should_save(completed_count):
            self.save_results()


def setup_logging(log_file: str = None) -> logging.Logger:
    """
    设置日志记录
    
    Args:
        log_file: 日志文件路径，如果为None则使用默认路径
        
    Returns:
        配置好的logger
    """
    if log_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"logs/filter_questions_{timestamp}.log"
    
    # 创建logger
    logger = logging.getLogger('filter_questions')
    logger.setLevel(logging.INFO)
    
    # 清除已有的处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 创建文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 创建格式器
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 添加处理器到logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def load_pipeline_results(file_path: str) -> List[Dict[str, Any]]:
    """
    加载pipeline_results.json文件
    
    Args:
        file_path: JSON文件路径
        
    Returns:
        问题列表
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 如果数据是单个对象，转换为列表
    if isinstance(data, dict):
        return [data]
    return data


def get_question_info(question_data: Dict[str, Any], question_type: str = "rewritten") -> Tuple[str, str, List[str]]:
    """
    从问题数据中提取问题、答案和支持事实
    
    Args:
        question_data: 单个问题的数据
        question_type: 问题类型 ("rewritten", "new_fact_question", "mixed_fact_question")
        
    Returns:
        (问题, 答案, 支持事实列表)
    """
    if question_type == "rewritten":
        question = question_data.get('rewritten', {}).get('question', '')
        answer = question_data.get('rewritten', {}).get('answer', '')
        
        supporting_facts = []
        facts_list = question_data.get('analysis', {}).get('supporting_facts', [])
        for fact_item in facts_list:
            if isinstance(fact_item, dict) and 'fact' in fact_item:
                supporting_facts.append(fact_item['fact'])
    
    elif question_type == "new_fact_question":
        question = question_data.get('new_fact_question', {}).get('question', '')
        answer = question_data.get('new_fact_question', {}).get('answer', '')
        
        supporting_facts = []
        facts_list = question_data.get('new_fact_question', {}).get('supporting_facts', [])
        for fact_item in facts_list:
            if isinstance(fact_item, dict) and 'fact' in fact_item:
                supporting_facts.append(fact_item['fact'])
            elif isinstance(fact_item, str):
                supporting_facts.append(fact_item)
    
    elif question_type == "mixed_fact_question":
        question = question_data.get('mixed_fact_question', {}).get('question', '')
        answer = question_data.get('mixed_fact_question', {}).get('answer', '')
        
        supporting_facts = []
        facts_list = question_data.get('mixed_fact_question', {}).get('supporting_facts', [])
        for fact_item in facts_list:
            if isinstance(fact_item, str):
                supporting_facts.append(fact_item)
            elif isinstance(fact_item, dict) and 'fact' in fact_item:
                supporting_facts.append(fact_item['fact'])
    
    else:
        raise ValueError(f"不支持的问题类型: {question_type}")
    
    return question, answer, supporting_facts


def ask_question_with_model(question: str, supporting_facts: List[str] = None, model: str = "Qwen/Qwen3-32B", logger: logging.Logger = None) -> str:
    """
    使用指定模型回答问题
    
    Args:
        question: 问题文本
        supporting_facts: 支持事实列表（可选）
        model: 模型名称
        logger: 日志记录器
        
    Returns:
        模型的回答
    """
    if supporting_facts:
        facts_text = "\n".join([f"- {fact}" for fact in supporting_facts])
        prompt = f"""请基于以下支持事实回答问题：

支持事实：
{facts_text}

问题：
{question}

请直接给出你的答案："""
        
        if logger:
            logger.info(f"[{model}] 回答问题（有支持事实）")
            logger.info(f"问题: {question}")
            logger.info(f"支持事实: {facts_text}")
    else:
        prompt = f"""请回答以下生物领域的问题：

{question}

仔细思考，再给出回答"""
        
        if logger:
            logger.info(f"[{model}] 回答问题（无支持事实）")
            logger.info(f"问题: {question}")
    
    messages = [
        {"role": "user", "content": prompt}
    ]
    
    response, token_info = call_qwen_chat(messages, model=model, temperature=0.1)
    
    if logger:
        logger.info(f"[{model}] 回答: {response if response else '(无回答)'}")
        logger.info(f"[{model}] Token使用: 输入{token_info['input_tokens']}, 输出{token_info['output_tokens']}, 总计{token_info['total_tokens']}")
    
    return response if response else ""


def judge_answer_correctness(question: str, model_answer: str, correct_answer: str, 
                           supporting_facts: List[str] = None, model: str = "Qwen/QwQ-32B", logger: logging.Logger = None) -> bool:
    """
    使用指定模型判断答案是否正确
    
    Args:
        question: 问题文本
        model_answer: 模型的回答
        correct_answer: 正确答案
        supporting_facts: 支持事实列表（可选）
        model: 判断模型名称
        logger: 日志记录器
        
    Returns:
        是否正确
    """
    prompt = f"""请判断模型回答是否正确。

    问题：
    {question}

    正确答案：
    {correct_answer}

    模型回答：
    {model_answer}

    请只回答"正确"或"错误"："""
    
    if logger:
        logger.info(f"[{model}] 判断答案正确性")
        logger.info(f"问题: {question}")
        logger.info(f"正确答案: {correct_answer}")
        logger.info(f"模型回答: {model_answer}")
    
    messages = [
        {"role": "user", "content": prompt}
    ]
    
    response, token_info = call_qwen_chat(messages, model=model, temperature=0.1)
    
    if not response:
        if logger:
            logger.warning(f"[{model}] 判断失败，无回答")
        return False
    
    # 判断回答是否包含"正确"
    is_correct = "正确" in response
    
    if logger:
        logger.info(f"[{model}] 判断结果: {response} -> {'正确' if is_correct else '错误'}")
        logger.info(f"[{model}] Token使用: 输入{token_info['input_tokens']}, 输出{token_info['output_tokens']}, 总计{token_info['total_tokens']}")
    
    return is_correct


def process_single_question(question_data: Dict[str, Any], question_types: List[str], answer_model: str, judge_model: str, logger: logging.Logger, question_index: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    处理单个问题的所有类型
    
    Args:
        question_data: 单个问题的数据
        question_types: 要处理的问题类型列表
        answer_model: 回答问题的模型名称
        judge_model: 判断答案正确性的模型名称
        logger: 日志记录器
        question_index: 问题索引
        
    Returns:
        (过滤后的问题列表, 统计信息)
    """
    filtered_questions = []
    stats = {
        "processed": 0,
        "without_facts_wrong": 0,
        "with_facts_correct": 0,
        "filtered": 0,
        "errors": 0,
        "by_type": {
            "rewritten": {"processed": 0, "filtered": 0},
            "new_fact_question": {"processed": 0, "filtered": 0},
            "mixed_fact_question": {"processed": 0, "filtered": 0}
        }
    }
    
    try:
        logger.info(f"处理问题 {question_index}")
        
        # 处理每种类型的问题
        for question_type in question_types:
            try:
                logger.info(f"--- 处理 {question_type} 类型问题 ---")
                
                # 提取问题信息
                question, correct_answer, supporting_facts = get_question_info(question_data, question_type)
                
                if not question or not correct_answer:
                    logger.warning(f"跳过 {question_type}：缺少问题或答案")
                    continue
                
                stats["processed"] += 1
                stats["by_type"][question_type]["processed"] += 1
                logger.info(f"问题类型: {question_type}")
                logger.info(f"问题: {question}")
                logger.info(f"正确答案: {correct_answer}")
                logger.info(f"支持事实数量: {len(supporting_facts)}")
                
                # 阶段1：没有supporting facts时回答问题
                logger.info("--- 阶段1：无支持事实回答问题 ---")
                answer_without_facts = ask_question_with_model(question, model=answer_model, logger=logger)
                time.sleep(0.5)  # 减少延迟
                
                # 判断阶段1答案是否正确
                is_correct_without_facts = judge_answer_correctness(
                    question, answer_without_facts, correct_answer, model=judge_model, logger=logger
                )
                time.sleep(0.5)
                
                if is_correct_without_facts:
                    logger.info("阶段1：答案正确，跳过此问题")
                    continue
                
                stats["without_facts_wrong"] += 1
                logger.info("阶段1：答案错误，继续阶段2")
                
                # 阶段2：有supporting facts时回答问题
                logger.info("--- 阶段2：有支持事实回答问题 ---")
                answer_with_facts = ask_question_with_model(
                    question, supporting_facts, model=answer_model, logger=logger
                )
                time.sleep(0.5)
                
                # 判断阶段2答案是否正确
                is_correct_with_facts = judge_answer_correctness(
                    question, answer_with_facts, correct_answer, supporting_facts, model=judge_model, logger=logger
                )
                time.sleep(0.5)
                
                if is_correct_with_facts:
                    stats["with_facts_correct"] += 1
                    stats["filtered"] += 1
                    stats["by_type"][question_type]["filtered"] += 1
                    
                    # 保存过滤后的问题
                    filtered_question = {
                        "question_type": question_type,
                        "original_data": question_data,
                        "test_results": {
                            "without_facts": {
                                "answer": answer_without_facts,
                                "correct": is_correct_without_facts
                            },
                            "with_facts": {
                                "answer": answer_with_facts,
                                "correct": is_correct_with_facts
                            }
                        }
                    }
                    filtered_questions.append(filtered_question)
                    logger.info(f"✓ {question_type} 问题通过过滤")
                else:
                    logger.info("阶段2：答案仍错误，跳过此问题")
                    
            except Exception as e:
                logger.error(f"处理 {question_type} 问题时出错：{e}")
                stats["errors"] += 1
                continue
                
    except Exception as e:
        logger.error(f"处理问题时出错：{e}")
        stats["errors"] += 1
    
    return filtered_questions, stats


def filter_questions(pipeline_file: str, output_file: str = None, answer_model:str='gpt-4o-mini', judge_model:str='gpt-4o-mini', log_file: str = None, question_types: List[str] = None, max_workers: int = 5) -> Dict[str, Any]:
    """
    过滤问题：保留那些在没有supporting facts时回答错误，但在有supporting facts时回答正确的问题
    
    Args:
        pipeline_file: pipeline_results.json文件路径
        output_file: 输出文件路径（可选）
        answer_model: 回答问题的模型名称
        judge_model: 判断答案正确性的模型名称
        log_file: 日志文件路径（可选）
        question_types: 要过滤的问题类型列表，默认为["rewritten", "new_fact_question", "mixed_fact_question"]
        max_workers: 最大线程数，默认为5
        
    Returns:
        过滤结果统计
    """
    # 设置默认问题类型
    if question_types is None:
        question_types = ["rewritten", "new_fact_question", "mixed_fact_question"]
    
    # 设置日志
    logger = setup_logging(log_file)
    logger.info("=" * 50)
    logger.info("开始过滤问题")
    logger.info(f"输入文件: {pipeline_file}")
    logger.info(f"输出文件: {output_file}")
    logger.info(f"回答模型: {answer_model}")
    logger.info(f"判断模型: {judge_model}")
    logger.info(f"问题类型: {question_types}")
    logger.info("=" * 50)
    
    print("开始加载问题数据...")
    questions_data = load_pipeline_results(pipeline_file)
    print(f"共加载 {len(questions_data)} 个问题")
    logger.info(f"共加载 {len(questions_data)} 个问题")
    
    # 创建线程安全的结果保存器
    result_saver = ThreadSafeResultSaver(output_file, logger) if output_file else None
    if result_saver:
        result_saver.set_total_questions(len(questions_data))
    
    # 多线程处理
    print(f"使用 {max_workers} 个线程并行处理问题...")
    logger.info(f"使用 {max_workers} 个线程并行处理问题")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_index = {
            executor.submit(process_single_question, question_data, question_types, answer_model, judge_model, logger, i): i
            for i, question_data in enumerate(questions_data)
        }
        
        # 收集结果
        completed_count = 0
        for future in as_completed(future_to_index):
            # 检查是否被中断
            if result_saver and result_saver.is_interrupted():
                print("检测到中断信号，停止处理新任务...")
                break
                
            question_index = future_to_index[future]
            completed_count += 1
            
            try:
                question_filtered, question_stats = future.result()
                
                # 使用线程安全保存器添加结果
                if result_saver:
                    result_saver.add_results(question_filtered, question_stats)
                    # 智能保存：每10个问题保存一次
                    result_saver.smart_save(completed_count)
                
                print(f"完成问题 {question_index + 1}/{len(questions_data)} (进度: {completed_count}/{len(questions_data)})")
                logger.info(f"完成问题 {question_index + 1}/{len(questions_data)}")
                
            except Exception as e:
                print(f"处理问题 {question_index + 1} 时出错：{e}")
                logger.error(f"处理问题 {question_index + 1} 时出错：{e}")
                if result_saver:
                    error_stats = {"processed": 0, "without_facts_wrong": 0, "with_facts_correct": 0, "filtered": 0, "errors": 1, "by_type": {}}
                    result_saver.add_results([], error_stats)
    
    # 最终保存（如果使用保存器的话，结果已经实时保存了）
    if result_saver:
        result_saver.save_results()  # 最终保存一次，确保所有数据都写入
        final_stats = result_saver.stats
        print(f"\n结果已保存到：{output_file}")
        logger.info(f"结果已保存到：{output_file}")
    else:
        # 如果没有使用保存器，使用原来的逻辑
        final_stats = {
            "total_questions": len(questions_data),
            "processed": 0,
            "without_facts_wrong": 0,
            "with_facts_correct": 0,
            "filtered": 0,
            "errors": 0,
            "by_type": {
                "rewritten": {"processed": 0, "filtered": 0},
                "new_fact_question": {"processed": 0, "filtered": 0},
                "mixed_fact_question": {"processed": 0, "filtered": 0}
            }
        }
    
    # 打印统计信息
    print(f"\n=== 过滤统计 ===")
    print(f"总问题数：{final_stats['total_questions']}")
    print(f"已处理：{final_stats['processed']}")
    print(f"阶段1错误：{final_stats['without_facts_wrong']}")
    print(f"阶段2正确：{final_stats['with_facts_correct']}")
    print(f"通过过滤：{final_stats['filtered']}")
    print(f"处理错误：{final_stats['errors']}")
    
    print(f"\n=== 按类型统计 ===")
    for question_type, type_stats in final_stats['by_type'].items():
        print(f"{question_type}: 处理 {type_stats['processed']}, 通过 {type_stats['filtered']}")
    
    # 记录统计信息到日志
    logger.info("=" * 50)
    logger.info("过滤完成 - 统计信息")
    logger.info(f"总问题数：{final_stats['total_questions']}")
    logger.info(f"已处理：{final_stats['processed']}")
    logger.info(f"阶段1错误：{final_stats['without_facts_wrong']}")
    logger.info(f"阶段2正确：{final_stats['with_facts_correct']}")
    logger.info(f"通过过滤：{final_stats['filtered']}")
    logger.info(f"处理错误：{final_stats['errors']}")
    
    logger.info("按类型统计:")
    for question_type, type_stats in final_stats['by_type'].items():
        logger.info(f"  {question_type}: 处理 {type_stats['processed']}, 通过 {type_stats['filtered']}")
    logger.info("=" * 50)
    
    return final_stats


if __name__ == "__main__":
    # 运行过滤
    stats = filter_questions(
        pipeline_file="pipeline_results_20250913_0035.json",
        output_file="filtered_questions.json",
        answer_model="qwen2.5-72b-instruct",
        judge_model="qwen2.5-72b-instruct",
        max_workers=10  # 使用5个线程并行处理
    )
