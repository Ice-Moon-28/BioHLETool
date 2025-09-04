"""
Reactome工具实现
Reactome生物反应通路数据库查询工具
支持通路、基因、物种等信息查询
"""

import json
import re
from typing import Dict, Any, List, Optional
from urllib.parse import quote

from util import edit_distance

from .base_tool import BaseTool


class ReactomeTool(BaseTool):
    """Reactome通路数据库查询工具"""
    
    def __init__(self):
        """
        初始化Reactome工具
        """
        super().__init__(
            tool_name="reactome",
            base_url="https://reactome.org/ContentService",
            timeout=30
        )
        self.api_version = "v1.0"
        self.supported_entities = ["gene", "protein", "pathway", "molecule", "species"]
        self.description = "Reactome生物反应通路数据库查询工具"
        
        # 设置请求头
        self.request_session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'BioGen-Reactome-Tool/1.0'
        })
    
    def generate_atomic_task(self, entity: str, query_type: str = "gene", species: str = "Homo sapiens", **kwargs) -> Dict[str, Any]:
        """
        生成原子任务
        
        Args:
            entity: 查询实体（基因名、通路名等）
            query_type: 查询类型 ("gene", "pathway", "protein", "molecule")
            species: 物种名称，默认为人类
            **kwargs: 其他参数
            
        Returns:
            原子任务字典
        """
        try:
            # 构建查询问题
            if query_type == "gene":
                question = f"基因 {entity} 在Reactome数据库中参与的主要通路ID是什么？"
            elif query_type == "pathway":
                question = f"通路 {entity} 在Reactome数据库中涉及到的蛋白质与基因是什么？"
            elif query_type == "protein":
                question = f"蛋白质 {entity} 在Reactome数据库中对应的稳定ID是什么？"
            else:
                question = f"{entity} 在Reactome数据库中的稳定ID是什么？"
            
            # 获取API端点
            endpoint = self.get_api_endpoint(entity, query_type=query_type, species=species, **kwargs)
            
            # 执行API调用
            response_data = self.make_api_request(endpoint)
            
            # 解析响应获取答案
            answer = self.parse_api_response(response_data, entity, query_type)
            
            return self.format_task_record(
                entity=entity,
                question=question,
                answer=answer,
                api_response=response_data,
                endpoint=endpoint,
                query_type=query_type,
                species=species
            )
            
        except Exception as e:
            return {
                "tool": self.tool_name,
                "i_T": entity,
                "Q": question if 'question' in locals() else f"查询{entity}的Reactome信息",
                "a": None,
                "C_excerpt": f"错误: {str(e)}",
                "meta": {"error": str(e), "query_type": query_type, "species": species}
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
                species = meta.get("species", "Homo sapiens")
                endpoint = self.get_api_endpoint(entity, query_type=query_type, species=species)
            
            if not endpoint:
                return False
            
            # 执行API调用
            response_data = self.make_api_request(endpoint)
            
            # 解析响应
            predicted_answer = self.parse_api_response(response_data, entity, meta.get("query_type", "gene"))
            expected_answer = task_record.get("a")
            
            # 比较答案
            return self._compare_answers(predicted_answer, expected_answer)
            
        except Exception as e:
            print(f"Reactome验证失败: {e}")
            return False
    
    def get_api_endpoint(self, entity: str, query_type: str = "gene", species: str = "Homo sapiens", **kwargs) -> str:
        """
        获取API端点URL - 使用Reactome搜索API
        
        Args:
            entity: 查询实体
            query_type: 查询类型
            species: 物种
            
        Returns:
            完整的API URL
        """

        if query_type in ['gene']:
            encoded_entity = quote(entity)
            encoded_species = quote(species.replace(" ", "+"))
            
            # 使用Reactome搜索API
            base_search_url = f"{self.base_url}/search/query"
            
            if edit_distance("Homo sapiens", species.lower()) <= 2:
                # 对于人类，可以不指定物种参数
                return f"{base_search_url}?query={encoded_entity}"
            else:
                # 对于其他物种，包含物种参数
                return f"{base_search_url}?query={encoded_entity}&species={encoded_species}"
        elif query_type in ['pathway']:
            # 对于通路查询，需要提供通路ID
            pathway_id = kwargs.get("pathway_id")

    def parse_api_response(self, response_data: Any, entity: str, query_type: str) -> Optional[str]:
        """
        解析API响应获取答案 - Reactome搜索API格式
        
        Args:
            response_data: API响应数据
            entity: 查询实体
            query_type: 查询类型
            
        Returns:
            解析出的稳定ID，如果失败返回None
        """
        try:
            if isinstance(response_data, dict):
                # 解析Reactome搜索API响应
                results = response_data.get("results", [])
                
                if not results:
                    return None
                
                # 查找最佳匹配的结果组
                for result_group in results:
                    entries = result_group.get("entries", [])
                    type_name = result_group.get("typeName", "")
                    
                    # 优先选择蛋白质或基因相关的结果
                    if query_type == "gene" and type_name.lower() in ["protein", "entitywithaccessionedsequence"]:
                        if entries:
                            first_entry = entries[0]
                            stable_id = self._extract_stable_id(first_entry)
                            if stable_id:
                                return stable_id
                    
                    # 如果没有找到理想类型，取第一个有效结果
                    if entries:
                        first_entry = entries[0]
                        stable_id = self._extract_stable_id(first_entry)
                        if stable_id:
                            return stable_id
                
                return None
                
            elif isinstance(response_data, str):
                # 如果响应是字符串，尝试解析JSON
                try:
                    parsed_data = json.loads(response_data)
                    return self.parse_api_response(parsed_data, entity, query_type)
                except json.JSONDecodeError:
                    # 从纯文本中提取稳定ID
                    return self._extract_stable_id_from_text(response_data)
            
            return None
            
        except Exception as e:
            print(f"Reactome响应解析失败: {e}")
            return None
    
    def _extract_stable_id(self, data: Dict[str, Any]) -> Optional[str]:
        """
        从响应数据中提取稳定ID
        
        Args:
            data: 响应数据字典
            
        Returns:
            稳定ID字符串
        """
        # Reactome稳定ID通常以"R-"开头
        stable_id_fields = [
            "stId", "stableId", "stable_id", "id", 
            "dbId", "reactomeId", "pathway_id"
        ]
        
        for field in stable_id_fields:
            if field in data:
                stable_id = str(data[field])
                if stable_id.startswith("R-") or stable_id.isdigit():
                    return stable_id
        
        # 如果没有找到标准字段，尝试从名称或其他字段提取
        if "displayName" in data:
            display_name = data["displayName"]
            # 从显示名称中提取可能的ID
            id_match = re.search(r'(R-[A-Z]{3}-\d+)', display_name)
            if id_match:
                return id_match.group(1)
        
        return None
    
    def _extract_stable_id_from_text(self, text: str) -> Optional[str]:
        """
        从文本中提取Reactome稳定ID
        
        Args:
            text: 响应文本
            
        Returns:
            提取的稳定ID
        """
        # Reactome稳定ID格式：R-HSA-123456, R-MMU-123456 等
        stable_id_pattern = r'\b(R-[A-Z]{3}-\d+)\b'
        matches = re.findall(stable_id_pattern, text)
        
        if matches:
            return matches[0]
        
        # 备选：查找纯数字ID（数据库ID）
        db_id_pattern = r'\b(\d{6,})\b'
        db_matches = re.findall(db_id_pattern, text)
        
        if db_matches:
            return db_matches[0]
        
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
                           species: str = "Homo sapiens", max_batch_size: int = 5) -> List[Dict[str, Any]]:
        """
        批量生成任务
        
        Args:
            entities: 实体列表
            query_type: 查询类型
            species: 物种
            max_batch_size: 最大批次大小
            
        Returns:
            任务列表
        """
        tasks = []
        
        for i in range(0, len(entities), max_batch_size):
            batch = entities[i:i + max_batch_size]
            
            for entity in batch:
                task = self.generate_atomic_task(entity, query_type=query_type, species=species)
                if task.get("a"):  # 只保留有效答案的任务
                    tasks.append(task)
        
        return tasks
    
    def get_supported_species(self) -> List[str]:
        """
        获取支持的物种列表
        
        Returns:
            支持的物种列表
        """
        return [
            "Homo sapiens",      # 人类
            "Mus musculus",      # 小鼠
            "Rattus norvegicus", # 大鼠
            "Danio rerio",       # 斑马鱼
            "Saccharomyces cerevisiae",  # 酿酒酵母
            "Caenorhabditis elegans",    # 线虫
            "Drosophila melanogaster",   # 果蝇
            "Gallus gallus",     # 鸡
            "Sus scrofa",        # 猪
            "Bos taurus"         # 牛
        ]
    
    def get_supported_query_types(self) -> List[str]:
        """
        获取支持的查询类型
        
        Returns:
            支持的查询类型列表
        """
        return ["gene", "protein", "pathway", "molecule", "reaction", "complex"]


def create_reactome_tool() -> ReactomeTool:
    """
    创建Reactome工具实例
    
    Returns:
        Reactome工具实例
    """
    return ReactomeTool()


# 测试函数
def test_reactome_tool():
    """测试Reactome工具功能"""
    tool = create_reactome_tool()
    
    # 测试基因查询
    print("测试基因查询...")
    gene_task = tool.generate_atomic_task("TP53", query_type="gene")
    print(f"基因任务: {gene_task}")

    print("测试蛋白质查询...")
    gene_task = tool.generate_atomic_task("BRCA1", query_type="gene")
    print(f"蛋白质任务: {gene_task}")
    
    # 测试通路查询
    print("\n测试通路查询...")
    pathway_task = tool.generate_atomic_task("R-HSA-69488", query_type="pathway")
    print(f"通路任务: {pathway_task}")
    
    # 测试验证
    print("\n测试验证...")
    if gene_task.get("a"):
        validation_result = tool.validate_task(gene_task)
        print(f"验证结果: {validation_result}")


if __name__ == "__main__":
    test_reactome_tool()