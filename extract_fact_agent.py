import json
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from tools.llm_call import chat_with_tools


class ExtractFactAgent:
    """
    从HLE训练数据中提取信息的agent
    提取：子领域、supporting facts、相关论文/PDF
    """
    
    def __init__(self, model: str = "Pro/deepseek-ai/DeepSeek-V3.1"):
        self.model = model
        self.logger = logging.getLogger(__name__)
        
        # Token统计
        self.token_stats = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "call_count": 0
        }
    
    def _update_token_stats(self, token_info: Dict[str, int]):
        """更新token统计信息"""
        self.token_stats["total_input_tokens"] += token_info.get("input_tokens", 0)
        self.token_stats["total_output_tokens"] += token_info.get("output_tokens", 0)
        self.token_stats["total_tokens"] += token_info.get("total_tokens", 0)
        self.token_stats["call_count"] += 1

    def get_token_stats(self) -> Dict[str, int]:
        """获取token统计信息"""
        return self.token_stats.copy()
    
    def load_training_data(self, file_path: str) -> List[Dict[str, Any]]:
        """加载训练数据"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    
    def extract_subdomains(self, question: str, rationale: str, raw_subject: str) -> List[str]:
        """
        从题目和思考过程中提取子领域
        
        Args:
            question: 题目内容
            rationale: 思考过程
            raw_subject: 原始学科分类
            
        Returns:
            子领域列表
        """
        prompt = f"""
You are a biology expert who needs to identify specific subdomains from the given question and reasoning process.

Original subject classification: {raw_subject}

Question:
{question}

Reasoning process:
{rationale}

Please analyze the question and reasoning process to identify the specific biology subdomains involved. Subdomains should be specific, professional fields, such as:
- Immunology
- Molecular Biology
- Cell Biology
- Genetics
- Biochemistry
- Microbiology
- Neuroscience
- Ecology
- Evolutionary Biology
- Developmental Biology
- Pharmacology
- Pathology
- Physiology
- Anatomy
- etc.

Please return the results in JSON format as follows:
[
  "Subdomain 1",
  "Subdomain 2",
  ...
]

Only return the JSON array, do not include other content. You should not have too many subdomains. If you cannot determine specific subdomains, return an empty array [].
"""
        
        messages = [{"role": "user", "content": prompt}]
        response_text, _, token_info = chat_with_tools(messages, model=self.model)
        self._update_token_stats(token_info)
        self.logger.info(f"提取子领域Token使用: 输入{token_info['input_tokens']}, 输出{token_info['output_tokens']}, 总计{token_info['total_tokens']}")
        
        try:
            subdomains = json.loads(response_text.strip())
            if isinstance(subdomains, list):
                return subdomains
            else:
                return []
        except json.JSONDecodeError:
            return []
    
    def extract_supporting_facts(self, question: str, rationale: str, answer:str) -> List[Dict[str, str]]:
        """
        从思考过程中提取supporting facts
        
        Args:
            question: 题目内容
            rationale: 思考过程
            
        Returns:
            supporting facts列表，每个fact包含fact内容和出处信息
        """
        prompt = f"""
You are a biology expert who needs to extract objective facts that support the question's answer from the given reasoning process.

Question:
{question}
Answer: {answer}
Reasoning process:
{rationale}

Please extract all objective facts that support the question's answer from the reasoning process. Each fact should:
1. Be an objective, verifiable biological fact and also a knowledge point that the question wants to test
2. Be meaningful, not overly simple or obvious statements


Examples:
- "Traditional APCs (such as macrophages, dendritic cells) can take up antigens through phagocytosis and then present them to T cells on MHC II"
- "Watterson's estimator (theta) focuses on whether sites are polymorphic, not on variant frequency"
- "pi (nucleotide diversity) is sensitive to variant frequency"

Please return the results in JSON format as follows:
[
  {{
    "fact": "Fact 1",
    "source": "raw_question",
    "source_detail": "Extracted from original question rationale"
  }},
  {{
    "fact": "Fact 2", 
    "source": "raw_question",
    "source_detail": "Extracted from original question rationale"
  }},
  ...
]

