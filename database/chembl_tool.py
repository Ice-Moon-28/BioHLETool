"""
ChEMBL 工具实现
用于查询化合物的生物活性数据

ChEMBL 是一个大型的生物活性数据库，包含药物发现中的化合物、靶点和生物活性数据
API 文档: https://chembl.gitbook.io/chembl-interface-documentation/web-services
"""

import re
import json
from typing import Dict, Any, Optional, List
from urllib.parse import quote

from .base_tool import BaseTool, ToolRegistry


class ChEMBLTool(BaseTool):
    """ChEMBL 药物化合物和生物活性数据工具"""
    
    def __init__(self):
        super().__init__(
            tool_name="chembl",
            base_url="https://www.ebi.ac.uk/chembl/api/data",
            timeout=30
        )
        self.api_version = "v1"
        self.supported_entities = ["compound", "drug_name", "chembl_id"]
        self.description = "查询化合物的生物活性数据、靶点信息和药物特性"
    
    def generate_atomic_task(self, entity: str, **kwargs) -> Dict[str, Any]:
        """
        为给定化合物生成原子任务
        
        Args:
            entity: 化合物名称或SMILES或ChEMBL ID
            **kwargs: 其他参数
            
        Returns:
            原子任务记录
        """
        if not self.validate_entity(entity):
            raise ValueError(f"无效的化合物实体: {entity}")
        
        # 获取API端点
        endpoint = self.get_api_endpoint(entity)
        
        # 查询ChEMBL数据
        try:
            response_data = self.make_api_request(endpoint)

            with open("chembl_response.json", "w") as f:
                json.dump(response_data, f, indent=4)

            # 解析响应获取ChEMBL ID
            chembl_id = self.parse_api_response(response_data, entity)
            
            if not chembl_id:
                raise ValueError(f"未找到化合物 {entity} 的ChEMBL数据")
            
            # 生成问题
            question = f"化合物 '{entity}' 在 ChEMBL 数据库中对应的 ChEMBL ID 是什么？"
            
            return self.format_task_record(
                entity=entity,
                question=question,
                answer=chembl_id,
                api_response=response_data,
                endpoint=endpoint,
                compound_type=self._detect_compound_type(entity)
            )
            
        except Exception as e:
            raise RuntimeError(f"生成ChEMBL任务失败: {str(e)}")
    
    def validate_task(self, task_record: Dict[str, Any]) -> bool:
        """
        验证ChEMBL任务的有效性
        
        Args:
            task_record: 任务记录
            
        Returns:
            验证是否通过
        """
        try:
            entity = task_record.get("i_T")
            expected_answer = task_record.get("a")
            
            if not entity or not expected_answer:
                return False
            
            # 重新查询验证答案
            endpoint = self.get_api_endpoint(entity)
            response_data = self.make_api_request(endpoint)
            actual_answer = self.parse_api_response(response_data, entity)
            
            # 比较答案
            return self._compare_chembl_ids(actual_answer, expected_answer)
            
        except Exception:
            return False
    
    def get_api_endpoint(self, entity: str, **kwargs) -> str:
        """
        构建ChEMBL API查询端点
        
        Args:
            entity: 化合物实体
            **kwargs: 其他参数
            
        Returns:
            API端点URL
        """
        compound_type = self._detect_compound_type(entity)
        
        if compound_type == "chembl_id":
            # 直接通过ChEMBL ID查询
            return f"{self.base_url}/molecule/{entity}"
        elif compound_type == "smiles":
            # 通过SMILES查询
            encoded_smiles = quote(entity)
            return f"{self.base_url}/molecule/search?q={encoded_smiles}&format=json"
        else:
            # 通过名称查询
            encoded_name = quote(entity)
            return f"{self.base_url}/molecule/search?q={encoded_name}&format=json"
    
    def parse_api_response(self, response_data: Any, entity: str) -> Optional[str]:
        """
        解析ChEMBL API响应获取ChEMBL ID
        
        Args:
            response_data: API响应数据
            entity: 查询实体
            
        Returns:
            ChEMBL ID或None
        """
        try:
            if isinstance(response_data, dict):
                # 直接ID查询的响应
                if "molecule_chembl_id" in response_data:
                    return response_data["molecule_chembl_id"]
                
                # 搜索查询的响应
                if "molecules" in response_data:
                    molecules = response_data["molecules"]
                    if molecules and len(molecules) > 0:
                        return molecules[0].get("molecule_chembl_id")
                
                # 其他格式的响应
                if "molecule" in response_data:
                    molecule = response_data["molecule"]
                    if isinstance(molecule, list) and len(molecule) > 0:
                        return molecule[0].get("molecule_chembl_id")
                    elif isinstance(molecule, dict):
                        return molecule.get("molecule_chembl_id")
            
            # 尝试从文本中提取ChEMBL ID
            if hasattr(response_data, 'get') and response_data.get('raw_text'):
                text = response_data['raw_text']
                chembl_match = re.search(r'CHEMBL\d+', text)
                if chembl_match:
                    return chembl_match.group()
            
            return None
            
        except Exception:
            return None
    
    def _detect_compound_type(self, entity: str) -> str:
        """
        检测化合物实体的类型
        
        Args:
            entity: 化合物实体
            
        Returns:
            实体类型：chembl_id, smiles, 或 name
        """
        entity = entity.strip().upper()
        
        # ChEMBL ID格式：CHEMBL123456
        if re.match(r'^CHEMBL\d+$', entity):
            return "chembl_id"
        
        # SMILES格式检测（简单启发式）
        if any(char in entity for char in ['(', ')', '[', ']', '=', '#']):
            return "smiles"
        
        # 默认为化合物名称
        return "name"
    
    def _compare_chembl_ids(self, id1: Optional[str], id2: Optional[str]) -> bool:
        """
        比较两个ChEMBL ID是否相等
        
        Args:
            id1: 第一个ID
            id2: 第二个ID
            
        Returns:
            是否相等
        """
        if not id1 or not id2:
            return False
        
        # 标准化格式并比较
        clean_id1 = id1.strip().upper()
        clean_id2 = id2.strip().upper()
        
        return clean_id1 == clean_id2
    
    def validate_entity(self, entity: str) -> bool:
        """
        验证化合物实体格式
        
        Args:
            entity: 化合物实体
            
        Returns:
            是否为有效格式
        """
        if not super().validate_entity(entity):
            return False
        
        entity = entity.strip()
        
        # 检查长度限制
        if len(entity) > 500:  # SMILES可能比较长
            return False
        
        # 检查是否包含明显的无效字符
        invalid_chars = ['<', '>', '&', '"', "'"]
        if any(char in entity for char in invalid_chars):
            return False
        
        return True


# 注册工具到工具注册表
def register_chembl_tool():
    """注册ChEMBL工具"""
    tool = ChEMBLTool()
    ToolRegistry.register_tool(tool)
    return tool


# 便利函数
def build_chembl_question(compound: str) -> Dict[str, Any]:
    """
    为化合物构建ChEMBL问题（兼容现有接口）
    
    Args:
        compound: 化合物名称
        
    Returns:
        任务记录
    """
    tool = ChEMBLTool()
    return tool.generate_atomic_task(compound)


if __name__ == "__main__":
    # 测试代码
    tool = ChEMBLTool()
    
    # 测试化合物
    test_compounds = [
        "aspirin",
        # "caffeine",
        # "CHEMBL25",
    ]
    
    for compound in test_compounds:
        try:
            print(f"\n测试化合物: {compound}")
            task = tool.generate_atomic_task(compound)
            print(f"问题: {task['Q']}")
            print(f"答案: {task['a']}")
            
            # 验证任务
            is_valid = tool.validate_task(task)
            print(f"验证结果: {'通过' if is_valid else '失败'}")
            
        except Exception as e:
            print(f"错误: {e}")