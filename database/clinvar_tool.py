"""
ClinVar 工具实现
用于查询基因变异的临床意义数据

ClinVar 是 NCBI 的公共数据库，收集基因变异与人类健康的关系信息
API 文档: https://www.ncbi.nlm.nih.gov/clinvar/docs/api/
"""

import re
import json
import urllib.parse
from typing import Dict, Any, Optional, List
from datetime import datetime

import sys
import os
biogen_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, biogen_root)

from tools.base_tool import BaseTool, ToolRegistry


class ClinVarTool(BaseTool):
    """ClinVar 基因变异临床意义查询工具"""
    
    def __init__(self):
        super().__init__(
            tool_name="clinvar",
            base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
            timeout=30
        )
        self.api_version = "v1"
        self.supported_entities = ["gene", "variant", "hgvs", "rsid"]
        self.description = "查询基因变异的临床意义、致病性分类和相关疾病信息"
        
        # ClinVar 数据库配置
        self.db_name = "clinvar"
        self.retmax = 50  # 返回结果数量限制
        
        # 临床意义分类映射
        self.significance_map = {
            "pathogenic": "致病性",
            "likely pathogenic": "可能致病性",
            "uncertain significance": "意义不明确",
            "likely benign": "可能良性",
            "benign": "良性",
            "conflicting interpretations": "解释冲突",
            "drug response": "药物反应",
            "association": "关联性",
            "risk factor": "风险因子",
            "protective": "保护性"
        }
    
    def generate_atomic_task(self, entity: str, **kwargs) -> Dict[str, Any]:
        """
        为给定基因或变异生成原子任务
        
        Args:
            entity: 基因名称或变异标识符
            **kwargs: 其他参数
                - query_type: 查询类型 ("gene", "variant", "hgvs", "rsid")
                - significance_filter: 临床意义过滤器
                
        Returns:
            原子任务记录
        """
        if not self.validate_entity(entity):
            raise ValueError(f"无效的基因或变异标识符: {entity}")
        
        query_type = kwargs.get("query_type", "gene")
        significance_filter = kwargs.get("significance_filter", None)
        
        # 构建查询
        search_term = self._build_search_term(entity, query_type, significance_filter)
        
        try:
            # 执行查询
            search_results = self._execute_search(search_term)
            
            if not search_results or len(search_results) == 0:
                # 如果没有结果，生成一个说明性的任务
                question = self._generate_question(entity, query_type)
                return self.format_task_record(
                    entity=entity,
                    question=question,
                    answer="在ClinVar数据库中未找到相关变异信息",
                    api_response={"message": "No results found", "count": 0},
                    endpoint=f"{self.base_url}/esearch.fcgi",
                    query_type=query_type,
                    search_term=search_term
                )
            
            # 获取详细信息
            detailed_results = self._fetch_detailed_results(search_results[:5])  # 限制前5个结果
            
            # 解析结果
            parsed_answer = self._parse_clinvar_results(detailed_results, entity)
            
            # 生成问题
            question = self._generate_question(entity, query_type)
            
            return self.format_task_record(
                entity=entity,
                question=question,
                answer=parsed_answer,
                api_response=detailed_results,
                endpoint=f"{self.base_url}/esummary.fcgi",
                query_type=query_type,
                search_term=search_term,
                result_count=len(search_results)
            )
            
        except Exception as e:
            raise RuntimeError(f"ClinVar查询失败: {str(e)}")
    
    def validate_task(self, task_record: Dict[str, Any]) -> bool:
        """
        验证任务有效性（A通道验证）
        
        Args:
            task_record: 任务记录
            
        Returns:
            验证是否通过
        """
        try:
            entity = task_record.get("i_T", "")
            expected_answer = task_record.get("a", "")
            
            if not entity or not expected_answer:
                return False
            
            # 基础格式验证
            if not self.validate_entity(entity):
                return False
            
            # 检查答案是否包含必要的ClinVar相关信息
            required_indicators = [
                "ClinVar", "变异", "临床意义", "记录", "找到"
            ]
            
            has_indicators = any(indicator in expected_answer for indicator in required_indicators)
            if not has_indicators:
                return False
            
            # 检查答案是否合理（不是错误信息）
            error_indicators = [
                "查询失败", "API错误", "连接超时", "服务不可用"
            ]
            
            has_errors = any(error in expected_answer for error in error_indicators)
            if has_errors:
                return False
            
            # 检查实体是否在答案中被正确引用
            if entity.upper() not in expected_answer.upper():
                return False
            
            # 简单的长度和格式检查
            if len(expected_answer) < 20 or len(expected_answer) > 1000:
                return False
            
            return True
            
        except Exception:
            return False
    
    def get_api_endpoint(self, entity: str, **kwargs) -> str:
        """
        获取API端点URL
        
        Args:
            entity: 查询实体
            **kwargs: 其他参数
            
        Returns:
            完整的API URL
        """
        query_type = kwargs.get("query_type", "gene")
        search_term = self._build_search_term(entity, query_type)
        
        params = {
            "db": self.db_name,
            "term": search_term,
            "retmode": "json",
            "retmax": self.retmax
        }
        
        query_string = urllib.parse.urlencode(params)
        return f"{self.base_url}/esearch.fcgi?{query_string}"
    
    def parse_api_response(self, response_data: Any, entity: str) -> Optional[str]:
        """
        解析API响应获取答案
        
        Args:
            response_data: API响应数据
            entity: 查询实体
            
        Returns:
            解析出的答案, 如果失败返回None
        """
        try:
            if isinstance(response_data, list) and len(response_data) > 0:
                return self._parse_clinvar_results(response_data, entity)
            elif isinstance(response_data, dict):
                if "esearchresult" in response_data:
                    # 搜索结果
                    id_list = response_data["esearchresult"].get("idlist", [])
                    if id_list:
                        # 需要进一步查询详细信息
                        detailed_results = self._fetch_detailed_results(id_list[:5])
                        return self._parse_clinvar_results(detailed_results, entity)
                    else:
                        return f"在ClinVar数据库中未找到{entity}的相关变异信息"
                elif "result" in response_data:
                    # 详细结果
                    results = list(response_data["result"].values())
                    results = [r for r in results if isinstance(r, dict)]
                    return self._parse_clinvar_results(results, entity)
            
            return None
            
        except Exception:
            return None
    
    def _build_search_term(self, entity: str, query_type: str, significance_filter: str = None) -> str:
        """构建搜索词"""
        # 清理实体名称
        entity = entity.strip().upper()
        
        if query_type == "gene":
            # 基因查询
            search_term = f'"{entity}"[gene]'
        elif query_type == "variant":
            # 变异查询
            search_term = f'"{entity}"[variant name]'
        elif query_type == "hgvs":
            # HGVS命名法查询
            search_term = f'"{entity}"[variant name]'
        elif query_type == "rsid":
            # rsID查询
            search_term = f'"{entity}"[variant id]'
        else:
            # 默认基因查询
            search_term = f'"{entity}"[gene]'
        
        # 添加临床意义过滤器
        if significance_filter:
            search_term += f' AND "{significance_filter}"[clinical significance]'
        
        return search_term
    
    def _execute_search(self, search_term: str) -> List[str]:
        """执行搜索查询"""
        params = {
            "db": self.db_name,
            "term": search_term,
            "retmode": "json",
            "retmax": self.retmax
        }
        
        url = f"{self.base_url}/esearch.fcgi"
        response = self.make_api_request(url, params=params)
        
        if isinstance(response, dict) and "esearchresult" in response:
            return response["esearchresult"].get("idlist", [])
        
        return []
    
    def _fetch_detailed_results(self, id_list: List[str]) -> List[Dict[str, Any]]:
        """获取详细结果"""
        if not id_list:
            return []
        
        params = {
            "db": self.db_name,
            "id": ",".join(id_list),
            "retmode": "json"
        }
        
        url = f"{self.base_url}/esummary.fcgi"
        response = self.make_api_request(url, params=params)
        
        if isinstance(response, dict) and "result" in response:
            results = []
            for uid in id_list:
                if uid in response["result"]:
                    result_data = response["result"][uid]
                    if isinstance(result_data, dict):
                        results.append(result_data)
            return results
        
        return []
    
    def _parse_clinvar_results(self, results: List[Dict[str, Any]], entity: str) -> str:
        """解析ClinVar结果"""
        if not results:
            return f"在ClinVar数据库中未找到{entity}的相关变异信息"
        
        # 统计临床意义
        significance_counts = {}
        diseases = set()
        variants = []

        with open("tools/clinvar_tool.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        
        for result in results:
            # 提取临床意义
            clinical_significance = result.get("clinical_significance", "")
            if clinical_significance:
                significance_counts[clinical_significance] = significance_counts.get(clinical_significance, 0) + 1
            
            # 提取相关疾病
            disease_names = result.get("disease_names", "")
            if disease_names:
                diseases.update([d.strip() for d in disease_names.split(",")])
            
            # 提取变异信息
            variant_name = result.get("title", "")
            if variant_name:
                variants.append(variant_name)
        
        # 构建回答
        answer_parts = []
        
        # 基本信息
        answer_parts.append(f"在ClinVar数据库中找到{len(results)}个与{entity}相关的变异记录")
        
        # 临床意义统计
        if significance_counts:
            sig_text = []
            for sig, count in sorted(significance_counts.items(), key=lambda x: x[1], reverse=True):
                chinese_sig = self.significance_map.get(sig.lower(), sig)
                sig_text.append(f"{chinese_sig}({count}个)")
            answer_parts.append(f"临床意义分布：{', '.join(sig_text[:3])}")  # 只显示前3个
        
        # 相关疾病
        if diseases:
            disease_list = list(diseases)[:3]  # 只显示前3个疾病
            answer_parts.append(f"主要相关疾病：{', '.join(disease_list)}")
        
        # 示例变异
        if variants:
            example_variants = variants[:2]  # 只显示前2个变异
            answer_parts.append(f"示例变异：{'; '.join(example_variants)}")
        
        return "；".join(answer_parts)
    
    def _generate_question(self, entity: str, query_type: str) -> str:
        """生成问题"""
        if query_type == "gene":
            return f"在ClinVar数据库中查询{entity}基因的变异信息，包括临床意义和相关疾病？"
        elif query_type == "variant":
            return f"在ClinVar数据库中查询变异{entity}的临床意义和致病性分类？"
        elif query_type == "hgvs":
            return f"在ClinVar数据库中查询HGVS命名{entity}的临床意义评估？"
        elif query_type == "rsid":
            return f"在ClinVar数据库中查询rsID {entity}的变异信息和临床意义？"
        else:
            return f"在ClinVar数据库中查询{entity}的基因变异和临床意义信息？"
    
    def validate_entity(self, entity: str) -> bool:
        """
        验证输入实体的格式
        
        Args:
            entity: 待验证的实体
            
        Returns:
            是否为有效实体
        """
        if not super().validate_entity(entity):
            return False
        
        entity = entity.strip()
        
        # 基因名称模式（大写字母开头，可包含数字）
        gene_pattern = r'^[A-Z][A-Z0-9]*[A-Z0-9]?$'
        
        # rsID模式
        rsid_pattern = r'^rs\d+$'
        
        # HGVS模式（简化）
        hgvs_pattern = r'^[A-Z]+_\d+\.\d+:'
        
        # 检查是否匹配任何一种模式
        if (re.match(gene_pattern, entity.upper()) or 
            re.match(rsid_pattern, entity.lower()) or 
            re.search(hgvs_pattern, entity)):
            return True
        
        # 允许一些特殊情况（如基因名包含连字符）
        if len(entity) >= 2 and len(entity) <= 50:
            return True
        
        return False


# 注册工具
def register_clinvar_tool():
    """注册ClinVar工具到工具注册表"""
    tool = ClinVarTool()
    ToolRegistry.register_tool(tool)
    return tool


if __name__ == "__main__":
    # 测试代码
    print("测试ClinVar工具...")
    
    tool = ClinVarTool()
    
    # 测试用例
    test_cases = [
        {"entity": "BRCA1", "query_type": "gene"},
        # {"entity": "TP53", "query_type": "gene"},
        # {"entity": "rs80357906", "query_type": "rsid"}
    ]
    
    for case in test_cases:
        try:
            print(f"\n测试查询: {case['entity']} (类型: {case['query_type']})")
            
            task = tool.generate_atomic_task(**case)
            
            print(f"问题: {task['Q']}")
            print(f"答案: {task['a']}")
            print(f"端点: {task['meta']['endpoint']}")
            
            # 验证任务
            is_valid = tool.validate_task(task)
            print(f"验证结果: {'通过' if is_valid else '失败'}")
            
        except Exception as e:
            print(f"测试失败: {str(e)}")
    
    print("\nClinVar工具测试完成")