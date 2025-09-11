import json
import re
from typing import List, Dict, Any, Optional, Tuple
from tools.llm_call import chat_with_tools


class ExtractFactAgent:
    """
    从HLE训练数据中提取信息的agent
    提取：子领域、supporting facts、相关论文/PDF
    """
    
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
    
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
你是一个生物学专家，需要从给定的题目和思考过程中识别出具体的子领域。

原始学科分类: {raw_subject}

题目:
{question}

思考过程:
{rationale}

请分析题目和思考过程，识别出涉及的具体生物学子领域。子领域应该是具体的、专业的领域，比如：
- 免疫学 (Immunology)
- 分子生物学 (Molecular Biology) 
- 细胞生物学 (Cell Biology)
- 遗传学 (Genetics)
- 生物信息学 (Bioinformatics)
- 生物化学 (Biochemistry)
- 微生物学 (Microbiology)
- 神经科学 (Neuroscience)
- 生态学 (Ecology)
- 进化生物学 (Evolutionary Biology)
- 发育生物学 (Developmental Biology)
- 药理学 (Pharmacology)
- 病理学 (Pathology)
- 生理学 (Physiology)
- 解剖学 (Anatomy)
- 等等

请以JSON格式返回结果，格式如下：
[
  "子领域1",
  "子领域2",
  ...
]

只返回JSON数组，不要包含其他内容。如果无法确定具体子领域，返回空数组[]。
"""
        
        messages = [{"role": "user", "content": prompt}]
        response_text, _ = chat_with_tools(messages, model=self.model)
        
        try:
            subdomains = json.loads(response_text.strip())
            if isinstance(subdomains, list):
                return subdomains
            else:
                return []
        except json.JSONDecodeError:
            return []
    
    def extract_supporting_facts(self, question: str, rationale: str) -> List[Dict[str, str]]:
        """
        从思考过程中提取supporting facts
        
        Args:
            question: 题目内容
            rationale: 思考过程
            
        Returns:
            supporting facts列表，每个fact包含fact内容和出处信息
        """
        prompt = f"""
你是一个生物学专家，需要从给定的思考过程中提取出支持题目解答的客观事实。

题目:
{question}

思考过程:
{rationale}

请从思考过程中提取出所有支持题目解答的客观事实。每个事实应该：
1. 是客观的、可验证的生物学事实
2. 不是推理过程或结论，而是作为推理基础的事实
3. 表达完整，包含必要的前提条件
4. 有意义，不是过于简单或显而易见的陈述
5. 与题目解答直接相关

例如：
- "传统 APC（如巨噬细胞、树突状细胞）能通过吞噬作用摄取抗原，然后在 MHC II 上呈递给 T 细胞"
- "Watterson's estimator (theta) 关注位点是否多态，而不是变异频率"
- "pi (nucleotide diversity) 对变异频率敏感"

请以JSON格式返回结果，格式如下：
[
  {{
    "fact": "事实1",
    "source": "raw_question",
    "source_detail": "从原始题目rationale中提取"
  }},
  {{
    "fact": "事实2", 
    "source": "raw_question",
    "source_detail": "从原始题目rationale中提取"
  }},
  ...
]

只返回JSON数组，不要包含其他内容。如果没有找到相关事实，返回空数组[]。
"""
        
        messages = [{"role": "user", "content": prompt}]
        response_text, _ = chat_with_tools(messages, model=self.model)
        
        try:
            facts = json.loads(response_text.strip())
            if isinstance(facts, list):
                # 过滤掉太短或没有意义的事实
                filtered_facts = []
                for fact in facts:
                    if isinstance(fact, dict) and "fact" in fact:
                        if len(fact["fact"].strip()) > 20:
                            # 确保有source信息
                            if "source" not in fact:
                                fact["source"] = "raw_question"
                            if "source_detail" not in fact:
                                fact["source_detail"] = "从原始题目rationale中提取"
                            filtered_facts.append(fact)
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
你是一个生物学专家，需要从给定的题目和思考过程中识别出是否引用了特定的论文、研究或PDF文档。

题目:
{question}

思考过程:
{rationale}

请分析题目和思考过程，识别出：
1. 是否提到了特定的研究论文
2. 是否引用了具体的作者或研究
3. 是否提到了特定的实验、方法或发现
4. 是否引用了教科书、综述文章或其他学术资源

如果找到了相关的研究或论文，请提取以下信息：
- 论文标题（如果提到）
- 作者姓名（如果提到）
- 期刊名称（如果提到）
- 年份（如果提到）
- 任何其他相关信息

请以JSON格式返回结果，格式如下：
[
  {{
    "title": "论文标题或研究名称",
    "authors": "作者姓名",
    "journal": "期刊名称",
    "year": "发表年份",
    "url": "如果有URL的话",
    "description": "其他相关信息"
  }},
  ...
]

如果没有找到相关论文或研究，返回空数组[]。
只返回JSON数组，不要包含其他内容。
"""
        
        messages = [{"role": "user", "content": prompt}]
        response_text, _ = chat_with_tools(messages, model=self.model)
        
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
        
        print(f"处理题目 ID: {question_id}")
        print(f"原始学科: {raw_subject}")
        
        # 提取子领域
        subdomains = self.extract_subdomains(question, rationale, raw_subject)
        print(f"提取到 {len(subdomains)} 个子领域: {subdomains}")
        
        # 提取supporting facts
        supporting_facts = self.extract_supporting_facts(question, rationale)
        print(f"提取到 {len(supporting_facts)} 个supporting facts")
        
        # 提取相关论文
        related_papers = self.extract_related_papers(question, rationale)
        print(f"提取到 {len(related_papers)} 个相关论文/研究")
        
        result = {
            "id": question_id,
            "question": question,
            "answer": answer,
            "raw_subject": raw_subject,
            "extracted_subdomains": subdomains,
            "supporting_facts": supporting_facts,
            "related_papers": related_papers,
            "rationale": rationale
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