Only return the JSON array, do not include other content. If no relevant facts are found, return an empty array [].
"""
        
        messages = [{"role": "user", "content": prompt}]
        response_text, _, token_info = chat_with_tools(messages, model=self.model)
        self._update_token_stats(token_info)
        self.logger.info(f"提取支撑事实Token使用: 输入{token_info['input_tokens']}, 输出{token_info['output_tokens']}, 总计{token_info['total_tokens']}")
        
        try:
            facts = json.loads(response_text.strip())
            if isinstance(facts, list):
                # 过滤掉太短或没有意义的事实
                filtered_facts = []
                for fact in facts:
                    if isinstance(fact, dict) and "fact" in fact:
                        if len(fact["fact"].strip()) > 20:
                            # 确保有source信息，创建新的字典避免修改原始数据
                            processed_fact = fact.copy()
                            if "source" not in processed_fact:
                                processed_fact["source"] = "raw_question"
                            if "source_detail" not in processed_fact:
                                processed_fact["source_detail"] = "从原始题目rationale中提取"
                            filtered_facts.append(processed_fact)
                    elif isinstance(fact, str) and len(fact.strip()) > 20:
                        # 兼容旧格式
                        filtered_facts.append({
                            "fact": fact.strip(),
                            "source": "raw_question",
                            "source_detail": "从原始题目rationale中提取"
                        })
                return filtered_facts
            else:
                return []
        except json.JSONDecodeError:
            return []
    
    def extract_related_papers(self, question: str, rationale: str) -> List[Dict[str, str]]:
        """
        从题目和思考过程中提取相关论文/PDF信息
        
        Args:
            question: 题目内容
            rationale: 思考过程
            
        Returns:
            相关论文信息列表
        """
        prompt = f"""
You are a biology expert who needs to identify whether specific papers, research, or PDF documents are referenced in the given question and reasoning process.

Question:
{question}

Reasoning process:
{rationale}

Please analyze the question and reasoning process to identify:
1. Whether specific research papers are mentioned
2. Whether specific authors or research are cited
3. Whether specific experiments, methods, or discoveries are mentioned
4. Whether textbooks, review articles, or other academic resources are cited

If relevant research or papers are found, please extract the following information:
- Paper title (if mentioned)
- Author names (if mentioned)
- Journal name (if mentioned)
- Year (if mentioned)
- Any other relevant information

Please return the results in JSON format as follows:
[
  {{
    "title": "Paper title or research name",
    "authors": "Author names",
    "journal": "Journal name",
    "year": "Publication year",
    "url": "If there is a URL",
    "description": "Other relevant information"
  }},
  ...
]

