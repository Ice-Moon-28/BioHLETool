"""
OMIM工具实现
Online Mendelian Inheritance in Man (OMIM) 数据库查询工具
支持基因、疾病、表型等信息查询
"""

import json
import re
from typing import Dict, Any, List, Optional
from urllib.parse import quote

from .base_tool import BaseTool


class OMIMTool(BaseTool):
    """OMIM数据库查询工具"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化OMIM工具
        
        Args:
            api_key: OMIM API密钥（可选，用于提高请求限制）
        """
        super().__init__(
            tool_name="omim",
            base_url="https://api.omim.org/api",
            timeout=30
        )
        self.api_key = api_key
        self.api_version = "v1.0"
        self.supported_entities = ["gene", "disease", "phenotype", "mim_number"]
        self.description = "OMIM人类基因和遗传疾病数据库查询工具"
        
        # 设置请求头
        if self.api_key:
            self.request_session.headers.update({
                'Authorization': f'Bearer {self.api_key}',
                'Accept-Encoding': 'gzip',
                'User-Agent': 'BioGen-OMIM-Tool/1.0'
            })
    
    def generate_atomic_task(self, entity: str, query_type: str = "gene", **kwargs) -> Dict[str, Any]:
        """
        生成原子任务
        
        Args:
            entity: 查询实体（基因名、疾病名等）
            query_type: 查询类型 ("gene", "disease", "phenotype")
            **kwargs: 其他参数
            
        Returns:
            原子任务字典
        """
        try:
            # 构建查询问题
            if query_type == "gene":
                question = f"基因 {entity} 在OMIM数据库中对应的MIM编号是什么？"
                search_field = "gene_symbols"
            elif query_type == "disease":
                question = f"疾病 {entity} 在OMIM数据库中的MIM编号是什么？"
                search_field = "titles"
            elif query_type == "phenotype":
                question = f"表型 {entity} 在OMIM数据库中对应的MIM编号是什么？"
                search_field = "titles"
            else:
                question = f"{entity} 在OMIM数据库中的MIM编号是什么？"
                search_field = "all_text"
            
            # 获取API端点
            endpoint = self.get_api_endpoint(entity, query_type=query_type, search_field=search_field)
            
            # 执行API调用
            response_data = self.make_api_request(endpoint)
            
            # 解析响应获取答案
            answer = self.parse_api_response(response_data, entity)
            
            return self.format_task_record(
                entity=entity,
                question=question,
                answer=answer,
                api_response=response_data,
                endpoint=endpoint,
                query_type=query_type,
                search_field=search_field
            )
            
        except Exception as e:
            return {
                "tool": self.tool_name,
                "i_T": entity,
                "Q": question if 'question' in locals() else f"查询{entity}的OMIM信息",
                "a": None,
                "C_excerpt": f"错误: {str(e)}",
                "meta": {"error": str(e), "query_type": query_type}
            }
    
    def validate_task(self, task_record: Dict[str, Any]) -> bool:
        """
        验证任务有效性（A通道验证）
        
        Args:
            task_record: 任务记录
            
        Returns:
            验证是否通过
        """
        try:
            entity = task_record.get("i_T")
            meta = task_record.get("meta", {})
            endpoint = meta.get("endpoint")
            
            if not endpoint and entity:
                # 重新构建端点
                query_type = meta.get("query_type", "gene")
                search_field = meta.get("search_field", "gene_symbols")
                endpoint = self.get_api_endpoint(entity, query_type=query_type, search_field=search_field)
            
            if not endpoint:
                return False
            
            # 执行API调用
            response_data = self.make_api_request(endpoint)
            
            # 解析响应
            predicted_answer = self.parse_api_response(response_data, entity)
            expected_answer = task_record.get("a")
            
            # 比较答案
            return self._compare_answers(predicted_answer, expected_answer)
            
        except Exception as e:
            print(f"OMIM验证失败: {e}")
            return False
    
    def get_api_endpoint(self, entity: str, query_type: str = "gene", search_field: str = "gene_symbols") -> str:
        """
        获取API端点URL - 使用NCBI OMIM镜像
        
        Args:
            entity: 查询实体
            query_type: 查询类型
            search_field: 搜索字段
            
        Returns:
            完整的API URL
        """
        # 使用NCBI的OMIM搜索接口，这是公开可访问的
        encoded_entity = quote(f"{entity}[gene]" if query_type == "gene" else entity)
        
        # NCBI E-utilities API for OMIM database
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        
        # 构建搜索URL - 先搜索获取ID列表
        search_url = f"{base_url}/esearch.fcgi"
        params = [
            "db=omim",
            f"term={encoded_entity}",
            "retmode=json",
            "retmax=5",
            "tool=biogen",
            "email=biogen@example.com"  # NCBI要求邮箱信息
        ]
        
        param_string = "&".join(params)
        return f"{search_url}?{param_string}"
    
    def parse_api_response(self, response_data: Any, entity: str) -> Optional[str]:
        """
        解析API响应获取答案 - NCBI E-utilities格式
        
        Args:
            response_data: API响应数据
            entity: 查询实体
            
        Returns:
            解析出的MIM编号，如果失败返回None
        """
        try:
            if isinstance(response_data, dict):
                # 解析NCBI E-utilities响应
                esearch_result = response_data.get("esearchresult", {})
                id_list = esearch_result.get("idlist", [])
                
                if id_list:
                    # NCBI OMIM数据库中的ID就是MIM编号
                    # 返回第一个匹配的MIM编号
                    mim_number = id_list[0]
                    
                    # 验证MIM编号格式（通常是6位数字）
                    if mim_number.isdigit() and len(mim_number) == 6:
                        return mim_number
                    elif mim_number.isdigit():
                        # 如果长度不足6位，在前面补0
                        return mim_number.zfill(6)
                    else:
                        return mim_number
                
                # 如果没有找到ID列表，检查错误信息
                error_list = esearch_result.get("errorlist", {})
                if error_list:
                    print(f"NCBI搜索错误: {error_list}")
                
            elif isinstance(response_data, str):
                # 如果响应是字符串，尝试解析JSON
                try:
                    parsed_data = json.loads(response_data)
                    return self.parse_api_response(parsed_data, entity)
                except json.JSONDecodeError:
                    # 从纯文本中提取MIM编号
                    return self._extract_mim_number_from_text(response_data)
            
            return None
            
        except Exception as e:
            print(f"OMIM响应解析失败: {e}")
            return None
    
    def _find_best_match(self, entry_list: List[Dict], entity: str) -> Optional[Dict]:
        """
        在条目列表中查找最佳匹配
        
        Args:
            entry_list: OMIM条目列表
            entity: 查询实体
            
        Returns:
            最佳匹配的条目
        """
        entity_upper = entity.upper()
        
        for entry_item in entry_list:
            entry = entry_item.get("entry", {})
            
            # 检查基因符号匹配
            gene_symbols = entry.get("geneSymbols", "")
            if entity_upper in gene_symbols.upper():
                return entry_item
            
            # 检查标题匹配
            titles = entry.get("titles", {})
            preferred_title = titles.get("preferredTitle", "")
            if entity.upper() in preferred_title.upper():
                return entry_item
            
            # 检查别名匹配
            alternative_titles = titles.get("alternativeTitles", "")
            if entity.upper() in alternative_titles.upper():
                return entry_item
        
        # 如果没有精确匹配，返回第一个结果
        return entry_list[0] if entry_list else None
    
    def _extract_mim_number_from_text(self, text: str) -> Optional[str]:
        """
        从文本中提取MIM编号
        
        Args:
            text: 响应文本
            
        Returns:
            提取的MIM编号
        """
        # MIM编号通常是6位数字
        mim_pattern = r'\b(\d{6})\b'
        matches = re.findall(mim_pattern, text)
        
        if matches:
            # 返回第一个找到的MIM编号
            return matches[0]
        
        return None
    
    def _compare_answers(self, predicted: Optional[str], expected: Optional[str]) -> bool:
        """
        比较预测答案和期望答案
        
        Args:
            predicted: 预测的答案
            expected: 期望的答案
            
        Returns:
            是否匹配
        """
        if not predicted or not expected:
            return False
        
        # 标准化答案格式
        pred_clean = str(predicted).strip()
        exp_clean = str(expected).strip()
        
        return pred_clean == exp_clean
    
    def generate_batch_tasks(self, entities: List[str], query_type: str = "gene", 
                           max_batch_size: int = 5) -> List[Dict[str, Any]]:
        """
        批量生成任务
        
        Args:
            entities: 实体列表
            query_type: 查询类型
            max_batch_size: 最大批次大小
            
        Returns:
            任务列表
        """
        tasks = []
        
        for i in range(0, len(entities), max_batch_size):
            batch = entities[i:i + max_batch_size]
            
            for entity in batch:
                task = self.generate_atomic_task(entity, query_type=query_type)
                if task.get("a"):  # 只保留有效答案的任务
                    tasks.append(task)
        
        return tasks
    
    def get_supported_query_types(self) -> List[str]:
        """
        获取支持的查询类型
        
        Returns:
            支持的查询类型列表
        """
        return ["gene", "disease", "phenotype", "syndrome", "disorder"]


def create_omim_tool(api_key: Optional[str] = None) -> OMIMTool:
    """
    创建OMIM工具实例
    
    Args:
        api_key: OMIM API密钥
        
    Returns:
        OMIM工具实例
    """
    return OMIMTool(api_key=api_key)


# 测试函数
def test_omim_tool():
    """测试OMIM工具功能"""
    tool = create_omim_tool()
    
    # 测试基因查询
    print("测试基因查询...")
    gene_task = tool.generate_atomic_task("BRCA1", query_type="gene")
    print(f"基因任务: {gene_task}")
    
    # 测试疾病查询
    print("\n测试疾病查询...")
    disease_task = tool.generate_atomic_task("Huntington disease", query_type="disease")
    print(f"疾病任务: {disease_task}")
    
    # 测试验证
    print("\n测试验证...")
    if gene_task.get("a"):
        validation_result = tool.validate_task(gene_task)
        print(f"验证结果: {validation_result}")


if __name__ == "__main__":
    test_omim_tool()