"""
DrugBank工具实现
药物信息和靶点数据查询工具
由于DrugBank API需要付费，使用ChEMBL和NIH等公开API作为替代
"""

import json
import re
from typing import Dict, Any, List, Optional
from urllib.parse import quote

from .base_tool import BaseTool


class DrugBankTool(BaseTool):
    """DrugBank风格的药物信息查询工具"""
    
    def __init__(self):
        """
        初始化DrugBank工具
        使用ChEMBL作为主要数据源
        """
        super().__init__(
            tool_name="drugbank",
            base_url="https://www.ebi.ac.uk/chembl/api/data",
            timeout=30
        )
        self.api_version = "v1"
        self.supported_entities = ["drug", "compound", "target"]
        self.description = "药物信息和靶点数据查询工具"
        
        # 设置请求头
        self.request_session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'BioGen-DrugBank-Tool/1.0'
        })
    
    def generate_atomic_task(self, entity: str, query_type: str = "drug", **kwargs) -> Dict[str, Any]:
        """
        生成原子任务
        
        Args:
            entity: 查询实体（药物名、化合物名等）
            query_type: 查询类型 ("drug", "compound", "target", "indication")
            **kwargs: 其他参数
            
        Returns:
            原子任务字典
        """
        try:
            # 构建查询问题
            if query_type == "drug":
                question = f"药物 {entity} 在药物数据库中的主要靶点ID是什么？"
            elif query_type == "compound":
                question = f"化合物 {entity} 的ChEMBL ID是什么？"
            elif query_type == "target":
                question = f"靶点 {entity} 对应的UniProt ID是什么？"
            elif query_type == "indication":
                question = f"药物 {entity} 的主要适应症是什么？"
            else:
                question = f"{entity} 在药物数据库中对应的ID是什么？"
            
            # 获取API端点
            endpoint = self.get_api_endpoint(entity, query_type=query_type)
            
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
                query_type=query_type
            )
            
        except Exception as e:
            return {
                "tool": self.tool_name,
                "i_T": entity,
                "Q": question if 'question' in locals() else f"查询{entity}的药物信息",
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
                query_type = meta.get("query_type", "drug")
                endpoint = self.get_api_endpoint(entity, query_type=query_type)
            
            if not endpoint:
                return False
            
            # 执行API调用
            response_data = self.make_api_request(endpoint)
            
            # 解析响应
            predicted_answer = self.parse_api_response(response_data, entity, meta.get("query_type", "drug"))
            expected_answer = task_record.get("a")
            
            # 比较答案
            return self._compare_answers(predicted_answer, expected_answer)
            
        except Exception as e:
            print(f"DrugBank验证失败: {e}")
            return False
    
    def get_api_endpoint(self, entity: str, query_type: str = "drug") -> str:
        """
        获取API端点URL - 使用ChEMBL API
        
        Args:
            entity: 查询实体
            query_type: 查询类型
            
        Returns:
            完整的API URL
        """
        encoded_entity = quote(entity)
        
        # ChEMBL API endpoints
        base_url = self.base_url
        
        if query_type == "drug" or query_type == "compound":
            # 搜索药物/化合物
            endpoint = f"{base_url}/molecule/search"
            params = f"q={encoded_entity}&format=json&limit=5"
            
        elif query_type == "target":
            # 搜索靶点
            endpoint = f"{base_url}/target/search"
            params = f"q={encoded_entity}&format=json&limit=5"
            
        elif query_type == "indication":
            # 搜索药物适应症 - 使用drug indication endpoint
            endpoint = f"{base_url}/drug_indication/search"
            params = f"q={encoded_entity}&format=json&limit=5"
            
        else:
            # 默认搜索分子
            endpoint = f"{base_url}/molecule/search"
            params = f"q={encoded_entity}&format=json&limit=5"
        
        return f"{endpoint}?{params}"
    
    def parse_api_response(self, response_data: Any, entity: str, query_type: str) -> Optional[str]:
        """
        解析API响应获取答案 - ChEMBL API格式
        
        Args:
            response_data: API响应数据
            entity: 查询实体
            query_type: 查询类型
            
        Returns:
            解析出的ID或信息，如果失败返回None
        """
        try:
            if isinstance(response_data, dict):
                molecules = response_data.get("molecules", [])
                targets = response_data.get("targets", [])
                indications = response_data.get("drug_indications", [])
                
                if query_type == "drug" or query_type == "compound":
                    if molecules:
                        # 返回第一个匹配的分子ID
                        first_mol = molecules[0]
                        if "molecule_chembl_id" in first_mol:
                            return first_mol["molecule_chembl_id"]
                        elif "chembl_id" in first_mol:
                            return first_mol["chembl_id"]
                            
                elif query_type == "target":
                    if targets:
                        # 返回第一个匹配的靶点ID
                        first_target = targets[0]
                        if "target_chembl_id" in first_target:
                            return first_target["target_chembl_id"]
                        elif "chembl_id" in first_target:
                            return first_target["chembl_id"]
                        # 尝试提取UniProt ID
                        target_components = first_target.get("target_components", [])
                        if target_components:
                            for component in target_components:
                                accession = component.get("accession")
                                if accession and accession.startswith("P"):  # UniProt格式
                                    return accession
                                    
                elif query_type == "indication":
                    if indications:
                        # 返回第一个适应症
                        first_indication = indications[0]
                        indication_text = first_indication.get("indication", "")
                        if indication_text:
                            return indication_text
                
                # 备选：从通用结构中提取
                for key in ["molecules", "targets", "drug_indications"]:
                    if key in response_data and response_data[key]:
                        first_item = response_data[key][0]
                        return self._extract_id_from_item(first_item, query_type)
            
            return None
            
        except Exception as e:
            print(f"DrugBank响应解析失败: {e}")
            return None
    
    def _extract_id_from_item(self, item: Dict[str, Any], query_type: str) -> Optional[str]:
        """
        从API项目中提取ID
        
        Args:
            item: API返回的单个项目
            query_type: 查询类型
            
        Returns:
            提取的ID
        """
        # 优先ID字段
        id_fields = [
            "molecule_chembl_id", "target_chembl_id", "chembl_id", 
            "compound_chembl_id", "accession", "uniprot_id"
        ]
        
        for field in id_fields:
            if field in item and item[field]:
                return str(item[field])
        
        # 对于靶点，尝试从target_components提取UniProt
        if query_type == "target" and "target_components" in item:
            components = item["target_components"]
            if components:
                for component in components:
                    accession = component.get("accession", "")
                    if accession and accession.startswith("P"):
                        return accession
        
        # 对于适应症，返回indication文本
        if query_type == "indication" and "indication" in item:
            return item["indication"]
        
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
    
    def generate_batch_tasks(self, entities: List[str], query_type: str = "drug", 
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
        return ["drug", "compound", "target", "indication"]
    
    def get_example_entities(self) -> Dict[str, List[str]]:
        """
        获取示例实体
        
        Returns:
            按查询类型分组的示例实体
        """
        return {
            "drug": ["Aspirin", "Ibuprofen", "Paracetamol", "Morphine", "Insulin"],
            "compound": ["Caffeine", "Glucose", "Adenosine", "Dopamine", "Serotonin"],
            "target": ["EGFR", "TP53", "BRCA1", "VEGFA", "TNF"],
            "indication": ["Cancer", "Diabetes", "Hypertension", "Pain", "Infection"]
        }


def create_drugbank_tool() -> DrugBankTool:
    """
    创建DrugBank工具实例
    
    Returns:
        DrugBank工具实例
    """
    return DrugBankTool()


# 测试函数
def test_drugbank_tool():
    """测试DrugBank工具功能"""
    tool = create_drugbank_tool()
    
    # 测试药物查询
    print("测试药物查询...")
    drug_task = tool.generate_atomic_task("Aspirin", query_type="drug")
    print(f"药物任务: {drug_task}")
    
    # 测试化合物查询
    print("\n测试化合物查询...")
    compound_task = tool.generate_atomic_task("Caffeine", query_type="compound")
    print(f"化合物任务: {compound_task}")

    # 测试靶点查询
    print("\n测试靶点查询...")
    target_task = tool.generate_atomic_task("EGFR", query_type="target")
    print(f"靶点任务: {target_task}")

    # 测试适应症查询
    print("\n测试适应症查询...")
    indication_task = tool.generate_atomic_task("Caffeine", query_type="indication")
    print(f"适应症任务: {indication_task}")

    # 测试验证
    print("\n测试验证...")
    if drug_task.get("a"):
        validation_result = tool.validate_task(drug_task)
        print(f"验证结果: {validation_result}")


if __name__ == "__main__":
    test_drugbank_tool()