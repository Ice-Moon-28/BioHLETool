import json
import re
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from tools.llm_call import chat_with_tools
from tools.web_tools import search_google, browse_webpage, extract_pdf_content
from tools.search import search_serper_dev
from prompts.tool_desc import WEB_TOOLS


@dataclass
class FactWithSource:
    """带出处信息的事实"""
    fact: str
    source: str  # "raw_question" 或 "web_search"
    source_detail: str  # 详细出处信息
    source_url: Optional[str] = None  # 网页URL（如果是网络搜索）
    source_title: Optional[str] = None  # 网页标题（如果是网络搜索）


class SearchInfoAgent:
    """
    一个可以自主进行搜索和浏览的agent，用于根据已知的"subdomain"和"supporting fact"获取"new fact"
    """
    
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.tools = self._parse_tools()
        
    def _parse_tools(self) -> List[Dict[str, Any]]:
        """解析工具描述"""
        try:
            # 移除WEB_TOOLS字符串的引号并解析JSON
            tools_str = WEB_TOOLS.strip()
            if tools_str.startswith('"""') and tools_str.endswith('"""'):
                tools_str = tools_str[3:-3]
            elif tools_str.startswith("'''") and tools_str.endswith("'''"):
                tools_str = tools_str[3:-3]
            
            # 解析JSON数组
            tools_list = json.loads(tools_str)
            
            # 转换为OpenAI function calling格式
            formatted_tools = []
            for tool in tools_list:
                formatted_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["parameters"]
                    }
                })
            return formatted_tools
        except Exception as e:
            print(f"解析工具描述时出错: {e}")
            return []
    
    def extract_upper_concepts(self, supporting_facts: List[str], subdomain: str) -> List[str]:
        """
        从supporting facts中提取上层概念
        
        Args:
            supporting_facts: 支持事实列表
            subdomain: 子领域
            
        Returns:
            上层概念列表
        """
        prompt = f"""
你是一个生物学专家，需要从给定的支持事实中提取上层概念。

子领域: {subdomain}

支持事实:
{chr(10).join([f"- {fact}" for fact in supporting_facts])}

请分析这些支持事实，提取出3-5个关键的上层概念。上层概念应该是更广泛、更抽象的概念，能够涵盖这些具体事实。

例如：
- 如果事实是"传统 APC（如巨噬细胞、树突状细胞）能通过吞噬作用摄取抗原，然后在 MHC II 上呈递给 T 细胞"
- 上层概念可能是"抗原呈递细胞（APCs）的功能机制"

请只返回上层概念列表，每行一个概念，不要包含其他解释。
"""
        
        messages = [{"role": "user", "content": prompt}]
        response_text, _ = chat_with_tools(messages, model=self.model)
        
        # 解析返回的概念列表
        concepts = []
        for line in response_text.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                # 移除可能的编号或符号
                concept = re.sub(r'^[-•\d\.\)\s]+', '', line).strip()
                if concept:
                    concepts.append(concept)
        
        return concepts[:5]  # 最多返回5个概念
    
    def search_and_filter_results(self, concepts: List[str], k: int = 5) -> List[Dict[str, str]]:
        """
        搜索上层概念并过滤生物学相关结果
        
        Args:
            concepts: 上层概念列表
            k: 每个概念搜索的结果数量
            
        Returns:
            过滤后的相关网页列表
        """
        all_results = []
        
        for concept in concepts:
            print(f"正在搜索概念: {concept}")
            
            # 使用Google搜索
            search_results = search_serper_dev(concept, num_results=k, language="en")
            
            # 解析搜索结果
            results = self._parse_search_results(search_results)
            
            filtered_results = self._filter_biology_related(results)
            print(f"找到 {len(filtered_results)} 个相关结果")

        all_results.extend(filtered_results)
        
        
        return all_results
    
    def _parse_search_results(self, search_results: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """解析Google搜索结果"""
        # search_google现在直接返回字典列表，不需要解析
        return search_results
    
    def _filter_biology_related(self, results: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """使用LLM过滤生物学相关的结果"""
        if not results:
            return []
        
        # 将结果格式化为文本
        results_text = ""
        for i, result in enumerate(results, 1):
            title = result.get('title', '')
            description = result.get('snippet', '')
            url = result.get('link', '')
            results_text += f"{i}. 标题: {title}\n   描述: {description}\n   URL: {url}\n\n"
        
        prompt = f"""
你是一个生物学专家，需要判断以下搜索结果是否与生物学相关。

搜索结果:
{results_text}

请分析每个搜索结果，判断其是否与生物学、生物医学、生命科学等相关。考虑以下因素：
1. 标题和描述中是否包含生物学概念
2. 内容是否涉及细胞、分子、基因、蛋白质、生物过程等
3. 是否与医学、药理学、生物技术等相关
4. 是否与生物体、生态系统、进化等相关

请以JSON格式返回结果，格式如下：
[
  {{
    "index": 1,
    "is_biology_related": true,
    "reason": "包含细胞生物学和免疫学相关内容"
  }},
  {{
    "index": 2,
    "is_biology_related": false,
    "reason": "主要是计算机技术相关内容"
  }},
  ...
]

只返回JSON数组，不要包含其他内容。
"""
        
        messages = [{"role": "user", "content": prompt}]
        response_text, _ = chat_with_tools(messages, model=self.model)
        
        try:
            # 解析LLM的响应
            judgments = json.loads(response_text.strip())
            if not isinstance(judgments, list):
                return results  # 如果解析失败，返回所有结果
            
            # 根据判断结果过滤
            filtered_results = []
            for judgment in judgments:
                if isinstance(judgment, dict) and judgment.get('is_biology_related', True):
                    index = judgment.get('index', 0) - 1  # 转换为0-based索引
                    if 0 <= index < len(results):
                        filtered_results.append(results[index])
            
            return filtered_results
            
        except json.JSONDecodeError:
            print("LLM过滤结果解析失败，使用关键词过滤作为备选方案")
            return results
    
    
    def browse_and_extract_facts(self, urls: List[Dict[str, str]], n: int = 3) -> List[FactWithSource]:
        """
        浏览网页并提取new facts
        
        Args:
            urls: 网页信息列表
            n: 每个网页提取的facts数量
            
        Returns:
            提取的facts列表，每个fact包含出处信息
        """
        all_facts = []
        
        for url_info in urls:
            url = url_info['url']
            title = url_info.get('title', '')
            
            print(f"正在浏览: {title}")
            print(f"URL: {url}")
            
            try:
                # 判断是否为PDF
                if url.lower().endswith('.pdf') or 'pdf' in url.lower():
                    content = extract_pdf_content(url)
                else:
                    content = browse_webpage(url)
                
                if content and len(content.strip()) > 100:  # 确保有足够的内容
                    facts = self._extract_facts_from_content(content, title, n, url)
                    if facts is None:
                        continue
                    # 将facts转换为FactWithSource对象
                    for fact in facts:
                        if isinstance(fact, dict):
                            fact_obj = FactWithSource(
                                fact=fact.get('fact', ''),
                                source='web_search',
                                source_detail=f"网页标题: {title}",
                                source_url=url,
                                source_title=title,
                                #context=fact.get('context', '')
                            )
                            all_facts.append(fact_obj)
                    print(f"从 {title} 提取了 {len(facts)} 个facts")
                else:
                    print(f"无法从 {title} 提取内容")
                    
            except Exception as e:
                print(f"浏览 {url} 时出错: {e}")
                continue
        
        return all_facts
    
    def _extract_facts_from_content(self, content: str, title: str, n: int, url: str = "") -> List[Dict[str, str]]:
        """从内容中提取facts"""
        # 限制内容长度以避免token限制
        max_length = 38000
        if len(content) > max_length:
            content = content[:max_length] + "..."
        
        prompt = f"""
你是一个生物学专家，需要从给定的网页内容中提取客观的生物学事实。

网页标题: {title}
网页URL: {url}

网页内容:
{content}

请从上述内容中提取 {n} 个重要的生物学事实。每个事实应该：
1. 是客观的事实陈述，不是观点或推测
2. 包含完整的前提条件（如在什么环境下、什么条件下）
3. 不能过于简单，应该是有意义的内容，应该包含必要的上下文说明
4. 如果实在无法达到数量要求，宁缺毋滥

请以JSON格式返回，格式如下：
[
  {{
    "fact": "相关条件或环境(前提)+具体事实陈述",
    "source": "web_search",
    "source_detail": "网页标题: {title}",
    "source_url": "{url}"
  }},
  ...
]

只返回JSON数组，不要包含其他内容。
"""
        
        messages = [{"role": "user", "content": prompt}]
        response_text, _ = chat_with_tools(messages, model=self.model)
        
        try:
            # 尝试解析JSON
            facts = json.loads(response_text.strip())
            if isinstance(facts, list):
                return facts[:n]  # 确保不超过n个
            else:
                return []
        except json.JSONDecodeError:
            # 如果JSON解析失败，尝试手动提取
            return None
    
    
    def merge_and_deduplicate_facts(self, facts: List[FactWithSource]) -> List[FactWithSource]:
        """合并和去重facts"""
        if not facts:
            return []
        
        # 使用LLM进行智能去重和合并
        facts_text = "\n".join([f"- {fact.fact} (来源: {fact.source_title or 'Unknown'})" 
                               for fact in facts])
        
        prompt = f"""
你是一个生物学专家，需要合并和去重以下生物学事实列表。

原始事实列表:
{facts_text}

请分析这些事实，进行以下操作：
1. 去除重复或高度相似的事实
2. 合并可以合并的相关事实
3. 保留最有价值和最准确的事实
4. 确保每个事实都是客观、准确的生物学陈述

请以JSON格式返回合并后的结果，格式如下：
[
  {{
    "fact": "合并后的事实陈述",
    "source": "web_search",
    "source_detail": "合并自多个网页",
    "source_url": "主要来源URL",
    "source_title": "主要来源标题",
    "sources": ["来源1", "来源2", ...]
  }},
  ...
]

只返回JSON数组，不要包含其他内容。
"""
        
        messages = [{"role": "user", "content": prompt}]
        response_text, _ = chat_with_tools(messages, model=self.model)
        
        try:
            merged_facts_data = json.loads(response_text.strip())
            if isinstance(merged_facts_data, list):
                # 将JSON数据转换为FactWithSource对象
                merged_facts = []
                for fact_data in merged_facts_data:
                    fact_obj = FactWithSource(
                        fact=fact_data.get('fact', ''),
                        source=fact_data.get('source', 'web_search'),
                        source_detail=fact_data.get('source_detail', '合并自多个网页'),
                        source_url=fact_data.get('source_url'),
                        source_title=fact_data.get('source_title'),
                    )
                    merged_facts.append(fact_obj)
                return merged_facts
            else:
                return facts  # 如果解析失败，返回原始facts
        except json.JSONDecodeError:
            return facts  # 如果解析失败，返回原始facts
    
    def run(self, subdomain: str, supporting_facts: List[str], k: int = 5, n: int = 3) -> Dict[str, Any]:
        """
        运行完整的搜索和提取流程
        
        Args:
            subdomain: 子领域
            supporting_facts: 支持事实列表
            k: 每个概念搜索的结果数量
            n: 每个网页提取的facts数量
            
        Returns:
            包含所有结果的字典
        """
        print(f"开始处理子领域: {subdomain}")
        print(f"支持事实数量: {len(supporting_facts)}")
        
        # 步骤1: 提取上层概念
        print("\n步骤1: 提取上层概念...")
        concepts = self.extract_upper_concepts(supporting_facts, subdomain)
        print(f"提取到 {len(concepts)} 个上层概念:")
        for i, concept in enumerate(concepts, 1):
            print(f"  {i}. {concept}")
        
        # 步骤2: 搜索和过滤结果
        print(f"\n步骤2: 搜索概念并过滤结果...")
        search_results = self.search_and_filter_results(concepts, k)
        print(f"找到 {len(search_results)} 个相关网页")
        
        # 步骤3: 浏览网页并提取facts
        print(f"\n步骤3: 浏览网页并提取facts...")
        extracted_facts = self.browse_and_extract_facts(search_results, n)
        print(f"总共提取了 {len(extracted_facts)} 个facts")
        
        # 步骤4: 合并和去重
        print(f"\n步骤4: 合并和去重facts...")
        final_facts = self.merge_and_deduplicate_facts(extracted_facts)
        print(f"最终得到 {len(final_facts)} 个unique facts")
        
        # 返回结果
        result = {
            "subdomain": subdomain,
            "supporting_facts": supporting_facts,
            "extracted_concepts": concepts,
            "search_results": search_results,
            "extracted_facts": extracted_facts,
            "final_facts": final_facts,
            "summary": {
                "concepts_count": len(concepts),
                "search_results_count": len(search_results),
                "extracted_facts_count": len(extracted_facts),
                "final_facts_count": len(final_facts)
            }
        }
        
        return result


def main():
    """测试函数"""
    agent = SearchInfoAgent()
    
    # 测试数据
    subdomain = "免疫学"
    supporting_facts = [
        "传统 APC（如巨噬细胞、树突状细胞）能通过吞噬作用摄取抗原，然后在 MHC II 上呈递给 T 细胞。",
        "B 细胞能够识别并结合特异性抗原，然后分化为浆细胞产生抗体。",
        "T 细胞分为辅助性 T 细胞（Th）和细胞毒性 T 细胞（Tc），分别参与细胞免疫和体液免疫。"
    ]
    
    result = agent.run(subdomain, supporting_facts, k=3, n=2)
    
    print("\n=== 最终结果 ===")
    print(f"子领域: {result['subdomain']}")
    print(f"提取的概念: {result['extracted_concepts']}")
    print(f"最终facts数量: {result['summary']['final_facts_count']}")
    
    print("\n=== 最终Facts ===")
    for i, fact in enumerate(result['final_facts'], 1):
        print(f"{i}. {fact['fact']}")
        if 'sources' in fact:
            print(f"   来源: {', '.join(fact['sources'])}")
        print()


if __name__ == "__main__":
    main()
