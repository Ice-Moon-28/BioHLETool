#!/usr/bin/env python3
"""
生物医学题目生成Pipeline
基于extract_prompt.py中定义的流程，实现题目知识提取、重写和扩展功能
"""

from curses import raw
import json
import os
import logging
import threading
import signal
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# 导入现有的工具和LLM配置
from tools.llm_call import chat_with_tools, call_openai_chat
from tools.llm_config import OPENAI_TOOLS
from tools.tool_router import execute_tool
from prompts.extract_info_prompts import GENERATE_QUESTION_NEW_FACT
# 导入新的agents
from extract_fact_agent import ExtractFactAgent
from search_info_agent import SearchInfoAgent, FactWithSource


@dataclass
class QuestionAnalysis:
    """题目分析结果"""
    raw_question: str
    subdomain: str
    supporting_facts:  List[Dict[str, str]]


@dataclass
class RewrittenQuestion:
    """
    重写后的题目
    """
    question: str
    answer: str
    rationale: str


@dataclass
class ExtendedQuestion:
    """
    扩展后的题目
    """
    question: str
    answer: str
    rationale: str
    supporting_facts: List[str]
    new_facts_added: List[str]


@dataclass
class NewFactQuestion:
    """
    基于新事实生成的题目
    """
    question: str
    answer: str
    rationale: str
    supporting_facts: List[Dict[str, Any]]


@dataclass
class MixedFactQuestion:
    """
    基于混合事实生成的题目
    """
    question: str
    answer: str
    rationale: str
    supporting_facts: List[str]