If no relevant papers or research are found, return an empty array [].
Only return the JSON array, do not include other content.
"""
        
        messages = [{"role": "user", "content": prompt}]
        response_text, _, token_info = chat_with_tools(messages, model=self.model)
        self._update_token_stats(token_info)
        self.logger.info(f"提取相关论文Token使用: 输入{token_info['input_tokens']}, 输出{token_info['output_tokens']}, 总计{token_info['total_tokens']}")
        
        try:
            papers = json.loads(response_text.strip())
            if isinstance(papers, list):
                # 过滤掉空的信息
                filtered_papers = []
                for paper in papers:
                    if isinstance(paper, dict) and any(paper.values()):
                        filtered_papers.append(paper)
                return filtered_papers
            else:
                return []
        except json.JSONDecodeError:
            return []
    
    def process_single_question(self, question_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单个题目，提取所有信息
        
        Args:
            question_data: 题目数据
            
        Returns:
            提取的信息
        """
        question = question_data.get('question', '')
        rationale = question_data.get('rationale', '')
        raw_subject = question_data.get('raw_subject', '')
        answer = question_data.get('answer', '')
        question_id = question_data.get('id', '')
        
        self.logger.info(f"开始处理题目 ID: {question_id}")
        self.logger.info(f"原始学科: {raw_subject}")
        print(f"处理题目 ID: {question_id}")
        print(f"原始学科: {raw_subject}")
        
        # 提取子领域
        self.logger.info("开始提取子领域...")
        subdomains = self.extract_subdomains(question, rationale, raw_subject)
        self.logger.info(f"提取到{len(subdomains)}个子领域: {subdomains}")
        print(f"提取到 {len(subdomains)} 个子领域: {subdomains}")
        
        # 提取supporting facts
        self.logger.info("开始提取supporting facts...")
        supporting_facts = self.extract_supporting_facts(question, rationale, answer)
        
        # 提取相关论文
        #related_papers = self.extract_related_papers(question, rationale)
        #print(f"提取到 {len(related_papers)} 个相关论文/研究")
        
        result = {
            "id": question_id,
            "question": question,
            "answer": answer,
            "raw_subject": raw_subject,
            "extracted_subdomains": subdomains,
            "supporting_facts": supporting_facts,
            #"related_papers": related_papers,
            "rationale": rationale,
            "token_stats": self.get_token_stats()
        }
        
        return result
    
    def process_batch(self, data: List[Dict[str, Any]], start_idx: int = 0, batch_size: int = 10) -> List[Dict[str, Any]]:
        """
        批量处理题目
        
        Args:
            data: 题目数据列表
            start_idx: 开始索引
            batch_size: 批次大小
            
        Returns:
            处理结果列表
        """
        results = []
        end_idx = min(start_idx + batch_size, len(data))
        
        print(f"处理题目 {start_idx} 到 {end_idx-1}")
        
        for i in range(start_idx, end_idx):
            try:
                result = self.process_single_question(data[i])
                results.append(result)
                print(f"完成题目 {i+1}/{len(data)}")
                print("-" * 50)
            except Exception as e:
                print(f"处理题目 {i} 时出错: {e}")
                continue
        
        return results
    
    def save_results(self, results: List[Dict[str, Any]], output_file: str):
        """保存结果到文件"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到: {output_file}")
    
    def run(self, input_file: str, output_file: str, start_idx: int = 0, batch_size: int = 10):
        """
        运行完整的提取流程
        
        Args:
            input_file: 输入文件路径
            output_file: 输出文件路径
            start_idx: 开始索引
            batch_size: 批次大小
        """
        print("开始加载训练数据...")
        data = self.load_training_data(input_file)
        print(f"加载了 {len(data)} 个题目")
        
        print(f"开始处理，从索引 {start_idx} 开始，批次大小 {batch_size}")
        results = self.process_batch(data, start_idx, batch_size)
        
        print(f"处理完成，共处理了 {len(results)} 个题目")
        
        # 保存结果
        self.save_results(results, output_file)
        
        # 打印统计信息
        self.print_statistics(results)
    
    def print_statistics(self, results: List[Dict[str, Any]]):
        """打印统计信息"""
        total_questions = len(results)
        total_subdomains = sum(len(r['extracted_subdomains']) for r in results)
        total_facts = sum(len(r['supporting_facts']) for r in results)
        total_papers = sum(len(r['related_papers']) for r in results)
        
        print("\n=== 统计信息 ===")
        print(f"总题目数: {total_questions}")
        print(f"总子领域数: {total_subdomains}")
        print(f"总supporting facts数: {total_facts}")
        print(f"总相关论文数: {total_papers}")
        print(f"平均每题目子领域数: {total_subdomains/total_questions:.2f}")
        print(f"平均每题目facts数: {total_facts/total_questions:.2f}")
        print(f"平均每题目论文数: {total_papers/total_questions:.2f}")
        
        # 统计子领域分布
        subdomain_count = {}
        for result in results:
            for subdomain in result['extracted_subdomains']:
                subdomain_count[subdomain] = subdomain_count.get(subdomain, 0) + 1
        
        print("\n=== 子领域分布 ===")
        for subdomain, count in sorted(subdomain_count.items(), key=lambda x: x[1], reverse=True):
            print(f"{subdomain}: {count}")


def main():
    """测试函数"""
    agent = ExtractFactAgent()
    
    # 测试单个题目
    test_data = {
        "id": "test_1",
        "question": "Most naive B cells express a single BCR heavy chain and a single BCR light chain as mRNA. Likewise, most naive T cells express a single TCR beta chain and a single TCR alpha chain as mRNA.",
        "rationale": "Naive B and T cells typically express a single heavy/beta chain and a single light/alpha chain. This behavior is known as allelic exclusion. However, about 1% of naive B cells express two light chains and about 30% of naive T cells express two alpha chains. This behavior is known as allelic inclusion.",
        "raw_subject": "Biology",
        "answer": "(1,4,5), (1,3,4,5,6)"
    }
    
    result = agent.process_single_question(test_data)
    
    print("=== 测试结果 ===")
    print(f"子领域: {result['extracted_subdomains']}")
    print(f"Supporting facts: {result['supporting_facts']}")
    print(f"相关论文: {result['related_papers']}")


if __name__ == "__main__":
    # 运行测试
    main()
    
    # 或者运行完整流程
    # agent = ExtractFactAgent()
    # agent.run(
    #     input_file="/Users/liyihang/code/cursor/BioHLETool/dataset/hle/train.json",
    #     output_file="/Users/liyihang/code/cursor/BioHLETool/extracted_facts.json",
    #     start_idx=0,
    #     batch_size=5
    # )
