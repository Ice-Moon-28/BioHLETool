import json
import re
import logging
import hashlib
import pickle
import os
from typing import List, Dict, Any, Tuple, Optional, Set
from dataclasses import dataclass
from collections import defaultdict
from tools.llm_call import chat_with_tools
from tools.web_tools import search_google, browse_webpage, extract_pdf_content
from tools.search import search_serper_dev
from prompts.tool_desc import WEB_TOOLS
from prompts.extract_info_prompts import *
from openai import OpenAI

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
    
    def __init__(self, model: str = "Pro/deepseek-ai/DeepSeek-V3.1", cache_dir: str = "server/cache"):
        self.model = model
        self.tools = self._parse_tools()
        self.logger = logging.getLogger(__name__)
        self.visited_url = defaultdict(list)  # 存储已访问URL对应的概念列表
        self.cache_dir = cache_dir
        self.webpage_cache = {}  # 网页内容缓存
        self.fact_extractor = OpenAI(
            api_key='sk-b0ba29e85cac4cf9bfcb24d3a482cd17',
            base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
        )
        # 确保缓存目录存在
        os.makedirs(cache_dir, exist_ok=True)
        
        # Token统计
        self.token_stats = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "call_count": 0
        }
        
        # 加载已有的缓存
        self._load_cache()

    def _update_token_stats(self, token_info: Dict[str, int]):
        """更新token统计信息"""
        self.token_stats["total_input_tokens"] += token_info.get("input_tokens", 0)
        self.token_stats["total_output_tokens"] += token_info.get("output_tokens", 0)
        self.token_stats["total_tokens"] += token_info.get("total_tokens", 0)
        self.token_stats["call_count"] += 1

    def get_token_stats(self) -> Dict[str, int]:
        """获取token统计信息"""
        return self.token_stats.copy()

    def call_extractor(self, messages: List[Dict[str, Any]]):
        try:
            completion = self.fact_extractor.chat.completions.create(
                model="qwen2.5-72b-instruct",
                messages=messages,
                stream=False,
                timeout=10000,
            )
            content = completion.choices[0].message.content.strip()
            # 提取token使用信息
            usage = completion.usage
            token_info = {
                "input_tokens": usage.prompt_tokens if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0
            }
            return content, token_info
        except Exception as e:
            self.logger.error(f"调用extractor API时出错: {e}")
            return "", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def _load_cache(self):
        """加载网页缓存和概念信息"""
        cache_file = os.path.join(self.cache_dir, "webpage_cache.pkl")
        concepts_file = os.path.join(self.cache_dir, "visited_url_concepts.pkl")
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    self.webpage_cache = pickle.load(f)
                self.logger.info(f"加载了 {len(self.webpage_cache)} 个缓存的网页")
            except Exception as e:
                self.logger.warning(f"加载缓存失败: {e}")
                self.webpage_cache = {}
        else:
            self.webpage_cache = {}
            
        if os.path.exists(concepts_file):
            try:
                with open(concepts_file, 'rb') as f:
                    visited_concepts = pickle.load(f)
                    # 将加载的数据转换为defaultdict
                    self.visited_url = defaultdict(list, visited_concepts)
                self.logger.info(f"加载了 {len(self.visited_url)} 个URL的概念信息")
            except Exception as e:
                self.logger.warning(f"加载概念信息失败: {e}")
                self.visited_url = defaultdict(list)
        else:
            self.visited_url = defaultdict(list)

    def _save_cache(self):
        """保存网页缓存和概念信息"""
        cache_file = os.path.join(self.cache_dir, "webpage_cache.pkl")
        concepts_file = os.path.join(self.cache_dir, "visited_url_concepts.pkl")
        
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(self.webpage_cache, f)
            self.logger.info(f"保存了 {len(self.webpage_cache)} 个缓存的网页")
        except Exception as e:
            self.logger.error(f"保存缓存失败: {e}")
            
        try:
            with open(concepts_file, 'wb') as f:
                pickle.dump(dict(self.visited_url), f)
            self.logger.info(f"保存了 {len(self.visited_url)} 个URL的概念信息")
        except Exception as e:
            self.logger.error(f"保存概念信息失败: {e}")

    def _get_url_hash(self, url: str) -> str:
        """生成URL的哈希值作为缓存键"""
        return hashlib.md5(url.encode('utf-8')).hexdigest()

    def _are_concepts_identical(self, concepts1: List[str], concepts2: List[str]) -> bool:
        """
        判断两个概念列表是否完全相同
        
        Args:
            concepts1: 第一个概念列表
            concepts2: 第二个概念列表
            
        Returns:
            是否完全相同
        """
        if not concepts1 or not concepts2:
            return False
        
        # 将概念转换为小写并去除空格，然后排序
        set1 = sorted({concept.lower().strip() for concept in concepts1})
        set2 = sorted({concept.lower().strip() for concept in concepts2})
        
        return set1 == set2

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
        supporting_facts_text = chr(10).join([f"- {fact}" for fact in supporting_facts])
        #prompt = EXTRACT_CONCEPT.format(subdomain=subdomain, supporting_facts=supporting_facts_text)
        prompt = EXTRACT_KEYWORDS.format(subdomain=subdomain, supporting_facts=supporting_facts_text)
        messages = [{"role": "user", "content": prompt}]
        response_text, _, token_info = chat_with_tools(messages, model=self.model)
        self._update_token_stats(token_info)
        self.logger.info(f"提取概念Token使用: 输入{token_info['input_tokens']}, 输出{token_info['output_tokens']}, 总计{token_info['total_tokens']}")
        
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
        self.logger.info(f"开始搜索概念，共{len(concepts)}个概念，每个概念搜索{k}个结果")
        self.logger.debug(f"搜索概念列表: {concepts}")
        
        all_results = []
        
        for i, concept in enumerate(concepts):
            self.logger.info(f"正在搜索第{i+1}个概念: {concept}")
            print(f"正在搜索概念: {concept}")
            
            try:
                # 使用Google搜索
                self.logger.debug(f"调用search_serper_dev，参数: concept={concept}, num_results={k+1}")
                search_results = search_serper_dev(concept, num_results=k+2)
                self.logger.debug(f"search_serper_dev返回结果: {search_results}")
                
                # 解析搜索结果
                results = self._parse_search_results(search_results)
                self.logger.debug(f"解析后的结果: {results}")
                
                filtered_results = self._filter_wiki_web(results)#self._filter_biology_related(results)
                self.logger.info(f"概念'{concept}'搜索完成，获得{len(filtered_results)}个相关结果")
                
                filtered_results = filtered_results[:k]
                print(f"找到 {len(filtered_results)} 个相关结果")
                all_results.extend(filtered_results)
                
            except Exception as e:
                self.logger.error(f"搜索概念'{concept}'时出错: {e}", exc_info=True)
                print(f"搜索概念'{concept}'时出错: {e}")
                continue
        
        self.logger.info(f"所有概念搜索完成，总共找到 {len(all_results)} 个相关结果")
        return all_results
    
    def _parse_search_results(self, search_results: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """解析Google搜索结果"""
        # search_google现在直接返回字典列表，不需要解析
        return search_results
    
    def _filter_wiki_web(self,results: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """过滤wiki网页"""
        filtered_results = []
        for i, result in enumerate(results, 1):
            url = result.get('link', '')
            if "wikipedia.org" in url:
                filtered_results.append(result)
        return filtered_results

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
        
        prompt = FILTER_BIOLOGY_RELATED.format(results_text=results_text)
        
        messages = [{"role": "user", "content": prompt}]
        response_text, _, token_info = chat_with_tools(messages, model=self.model)
        self._update_token_stats(token_info)
        self.logger.info(f"过滤生物学相关内容Token使用: 输入{token_info['input_tokens']}, 输出{token_info['output_tokens']}, 总计{token_info['total_tokens']}")
        
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
    
    def remove_urls(self, text: str) -> str:
        # 匹配 http/https 或 www. 开头的 URL
        url_pattern = r'(https?://\S+|www\.\S+)'
        cleaned_text = re.sub(url_pattern, '', text)
        return cleaned_text
    
    def browse_and_extract_facts(self, urls: List[Dict[str, str]], concepts_text: str, n: int = 3, 
                                target_concepts: List[str] = None) -> List[FactWithSource]:
        """
        浏览网页并提取new facts，支持缓存和概念重叠度判断
        
        Args:
            urls: 网页信息列表
            concepts_text: 概念文本
            n: 每个网页提取的facts数量
            target_concepts: 目标概念列表，用于计算重叠度
            
        Returns:
            提取的facts列表，每个fact包含出处信息
        """
        self.logger.info(f"开始浏览网页并提取事实，共{len(urls)}个网页，每个网页提取{n}个事实")
        self.logger.debug(f"网页列表: {urls}")
        
        all_facts = []
        
        for i, url_info in enumerate(urls):
            self.logger.info(f"正在处理第{i+1}个网页")
            self.logger.debug(f"url_info: {url_info}")
            
            try:
                url = url_info['link']
                title = url_info.get('title', '')
                
                # 检查是否已经访问过相同概念
                if url in self.visited_url and target_concepts:
                    # 检查当前概念是否与已访问过的概念完全相同
                    is_identical = False
                    for visited_concepts in self.visited_url[url]:
                        if self._are_concepts_identical(target_concepts, visited_concepts):
                            is_identical = True
                            break
                    
                    if is_identical:
                        self.logger.info(f"已经浏览过 {url} 且概念相同，跳过")
                        print(f"已经浏览过 {url} 且概念相同，跳过")
                        continue
                
                cached_content = None
                # 检查缓存
                url_hash = self._get_url_hash(url)
                if url in self.visited_url:
                    cached_content = self.webpage_cache.get(url_hash)
                
                if cached_content:
                    self.logger.info(f"从缓存中获取网页内容: {title}")
                    print(f"从缓存中获取: {title}")
                    content = cached_content
                else:
                    
                    # 获取网页内容
                    self.logger.info(f"正在浏览: {title}")
                    self.logger.debug(f"URL: {url}")
                    print(f"正在浏览: {title}")
                    print(f"URL: {url}")
                    
                    # 判断是否为PDF
                    if url.lower().endswith('.pdf') or 'pdf' in url.lower():
                        content = extract_pdf_content(url)
                    else:
                        content = browse_webpage(url)
                    
                    # 缓存内容和概念信息
                    if content and len(content.strip()) > 100:
                        content = self.remove_urls(content)
                        self.webpage_cache[url_hash] = content
                        # 保存当前URL对应的概念信息
                        if target_concepts:
                            self.visited_url[url].append(target_concepts.copy())
                        self._save_cache()
                
            except KeyError as e:
                self.logger.error(f"url_info缺少必要的键: {e}, url_info内容: {url_info}")
                print(f"url_info缺少必要的键: {e}")
                continue
            
            try:
                if content and len(content.strip()) > 100:  # 确保有足够的内容
                    # 注意：visited_url现在是defaultdict(list)，不需要手动添加URL
                    # URL会在保存概念信息时自动添加
                    facts = self._extract_facts_from_content(content, title, n, url, concepts_text)
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
                self.logger.error(f"浏览 {url} 时出错: {e}")
                print(f"浏览 {url} 时出错: {e}")
                continue
        
        return all_facts
    
    def _extract_facts_from_content(self, content: str, title: str, n: int, url: str = "", concepts_text:str = "") -> List[Dict[str, str]]:
        """从内容中提取facts"""
        approx_tokens = len(content.split())
        print(f"url:{url}含有的token数大致为：{approx_tokens}")
        # 限制内容长度以避免token限制
        max_token = 12000
        if approx_tokens > max_token:
            content = ' '.join(content.split()[:max_token])
        
        prompt = f"""
You are a biology professor who needs to extract objective biological facts/knowledge points from the given webpage content for subsequent exam question generation.

Webpage Title: {title}
Webpage URL: {url}
Webpage Content:
{content}

Please extract {n} important biological facts from the above content. Each fact should be related to the concepts in [{concepts_text}].
1. Should be objective factual statements, not opinions or speculations
2. Should include complete prerequisite conditions (e.g., experimental phenomena and conclusions should provide specific experimental conditions and sources)
3. Should not be too simple, should be meaningful content with necessary contextual explanations
4. If the quantity requirement cannot be met, quality over quantity

Please return in JSON format as follows:
[
  {{
    "fact": "Relevant conditions or environment (prerequisites) + specific factual statement"
  }},
  {{
    "fact": "Another biological fact"
  }},
  ...
]

Only return the JSON array, each object should only contain the "fact" field, do not include other content.
"""
        
        messages = [{"role": "user", "content": prompt}]
        response_text, token_info = self.call_extractor(messages)
        self._update_token_stats(token_info)
        self.logger.info(f"从browse内容提取新事实Token使用: 输入{token_info['input_tokens']}, 输出{token_info['output_tokens']}, 总计{token_info['total_tokens']}")
        
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
        
        prompt = MERGE_FACTS.format(facts_text=facts_text)
        
        messages = [{"role": "user", "content": prompt}]
        response_text, _, token_info = chat_with_tools(messages, model=self.model)
        self._update_token_stats(token_info)
        self.logger.info(f"合并去重事实Token使用: 输入{token_info['input_tokens']}, 输出{token_info['output_tokens']}, 总计{token_info['total_tokens']}")
        
        try:
            merged_facts_data = json.loads(response_text.strip())
            if isinstance(merged_facts_data, list):
                # 将JSON数据转换为FactWithSource对象
                merged_facts = []
                for fact_data in merged_facts_data:
                    fact_obj = FactWithSource(
                        fact=fact_data.get('fact', ''),
                        source='web_search',
                        source_detail='合并自多个网页',
                        source_url=None,
                        source_title=None,
                    )
                    merged_facts.append(fact_obj)
                return merged_facts
            else:
                return facts  # 如果解析失败，返回原始facts
        except json.JSONDecodeError:
            self.logger.error(f"解析下面的json对象失败{merged_facts_data}")
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
        print(f"所有概念共找到 {len(search_results)} 个相关网页")
        
        # 步骤3: 浏览网页并提取facts
        print(f"\n步骤3: 浏览网页并提取facts...")
        concepts_text = chr(10).join([f"- {concept}" for concept in concepts])
        extracted_facts = self.browse_and_extract_facts(search_results, concepts_text, n, concepts)
        print(f"总共提取了 {len(extracted_facts)} 个facts")
        
        # 步骤4: 合并和去重
        #print(f"\n步骤4: 合并和去重facts...")
        #final_facts = self.merge_and_deduplicate_facts(extracted_facts)
        #print(f"最终得到 {len(final_facts)} 个unique facts")
        final_facts = extracted_facts
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
            },
            "token_stats": self.get_token_stats()
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