class BioQuestionPipeline:
    """
    生物医学题目生成Pipeline
    """
    
    def __init__(self, model: str = "gpt-5", debug: bool = False):
        self.model = model
        self.tools = OPENAI_TOOLS
        self.debug = debug
        
        # 初始化日志记录
        self._setup_logging()
        
        # 初始化新的agents
        self.extract_agent = ExtractFactAgent(model=model)
        self.search_agent = SearchInfoAgent(model=model)
        
        # 多线程相关
        self.results_lock = threading.Lock()
        self.file_lock = threading.Lock()
        self.processed_results = []
        self.interrupted = False
        
        # Token统计
        self.token_stats = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "call_count": 0
        }
    
    def _setup_logging(self):
        """设置日志记录"""
        # 创建日志目录
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 创建日志文件名（包含时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        info_log_file = os.path.join(log_dir, f"pipeline_info_{timestamp}.log")
        debug_log_file = os.path.join(log_dir, f"pipeline_debug_{timestamp}.log")
        
        # 配置根日志记录器，确保所有子模块都使用同一个日志文件
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # 清除现有的处理器
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 创建INFO级别文件处理器（只记录INFO及以上级别）
        info_file_handler = logging.FileHandler(info_log_file, encoding='utf-8')
        info_file_handler.setLevel(logging.INFO)
        
        # 创建DEBUG级别文件处理器（记录所有级别）
        debug_file_handler = logging.FileHandler(debug_log_file, encoding='utf-8')
        debug_file_handler.setLevel(logging.DEBUG)
        
        # 创建控制台处理器（只显示INFO及以上级别）
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 设置日志格式
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        info_file_handler.setFormatter(formatter)
        debug_file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加处理器到根日志记录器
        root_logger.addHandler(info_file_handler)
        root_logger.addHandler(debug_file_handler)
        root_logger.addHandler(console_handler)
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"日志记录已启动")
        self.logger.info(f"INFO级别日志文件: {info_log_file}")
        self.logger.info(f"DEBUG级别日志文件: {debug_log_file}")
        self.log_file = info_log_file  # 主要日志文件
        self.debug_log_file = debug_log_file
        
        # 设置中断信号处理
        if not self.debug:
            signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """处理Ctrl+C中断信号"""
        self.logger.info("接收到中断信号，正在保存已处理的结果...")
        print("\n接收到中断信号，正在保存已处理的结果...")
        self.interrupted = True
        # 使用带时间戳的文件名保存结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"pipeline_results_interrupted_{timestamp}.json"
        self._save_results(output_file)
        sys.exit(0)
    
    def _save_results(self, output_file: str = "pipeline_results.json"):
        """保存处理结果到文件（线程安全）"""
        with self.file_lock:
            try:
                # 读取现有结果
                existing_results = []
                if os.path.exists(output_file):
                    with open(output_file, 'r', encoding='utf-8') as f:
                        loaded_data = json.load(f)
                        # 确保existing_results是列表格式
                        if isinstance(loaded_data, list):
                            existing_results = loaded_data
                        elif isinstance(loaded_data, dict):
                            # 如果是字典，将其作为单个结果添加到列表中
                            existing_results = [loaded_data]
                        else:
                            existing_results = []
                
                # 合并新结果
                with self.results_lock:
                    all_results = existing_results + self.processed_results
                
                # 写入文件
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(all_results, f, ensure_ascii=False, indent=2)
                
                self.logger.info(f"已保存 {len(self.processed_results)} 个结果到 {output_file}")
                print(f"已保存 {len(self.processed_results)} 个结果到 {output_file}")
                
            except Exception as e:
                self.logger.error(f"保存结果时出错: {e}", exc_info=True)
                print(f"保存结果时出错: {e}")
    
    def _add_result(self, result: Dict[str, Any]):
        """线程安全地添加结果到列表"""
        with self.results_lock:
            self.processed_results.append(result)
    
    def _update_token_stats(self, token_info: Dict[str, int]):
        """更新token统计信息"""
        with self.results_lock:
            self.token_stats["total_input_tokens"] += token_info.get("input_tokens", 0)
            self.token_stats["total_output_tokens"] += token_info.get("output_tokens", 0)
            self.token_stats["total_tokens"] += token_info.get("total_tokens", 0)
            self.token_stats["call_count"] += 1
    
    def get_token_stats(self) -> Dict[str, int]:
        """获取token统计信息"""
        with self.results_lock:
            return self.token_stats.copy()
    
    def print_token_stats(self):
        """打印token统计信息"""
        stats = self.get_token_stats()
        print("\n=== Token使用统计 ===")
        print(f"总调用次数: {stats['call_count']}")
        print(f"总输入Token: {stats['total_input_tokens']:,}")
        print(f"总输出Token: {stats['total_output_tokens']:,}")
        print(f"总Token: {stats['total_tokens']:,}")
        if stats['call_count'] > 0:
            print(f"平均每次调用Token: {stats['total_tokens'] / stats['call_count']:.1f}")
            print(f"平均输入Token: {stats['total_input_tokens'] / stats['call_count']:.1f}")
            print(f"平均输出Token: {stats['total_output_tokens'] / stats['call_count']:.1f}")
    
    def _extract_json_from_response(self, response: str) -> str:
        """
        智能提取响应中的JSON内容
        处理```json代码块或纯JSON格式
        """
        response = response.strip()
        
        # 检查是否包含```json代码块
        if "```json" in response:
            # 提取```json和```之间的内容
            start_marker = "```json"
            end_marker = "```"
            
            start_idx = response.find(start_marker)
            if start_idx != -1:
                start_idx += len(start_marker)
                end_idx = response.find(end_marker, start_idx)
                if end_idx != -1:
                    return response[start_idx:end_idx].strip()
        
        # 检查是否包含```代码块（没有json标记）
        elif "```" in response:
            # 提取```和```之间的内容
            start_marker = "```"
            end_marker = "```"
            
            start_idx = response.find(start_marker)
            if start_idx != -1:
                start_idx += len(start_marker)
                end_idx = response.find(end_marker, start_idx)
                if end_idx != -1:
                    return response[start_idx:end_idx].strip()
        
        # 如果没有代码块标记，直接返回原响应
        return response
        
    def extract_knowledge(self, question: str, rationale: str, answer: str = "", raw_subject: str = "Biology") -> QuestionAnalysis:
        """
        步骤1: 使用extract_fact_agent从问题中提取相关知识
        包括：问题所属的subdomain、问题所有涉及的supporting facts、问题涉及的易错点（可选）
        """
        # 构造题目数据格式
        question_data = {
            "id": "pipeline_extraction",
            "question": question,
            "rationale": rationale,
            "raw_subject": raw_subject,
            "answer": answer
        }
        
        # 使用extract_fact_agent处理
        result = self.extract_agent.process_single_question(question_data)
        
        # 获取并更新token统计
        extract_token_stats = result.get('token_stats', {})
        if extract_token_stats:
            self._update_token_stats(extract_token_stats)
            self.logger.info(f"ExtractFactAgent Token使用: 输入{extract_token_stats.get('input_tokens', 0)}, 输出{extract_token_stats.get('output_tokens', 0)}, 总计{extract_token_stats.get('total_tokens', 0)}")
        
        # 提取子领域
        subdomain = ' '.join(result['extracted_subdomains']) if result['extracted_subdomains'] else "未知"
        
        # 获取supporting facts，为每个fact添加出处信息
        supporting_facts = []
        for fact in result['supporting_facts']:
            if isinstance(fact, str):
                supporting_facts.append({
                    "fact": fact,
                    "source": "raw_question",
                    "source_detail": "原始题目rationale中提取"
                })
            elif isinstance(fact, dict):
                # 如果已经是字典格式，确保有source字段
                processed_fact = fact.copy()
                if "source" not in processed_fact:
                    processed_fact["source"] = "raw_question"
                    processed_fact["source_detail"] = "原始题目rationale中提取"
                supporting_facts.append(processed_fact)
        
        
        return QuestionAnalysis(
            raw_question=question,
            subdomain=subdomain,
            supporting_facts=supporting_facts,
        )
    
    
    def rewrite_question(self, analysis: QuestionAnalysis) -> RewrittenQuestion:
        """
        步骤2: 基于subdomain和supporting facts重写题目
        与原问题的语言描述风格不同，问法不同
        """
        system_prompt = """You are a biology professor at a university. To exercise students' ability to think flexibly and apply knowledge, please rewrite a new question based on the original question, given subdomain, and supporting facts.

Requirements:
1. Use a different language description style from the original question
2. Change the question type, for example, if the original question is multiple choice, the new question should become fill-in-the-blank; if the original is fill-in-the-blank, the new question should become multiple choice.
3. Keep the knowledge points consistent
4. Provide clear solution approach

Please return in JSON format:
{{
    "question": "Rewritten question",
    "answer": "Question answer",
    "rationale": "Solution approach"
}}"""

        supporting_facts_text = "\n".join([f"- {fact}" for fact in analysis.supporting_facts])
        
        user_prompt = f"""Please rewrite a question based on the following information:

Original question: {analysis.raw_question}
Subdomain: {analysis.subdomain}
Supporting facts:
{supporting_facts_text}

Please generate a new question."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response, token_info = call_openai_chat(messages, model=self.model)
        self._update_token_stats(token_info)
        self.logger.info(f"重写题目Token使用: 输入{token_info['input_tokens']}, 输出{token_info['output_tokens']}, 总计{token_info['total_tokens']}")
        
        try:
            # 智能提取JSON内容
            json_content = self._extract_json_from_response(response)
            rewrite_data = json.loads(json_content)
            return RewrittenQuestion(
                question=rewrite_data.get("question", ""),
                answer=rewrite_data.get("answer", ""),
                rationale=rewrite_data.get("rationale", "")
            )
        except json.JSONDecodeError:
            print(f"重写题目JSON解析失败，原始响应: {response}")
            return RewrittenQuestion(
                question="重写失败",
                answer="解析错误",
                rationale="解析错误"
            )
    
    def search_related_facts(self, supporting_facts: List[Dict[str, str]], subdomain: str) -> Tuple[List[FactWithSource], List[str]]:
        """
        使用search_info_agent搜索与supporting facts相关的新事实
        
        Returns:
            Tuple[List[FactWithSource], List[str]]: (新事实列表, 提取的概念列表)
        """
        self.logger.info(f"开始搜索相关事实，子领域: {subdomain}")
        self.logger.debug(f"输入supporting_facts: {supporting_facts}")
        
        try:
            # 提取fact文本用于搜索
            fact_texts = []
            for i, fact in enumerate(supporting_facts):
                self.logger.debug(f"处理第{i+1}个fact: {fact}")
                if isinstance(fact, dict) and 'fact' in fact:
                    fact_texts.append(fact['fact'])
                    self.logger.debug(f"提取fact文本: {fact['fact']}")
                elif isinstance(fact, str):
                    fact_texts.append(fact)
                    self.logger.debug(f"直接使用fact文本: {fact}")
                else:
                    self.logger.warning(f"未知的fact格式: {type(fact)} - {fact}")
            
            self.logger.info(f"提取到{len(fact_texts)}个fact文本用于搜索")
            self.logger.debug(f"fact_texts: {fact_texts}")
            
            # 使用search_info_agent进行搜索和提取
            self.logger.info("调用search_agent.run方法")
            search_result = self.search_agent.run(
                subdomain=subdomain,
                supporting_facts=fact_texts,
                k=2,  # 每个概念搜索2个结果
                n=5   # 每个网页提取5个facts
            )
            
            self.logger.info("search_agent.run完成")
            self.logger.debug(f"search_result keys: {list(search_result.keys()) if isinstance(search_result, dict) else 'Not a dict'}")
            
            # 直接返回search_agent的结果，它已经包含了出处信息
            final_facts = search_result.get('final_facts', [])
            extracted_concepts = search_result.get('extracted_concepts', [])
            self.logger.info(f"获取到{len(final_facts)}个最终事实")
            self.logger.info(f"获取到{len(extracted_concepts)}个提取概念")
            
            # 获取并更新token统计
            search_token_stats = search_result.get('token_stats', {})
            if search_token_stats:
                self._update_token_stats(search_token_stats)
                self.logger.info(f"SearchInfoAgent Token使用: 输入{search_token_stats.get('input_tokens', 0)}, 输出{search_token_stats.get('output_tokens', 0)}, 总计{search_token_stats.get('total_tokens', 0)}")
            
            # 记录每个fact的详细信息
            for i, fact in enumerate(final_facts):
                self.logger.debug(f"最终事实{i+1}: {fact}")
            
            return final_facts[:5], extracted_concepts  # 最多返回5个新事实和所有提取的概念
            
        except Exception as e:
            self.logger.error(f"使用search_info_agent搜索事实时出错: {e}", exc_info=True)
            print(f"使用search_info_agent搜索事实时出错: {e}")
            # 如果search_agent失败，返回空列表
            return [], []
    
    
    def generate_question_with_new_facts_only(self, original_question: str, original_rationale: str, 
                                            new_facts: List[FactWithSource], subdomain: str) -> NewFactQuestion:
        """
        仅使用新事实生成题型、格式类似的问题
        """
        system_prompt = GENERATE_QUESTION_NEW_FACT

        new_facts_text = "\n".join([f"- {fact.fact} (来源: {fact.source_detail})" for fact in new_facts])
        
        user_prompt = f"""Please generate a new question based on the following information:

Original question: {original_question}

Subdomain: {subdomain}

Provided facts:
{new_facts_text}

Please generate a challenging question that is only based on new facts"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response, token_info = call_openai_chat(messages, model=self.model)
        self._update_token_stats(token_info)
        self.logger.info(f"生成新事实题目Token使用: 输入{token_info['input_tokens']}, 输出{token_info['output_tokens']}, 总计{token_info['total_tokens']}")
        
        try:
            json_content = self._extract_json_from_response(response)
            data = json.loads(json_content)
            return NewFactQuestion(
                question=data.get("question", ""),
                answer=data.get("answer", ""),
                rationale=data.get("rationale", ""),
                supporting_facts=[{
                    "fact": fact.fact,
                    "source_detail": fact.source_detail,
                    "source_url": fact.source_url,
                    "source_title": fact.source_title
                } for fact in new_facts]
            )
        except json.JSONDecodeError:
            print(f"生成新事实题目JSON解析失败，原始响应: {response}")
            return NewFactQuestion(
                question="生成失败",
                answer="解析错误",
                rationale="解析错误",
                supporting_facts=[{
                    "fact": fact.fact,
                    "source_detail": fact.source_detail,
                    "source_url": fact.source_url,
                    "source_title": fact.source_title
                } for fact in new_facts]
            )
    
    def generate_question_with_mixed_facts(self, original_question: str, original_rationale: str,
                                         original_facts: List[Dict[str, str]], original_answer:str, new_facts: List[FactWithSource], 
                                         subdomain: str) -> MixedFactQuestion:
        """
        从新事实和已有supporting fact的并集中选择适量事实生成题型、格式类似的问题
        """
        system_prompt = """You are a biology professor at a university. Please select an appropriate number of knowledge points from the union of original knowledge points and new knowledge points to generate a new question.

Requirements:
1. Modify the existing question type, for example, if the original question is multiple choice, you should make it fill-in-the-blank; if the original question is fill-in-the-blank, you should make it multiple choice
2. Maintain similar format and structure, but allow for appropriate innovation, making the question as challenging as possible
3. Do not plagiarize existing questions! Make it as different as possible from the original question, but ensure using at least one original knowledge point.
4. Provide clear solution approach
5. Clearly mark which knowledge points are used

Please return in JSON format:
{{
    "question": "New question",
    "answer": "Question answer",
    "rationale": "Solution approach and answer",
    "supporting_facts": ["All supporting facts (knowledge points) used"]
}}"""

        original_facts_text = "\n".join([f"- {fact['fact'] if isinstance(fact, dict) else fact}" for fact in original_facts])
        new_facts_text = "\n".join([f"- {fact.fact} (来源: {fact.source_detail})" for fact in new_facts])
        
        user_prompt = f"""Please generate a new question based on the following information:

Original question: {original_question}
Subdomain: {subdomain}
Original answer: {original_answer}
Original answer explanation: {original_rationale}

Extracted original supporting facts (knowledge points):
{original_facts_text}
Newly added knowledge points:
{new_facts_text}

The question you generate is:"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response, token_info = call_openai_chat(messages, model=self.model)
        self._update_token_stats(token_info)
        self.logger.info(f"生成混合事实题目Token使用: 输入{token_info['input_tokens']}, 输出{token_info['output_tokens']}, 总计{token_info['total_tokens']}")
        
        try:
            json_content = self._extract_json_from_response(response)
            data = json.loads(json_content)
            return MixedFactQuestion(
                question=data.get("question", ""),
                answer=data.get("answer", ""),
                rationale=data.get("rationale", ""),
                supporting_facts=data.get("supporting_facts", []),
            )
        except json.JSONDecodeError:
            print(f"生成混合事实题目JSON解析失败，原始响应: {response}")
            return MixedFactQuestion(
                question="生成失败",
                answer="解析错误",
                rationale="解析错误",
                supporting_facts=original_facts + new_facts
            )
    
    def extend_question_with_facts(self, rewritten_question: RewrittenQuestion, 
                                 original_facts: List[str], new_facts: List[str]) -> ExtendedQuestion:
        """
        步骤3: 基于扩展的supporting facts生成更难的题目
        """
        system_prompt = """You are a biomedical education expert. Please generate a more difficult question based on the original supporting facts and newly discovered related facts.

