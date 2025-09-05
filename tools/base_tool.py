"""
BioGen 工具基类
定义所有生物医学工具的统一接口和公共功能
"""

import json
import requests
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime


class BaseTool(ABC):
    """生物医学工具基类"""
    
    def __init__(self, tool_name: str, base_url: str, timeout: int = 30):
        """
        初始化工具
        
        Args:
            tool_name: 工具名称
            base_url: API 基础URL
            timeout: 请求超时时间
        """
        self.tool_name = tool_name
        self.base_url = base_url
        self.timeout = timeout
        self.request_session = requests.Session()
        
    @abstractmethod
    def generate_atomic_task(self, entity: str, **kwargs) -> Dict[str, Any]:
        """
        生成原子任务
        
        Args:
            entity: 输入实体（基因、化合物、蛋白质等）
            **kwargs: 其他参数
            
        Returns:
            原子任务字典，包含 tool, i_T, Q, a, C_excerpt, meta
        """
        pass
    
    @abstractmethod
    def validate_task(self, task_record: Dict[str, Any]) -> bool:
        """
        验证任务有效性（A通道验证）
        
        Args:
            task_record: 任务记录
            
        Returns:
            验证是否通过
        """
        pass
    
    @abstractmethod
    def get_api_endpoint(self, entity: str, **kwargs) -> str:
        """
        获取API端点URL
        
        Args:
            entity: 查询实体
            **kwargs: 其他参数
            
        Returns:
            完整的API URL
        """
        pass
    
    @abstractmethod
    def parse_api_response(self, response_data: Any, entity: str) -> Optional[str]:
        """
        解析API响应获取答案
        
        Args:
            response_data: API响应数据
            entity: 查询实体
            
        Returns:
            解析出的答案，如果失败返回None
        """
        pass
    
    def make_api_request(self, url: str, method: str = "GET", **kwargs) -> Any:
        """
        发起API请求的通用方法
        
        Args:
            url: 请求URL
            method: HTTP方法
            **kwargs: 其他请求参数
            
        Returns:
            API响应数据
        """
        try:
            if method.upper() == "GET":
                response = self.request_session.get(url, timeout=self.timeout, **kwargs)
            elif method.upper() == "POST":
                response = self.request_session.post(url, timeout=self.timeout, **kwargs)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")
            
            response.raise_for_status()
            
            # 尝试解析JSON，失败时返回原始文本
            try:
                return response.json()
            except (json.JSONDecodeError, requests.exceptions.JSONDecodeError):
                # 对于STRING这样的TSV API，直接返回文本
                return response.text
                
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API请求失败: {str(e)}")
    
    def get_tool_metadata(self) -> Dict[str, Any]:
        """
        获取工具元数据
        
        Returns:
            工具元数据字典
        """
        return {
            "tool_name": self.tool_name,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "api_version": getattr(self, "api_version", "unknown"),
            "supported_entities": getattr(self, "supported_entities", []),
            "description": getattr(self, "description", ""),
            "last_updated": datetime.now().isoformat()
        }
    
    def format_task_record(self, entity: str, question: str, answer: str, 
                          api_response: Any, endpoint: str, **metadata) -> Dict[str, Any]:
        """
        格式化任务记录的通用方法
        
        Args:
            entity: 输入实体
            question: 生成的问题
            answer: 答案
            api_response: API响应
            endpoint: API端点
            **metadata: 其他元数据
            
        Returns:
            格式化的任务记录
        """
        # 截取响应数据用于展示
        if isinstance(api_response, dict):
            excerpt = json.dumps(api_response)[:1000]
        else:
            excerpt = str(api_response)[:1000]
        
        return {
            "tool": self.tool_name,
            "i_T": entity,
            "Q": question,
            "a": answer,
            "C_excerpt": excerpt,
            "meta": {
                "endpoint": endpoint,
                "source": f"{self.tool_name.upper()} API",
                "tool_version": getattr(self, "api_version", "unknown"),
                "generation_timestamp": datetime.now().isoformat(),
                **metadata
            }
        }
    
    def validate_entity(self, entity: str) -> bool:
        """
        验证输入实体的基本格式
        
        Args:
            entity: 待验证的实体
            
        Returns:
            是否为有效实体
        """
        if not entity or not isinstance(entity, str):
            return False
        
        entity = entity.strip()
        if len(entity) == 0:
            return False
            
        # 可以在子类中重写以添加特定验证逻辑
        return True
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(tool_name='{self.tool_name}', base_url='{self.base_url}')"


class ToolRegistry:
    """工具注册表，管理所有可用的工具"""
    
    _tools: Dict[str, BaseTool] = {}
    
    @classmethod
    def register_tool(cls, tool: BaseTool):
        """注册工具"""
        cls._tools[tool.tool_name] = tool
        
    @classmethod
    def get_tool(cls, tool_name: str) -> Optional[BaseTool]:
        """获取工具实例"""
        return cls._tools.get(tool_name)
    
    @classmethod
    def list_tools(cls) -> List[str]:
        """列出所有注册的工具名称"""
        return list(cls._tools.keys())
    
    @classmethod
    def get_all_tools(cls) -> Dict[str, BaseTool]:
        """获取所有工具实例"""
        return cls._tools.copy()