Requirements:
1. Integrate the original supporting facts and newly discovered facts
2. Increase the difficulty of the question, which may require synthesizing multiple knowledge points
3. Maintain the scientific nature and accuracy of the question
4. Provide detailed solution approach

Please return in JSON format:
{{
    "question": "Extended question",
    "answer": "Question answer",
    "rationale": "Detailed solution approach",
    "supporting_facts": ["All relevant supporting facts"],
    "new_facts_added": ["Newly added facts"]
}}"""

        original_facts_text = "\n".join([f"- {fact}" for fact in original_facts])
        new_facts_text = "\n".join([f"- {fact}" for fact in new_facts])
        
        user_prompt = f"""Please generate a more difficult question based on the following information:

Original question: {rewritten_question.question}

Original solution: {rewritten_question.rationale}

Original supporting facts:
{original_facts_text}

Other facts obtained through search:
{new_facts_text}

Please generate a more difficult question that integrates these facts."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response, token_info = call_openai_chat(messages, model=self.model)
        self._update_token_stats(token_info)
        self.logger.info(f"扩展题目Token使用: 输入{token_info['input_tokens']}, 输出{token_info['output_tokens']}, 总计{token_info['total_tokens']}")
        
        try:
            # 智能提取JSON内容
            json_content = self._extract_json_from_response(response)
            extend_data = json.loads(json_content)
            return ExtendedQuestion(
                question=extend_data.get("question", ""),
                answer=extend_data.get("answer", ""),
                rationale=extend_data.get("rationale", ""),
                supporting_facts=extend_data.get("supporting_facts", []),
                new_facts_added=extend_data.get("new_facts_added", [])
            )
        except json.JSONDecodeError:
            print(f"扩展题目JSON解析失败，原始响应: {response}")
            return ExtendedQuestion(
                question="扩展失败",
                answer="解析错误",
                rationale="解析错误",
                supporting_facts=original_facts + new_facts,
                new_facts_added=new_facts
            )
    
    def run_pipeline(self, question: str, rationale: str, answer: str = "", raw_subject: str = "Biology") -> Dict[str, Any]:
        """
        运行完整的pipeline
        """
        self.logger.info("开始运行生物医学题目生成Pipeline...")
        self.logger.info(f"输入参数 - 题目长度: {len(question)}, 解答长度: {len(rationale)}, 答案: {answer}, 主题: {raw_subject}")
        print("开始运行生物医学题目生成Pipeline...")
        
        # 步骤1: 提取知识
        self.logger.info("步骤1: 提取题目相关知识...")
        print("步骤1: 提取题目相关知识...")
        try:
            analysis = self.extract_knowledge(question, rationale, answer, raw_subject)
            self.logger.info(f"知识提取完成 - 子领域: {analysis.subdomain}, 支撑事实数量: {len(analysis.supporting_facts)}")
            self.logger.info(f"提取的支撑事实: {analysis.supporting_facts}")
            print(f"提取结果: 子领域={analysis.subdomain}, 支撑事实数量={len(analysis.supporting_facts)}")
        except Exception as e:
            self.logger.error(f"知识提取失败: {e}", exc_info=True)
            raise
        
        # 步骤3: 搜索相关新事实
        self.logger.info("步骤3: 搜索相关新事实...")
        print("步骤3: 搜索相关新事实...")
        try:
            new_facts, extracted_concepts = self.search_related_facts(analysis.supporting_facts, analysis.subdomain)
            self.logger.info(f"新事实搜索完成，发现新事实数量: {len(new_facts)}")
            self.logger.info(f"提取概念数量: {len(extracted_concepts)}")
            self.logger.info(f"新事实:{new_facts}")
            self.logger.info(f"提取概念:{extracted_concepts}")
            print(f"发现新事实数量: {len(new_facts)}")
            print(f"提取概念数量: {len(extracted_concepts)}")
        except Exception as e:
            self.logger.error(f"新事实搜索失败: {e}", exc_info=True)
            new_facts = []  # 如果搜索失败，继续执行后续步骤
            extracted_concepts = []  # 如果搜索失败，概念列表也为空
        
        # 步骤4: 扩展题目（原有方法）
        #self.logger.info("步骤4: 基于新事实扩展题目...")
        #print("步骤4: 基于新事实扩展题目...")
        #try:
        #    extended = self.extend_question_with_facts(rewritten, analysis.supporting_facts, new_facts)
        #    self.logger.info("题目扩展完成")
        #    self.logger.info(f"扩展后的题目: {extended.question}")
        #except Exception as e:
        #    self.logger.error(f"题目扩展失败: {e}", exc_info=True)
        #    raise
        
        # 步骤5: 仅使用新事实生成题目
        self.logger.info("步骤5: 仅使用新事实生成题目...")
        print("步骤5: 仅使用新事实生成题目...")
        new_fact_question = None
        if new_facts:
            try:
                new_fact_question = self.generate_question_with_new_facts_only(
                    question, rationale, new_facts, analysis.subdomain
                )
                self.logger.info("新事实题目生成完成")
                self.logger.debug(f"新事实题目: {new_fact_question.question}")
            except Exception as e:
                self.logger.error(f"新事实题目生成失败: {e}", exc_info=True)
        else:
            self.logger.info("没有新事实，跳过新事实题目生成")
            print("没有新事实，跳过新事实题目生成")
        
        # 步骤6: 使用混合事实生成题目
        self.logger.info("步骤6: 使用混合事实生成题目...")
        print("步骤6: 使用混合事实生成题目...")
        mixed_fact_question = None
        if new_facts:
            try:
                mixed_fact_question = self.generate_question_with_mixed_facts(
                    question, rationale, analysis.supporting_facts, answer, new_facts, analysis.subdomain
                )
                self.logger.info("混合事实题目生成完成")
                self.logger.debug(f"混合事实题目: {mixed_fact_question.question}")
            except Exception as e:
                self.logger.error(f"混合事实题目生成失败: {e}", exc_info=True)
        else:
            self.logger.info("没有新事实，跳过混合事实题目生成")
            print("没有新事实，跳过混合事实题目生成")
        
        # 返回完整结果
        result = {
            "original": {
                "question": question,
                "rationale": rationale
            },
            "analysis": {
                "subdomain": analysis.subdomain,
                "supporting_facts": analysis.supporting_facts
            },
            "pipeline_metadata": {
                "model_used": self.model,
                "tools_available": len(self.tools),
                "new_facts_discovered": len(new_facts),
                "extracted_concepts": extracted_concepts
            }
        }
        
        # 添加新的问题生成结果
        if new_fact_question:
            result["new_fact_question"] = {
                "question": new_fact_question.question,
                "answer": new_fact_question.answer,
                "rationale": new_fact_question.rationale,
                "supporting_facts": new_fact_question.supporting_facts
            }
        
        if mixed_fact_question:
            result["mixed_fact_question"] = {
                "question": mixed_fact_question.question,
                "answer": mixed_fact_question.answer,
                "rationale": mixed_fact_question.rationale,
                "supporting_facts": mixed_fact_question.supporting_facts,
            }
        
        # 添加结果到暂存列表
        self._add_result(result)
        
        # 打印token统计
        self.print_token_stats()
        
        return result
    
    def process_single_question(self, question_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理单个问题的包装方法"""
        try:
            question = question_data['question']
            rationale = question_data['rationale']
            answer = question_data.get('answer', '')
            raw_subject = question_data.get('raw_subject', 'Biology')
            
            self.logger.info(f"开始处理问题 ID: {question_data.get('id', 'unknown')}")
            result = self.run_pipeline(question, rationale, answer, raw_subject)
            
            # 添加原始数据信息
            result['original_data'] = {
                'id': question_data.get('id', 'unknown'),
                'category': question_data.get('category', 'unknown'),
                'raw_subject': raw_subject
            }
            
            self.logger.info(f"完成处理问题 ID: {question_data.get('id', 'unknown')}")
            return result
            
        except Exception as e:
            self.logger.error(f"处理问题 {question_data.get('id', 'unknown')} 时出错: {e}", exc_info=True)
            return {
                'error': str(e),
                'original_data': {
                    'id': question_data.get('id', 'unknown'),
                    'category': question_data.get('category', 'unknown'),
                    'raw_subject': question_data.get('raw_subject', 'Biology')
                }
            }
    
    def process_dataset_batch(self, dataset_path: str, max_workers: int = 10, 
                            output_file: str = "pipeline_results.json", 
                            batch_size: int = 10) -> None:
        """批量处理数据集（多线程）"""
        # 加载数据集
        with open(dataset_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        total_questions = len(data)
        self.logger.info(f"开始批量处理 {total_questions} 个问题，使用 {max_workers} 个线程")
        print(f"开始批量处理 {total_questions} 个问题，使用 {max_workers} 个线程")
        
        # 分批处理
        for batch_start in range(0, total_questions, batch_size):
            if self.interrupted:
                self.logger.info("检测到中断信号，停止处理")
                break
                
            batch_end = min(batch_start + batch_size, total_questions)
            batch_data = data[batch_start:batch_end]
            
            self.logger.info(f"处理批次 {batch_start//batch_size + 1}: 问题 {batch_start+1}-{batch_end}")
            print(f"处理批次 {batch_start//batch_size + 1}: 问题 {batch_start+1}-{batch_end}")
            
            # 使用线程池处理当前批次
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交任务
                future_to_data = {
                    executor.submit(self.process_single_question, question_data): question_data 
                    for question_data in batch_data
                }
                
                # 等待完成
                for future in as_completed(future_to_data):
                    if self.interrupted:
                        break
                        
                    question_data = future_to_data[future]
                    try:
                        result = future.result()
                        self.logger.debug(f"完成问题 {question_data.get('id', 'unknown')}")
                    except Exception as e:
                        self.logger.error(f"处理问题 {question_data.get('id', 'unknown')} 时出错: {e}")
            
            # 每批次后保存结果
            if not self.interrupted:
                self._save_results(output_file)
                self.logger.info(f"批次 {batch_start//batch_size + 1} 完成，已保存结果")
                print(f"批次 {batch_start//batch_size + 1} 完成，已保存结果")
        
        if not self.interrupted:
            self.logger.info(f"所有 {total_questions} 个问题处理完成")
            print(f"所有 {total_questions} 个问题处理完成")


def load_sample_from_dataset(dataset_path: str, sample_index: int = 0) -> Tuple[str, str, str, str]:
    """
    从训练数据集中加载样例
    """
    with open(dataset_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if sample_index >= len(data):
        sample_index = 0
    
    sample = data[sample_index]
    question = sample['question']
    rationale = sample['rationale']
    answer = sample.get('answer', '')
    raw_subject = sample.get('raw_subject', 'Biology')
    
    print(f"使用数据集样例 {sample_index + 1}/{len(data)}")
    print(f"题目ID: {sample['id']}")
    print(f"类别: {sample['category']}")
    print(f"主题: {raw_subject}")
    print(f"答案: {answer}")
    
    return question, rationale, answer, raw_subject


def main():
    """
    测试pipeline功能
    """
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='生物医学题目生成Pipeline')
    parser.add_argument('--debug', action='store_true', help='调试模式，只处理第一条数据')
    parser.add_argument('--sample-index', type=int, default=0, help='调试模式下使用的样例索引')
    parser.add_argument('--dataset', type=str, default="dataset/hle/train.json", help='数据集路径')
    parser.add_argument('--output', type=str, default="pipeline_results.json", help='输出文件路径')
    parser.add_argument('--workers', type=int, default=10, help='并发线程数')
    parser.add_argument('--batch-size', type=int, default=10, help='批处理大小')
    
    args = parser.parse_args()
    
    # 创建pipeline实例
    pipeline = BioQuestionPipeline(debug=args.debug)
    
    # 根据模式选择处理方式
    if args.debug:
        # 调试模式：只处理第一条数据
        print("调试模式：只处理第一条数据...")
        sample_question, sample_rationale, sample_answer, sample_subject = load_sample_from_dataset(args.dataset, args.sample_index)
        
        try:
            result = pipeline.run_pipeline(sample_question.strip(), sample_rationale.strip(), sample_answer, sample_subject)
            pipeline.logger.info("Pipeline运行成功完成")
        except Exception as e:
            pipeline.logger.error(f"Pipeline运行失败: {e}", exc_info=True)
            print(f"Pipeline运行失败: {e}")
            raise
        
        # 保存结果（调试模式下保存为列表格式，与批量处理保持一致）
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump([result], f, ensure_ascii=False, indent=2)
        
        print(f"\nPipeline运行完成！结果已保存到 {args.output}")
        print(f"INFO级别日志已保存到: {pipeline.log_file}")
        print(f"DEBUG级别日志已保存到: {pipeline.debug_log_file}")
        
        # 打印关键结果
        print("\n=== 关键结果摘要 ===")
        print(f"子领域: {result['analysis']['subdomain']}")
        print(f"原支撑事实数量: {len(result['analysis']['supporting_facts'])}")
        
        # 打印重写后的题目
        print("\n=== 重写后的题目 ===")
        print(result['rewritten']['question'])
        print(result['rewritten']['rationale'])
        
        # 打印新事实题目
        if 'new_fact_question' in result:
            print("\n=== 仅使用新事实的题目 ===")
            print(result['new_fact_question']['question'])
        
        # 打印混合事实题目
        if 'mixed_fact_question' in result:
            print("\n=== 使用混合事实的题目 ===")
            print(result['mixed_fact_question']['question'])
    
    else:
        # 生产模式：批量处理
        output_file = args.output.split('.')[0] + '_' + datetime.now().strftime("%Y%m%d_%H%M") + '.json'
        print(f"生产模式：批量处理数据集 {args.dataset}")
        print(f"使用 {args.workers} 个线程，批处理大小: {args.batch_size}")
        print(f"结果将保存到: {output_file}")
        print("按 Ctrl+C 可以中断程序并保存已处理的结果")
        
        try:
            pipeline.process_dataset_batch(
                dataset_path=args.dataset,
                max_workers=args.workers,
                output_file=output_file,
                batch_size=args.batch_size
            )
            
            # 最终保存
            pipeline._save_results(output_file)
            
            print(f"\n所有处理完成！结果已保存到 {output_file}")
            print(f"INFO级别日志已保存到: {pipeline.log_file}")
            print(f"DEBUG级别日志已保存到: {pipeline.debug_log_file}")
            
        except KeyboardInterrupt:
            print("\n用户中断程序")
            pipeline._save_results(output_file)
        except Exception as e:
            pipeline.logger.error(f"批量处理失败: {e}", exc_info=True)
            print(f"批量处理失败: {e}")
            pipeline._save_results(output_file)
            raise


if __name__ == "__main__":
    main()
