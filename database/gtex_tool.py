"""
GTEx工具实现（带文件缓存；TTL 可设为永远）
基因表达谱数据查询工具
由于GTEx API访问限制，使用Ensembl表达数据API作为替代
"""

import json
import re
import os
from dataclasses import asdict 
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import quote
from base.config import DIR_GENE
from base.entity import GeneRecord
from util.edit_distance import is_similar_edit
import traceback
from util.file import dump_json, read_json, safe_filename

from .base_tool import BaseTool


class GTExTool(BaseTool):
    """GTEx风格的基因表达数据查询工具（内置文件缓存，文件名基于 entity/query_type/species）"""
    
    def __init__(self, cache_dir: Optional[str] = None, cache_ttl_sec: Optional[int] = None):
        """
        初始化GTEx工具
        使用Ensembl表达数据API作为主要数据源

        Args:
            cache_dir: 缓存目录（默认 network_cache/gtex）
            cache_ttl_sec: 缓存有效期（秒）；None 表示永不过期
        """
        super().__init__(
            tool_name="gtex",
            base_url="https://rest.ensembl.org",
            timeout=30
        )
        self.api_version = "v1"
        self.supported_entities = ["gene", "tissue", "expression"]
        self.description = "基因表达谱数据查询工具"

        # 缓存设置
        self.cache_ttl_sec = cache_ttl_sec  # None = 永不过期
        default_cache = Path("network_cache") / "gtex"
        self.cache_dir = Path(cache_dir) if cache_dir else default_cache
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Ensembl REST API 要求的请求头
        self.request_session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'BioGen-GTEx-Tool/1.0'
        })

    # =========================
    # 缓存相关的私有方法
    # =========================
    def _sanitize_filename(self, name: str) -> str:
        """清理字符串生成安全的文件名"""
        return re.sub(r'[^a-zA-Z0-9._-]', '_', name)

    def _cache_key(self, entity: str, query_type: str, species: str = '') -> str:
        """
        用 entity + query_type + species 生成缓存键（直接作为文件名）
        例如：TP53_gene_human.json
        """
        if species is not None:
            key = f"{entity}_{query_type}_{species}"
        else:
            key = f"{entity}_{query_type}"
        return self._sanitize_filename(key)

    def _cache_path(self, key: str) -> Path:
        """根据缓存键返回文件路径"""
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, key: str) -> Optional[Any]:
        """读取缓存；cache_ttl_sec=None 时表示永远有效"""
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            if self.cache_ttl_sec is None:
                # 永久缓存：存在就直接返回
                return payload.get("data")
            ts = payload.get("_cached_at", 0)
            if (time.time() - ts) <= self.cache_ttl_sec:
                return payload.get("data")
            else:
                # 过期当作未命中
                return None
        except Exception:
            # 文件损坏等，视为未命中
            return None

    def _write_cache(self, key: str, data: Any) -> None:
        """写入缓存到文件（原子替换）"""
        path = self._cache_path(key)
        tmp_path = path.with_suffix(".json.tmp")
        payload = {"_cached_at": time.time(), "data": data}
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=4)
            os.replace(tmp_path, path)
        except Exception:
            # 写失败不影响主流程；清理临时文件
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    def _fetch_with_cache(
        self,
        endpoint: str,
        entity: str,
        query_type: str,
        species: str = None,
        force_refresh: bool = False
    ) -> Any:
        """
        带缓存的请求：
        - 缓存文件名基于 entity/query_type/species
        - 非 force_refresh：先查缓存，命中则直接返回
        - 未命中或强制刷新：请求接口并写入缓存
        """
        key = self._cache_key(entity, query_type, species)
        if not force_refresh:
            cached = self._read_cache(key)
            if cached is not None:
                print("Read Gene From Cache", key)
                return cached

        # 真正发起网络请求
        data = self.make_api_request(endpoint)
        # 可按需限制缓存类型，这里只要 data 非 None 就写
        if data is not None:
            self._write_cache(key, data)
        return data

    def generate_atomic_task(
        self,
        entity: str,
        query_type: str = "expression",
        species: str = None,
        force_refresh: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成原子任务；支持 force_refresh 跳过缓存
        """
        try:
            # 构建查询问题（保留你的原始语气）
            if query_type == "expression":
                question = f"基因 {entity} 在GTEx数据库中的表达水平ID是什么？"
            elif query_type == "gene":
                question = f"基因 {entity} 在Ensembl数据库中的稳定ID是什么？"
            elif query_type == "tissue":
                question = f"组织 {entity} 中高表达基因的Ensembl ID是什么？"
            else:
                question = f"{entity} 在基因表达数据库中对应的ID是什么？"
            
            # API端点
            endpoint = self.get_api_endpoint(entity, query_type=query_type, species=species)
            
            # 带缓存请求（文件名由 entity/query_type/species 决定）
            response_data = self._fetch_with_cache(
                endpoint,
                entity,
                query_type,
                species,
                force_refresh=force_refresh
            )

            return response_data

            # return self.format_task_record(
            #     entity=entity,
            #     question=question,
            #     answer=answer,
            #     api_response=response_data,
            #     endpoint=endpoint,
            #     query_type=query_type,
            #     species=species
            # )
        except Exception as e:
            # 打印错误类型、信息和完整堆栈
            print("❌ generate_atomic_task 出错：", e)
            traceback.print_exc()
            return None

    def validate_task(self, task_record: Dict[str, Any], force_refresh: bool = False) -> bool:
        """
        验证任务有效性（A通道验证）；支持 force_refresh 控制是否绕过缓存
        """
        try:
            entity = task_record.get("i_T")
            meta = task_record.get("meta", {})
            endpoint = meta.get("endpoint")
            query_type = meta.get("query_type", "expression")
            species = meta.get("species", "human")
            
            if not endpoint and entity:
                endpoint = self.get_api_endpoint(entity, query_type=query_type, species=species)
            if not endpoint:
                return False
            
            # 带缓存请求（与生成任务时一致）
            response_data = self._fetch_with_cache(
                endpoint, entity, query_type, species, force_refresh=force_refresh
            )
            predicted_answer = self.parse_api_response(response_data, entity, query_type)
            expected_answer = task_record.get("a")
            return self._compare_answers(predicted_answer, expected_answer)
        except Exception as e:
            print(f"GTEx验证失败: {e}")
            return False

    def get_api_endpoint(self, entity: str, query_type: str = "expression", species: str = "human") -> str:
        """
        获取API端点URL - 使用Ensembl REST API
        """
        encoded_entity = quote(entity)
        base_url = self.base_url
        if species:
            species_map = {
                "human": "homo_sapiens",
                "mouse": "mus_musculus",
                "rat": "rattus_norvegicus"
            }
            ensembl_species = species_map.get(species.lower(), "homo_sapiens")
        else:
            ensembl_species = "homo_sapiens"
        
        # 目前三种查询都先用 lookup/symbol 获取稳定ID
        if query_type in {"gene", "expression", "tissue"}:
            endpoint = f"{base_url}/lookup/symbol/{ensembl_species}/{encoded_entity}"
        else:
            endpoint = f"{base_url}/lookup/symbol/{ensembl_species}/{encoded_entity}"
        return endpoint
    
    def parse_api_response(self, response_data: Any, entity: str, query_type: str) -> Optional[str]:
        """
        解析API响应获取答案 - Ensembl API格式
        """
        try:
            if isinstance(response_data, dict):
                # 对 gene / expression 优先返回 Ensembl 基因ID
                if query_type in ("gene", "expression"):
                    gene_id = response_data.get("id")
                    if gene_id and str(gene_id).startswith("ENSG"):
                        return gene_id
                    for field in ("stable_id", "gene_id", "ensembl_gene_id"):
                        stable_id = response_data.get(field)
                        if stable_id and str(stable_id).startswith("ENSG"):
                            return stable_id
                # 兜底返回展示名 / 描述中的 ID / 原始 id
                if "display_name" in response_data:
                    return response_data["display_name"]
                desc = response_data.get("description")
                if desc:
                    m = re.search(r'(ENSG\d+)', desc)
                    if m:
                        return m.group(1)
                if "id" in response_data:
                    return str(response_data["id"])
            elif isinstance(response_data, list) and response_data:
                # 列表则取第一个元素递归解析
                return self.parse_api_response(response_data[0], entity, query_type)
            return None
        except Exception as e:
            print(f"GTEx响应解析失败: {e}")
            return None
    
    def _compare_answers(self, predicted: Optional[str], expected: Optional[str]) -> bool:
        """
        比较预测答案和期望答案
        """
        if not predicted or not expected:
            return False
        return str(predicted).strip() == str(expected).strip()
    
    def generate_batch_tasks(
        self,
        entities: List[str],
        query_type: str = "expression", 
        species: str = "human",
        max_batch_size: int = 5,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        批量生成任务；批量亦复用缓存
        """
        tasks = []
        for i in range(0, len(entities), max_batch_size):
            batch = entities[i:i + max_batch_size]
            for entity in batch:
                try:
                    task = self.generate_atomic_task(
                        entity,
                        query_type=query_type,
                        species=species,
                        force_refresh=force_refresh
                    )
                    if task.get("a"):  # 只保留有答案的
                        tasks.append(task)
                except Exception as e:
                    print(f"批量生成任务失败 {entity}: {e}")
                    continue
        return tasks
    
    def get_supported_species(self) -> List[str]:
        """
        获取支持的物种列表
        """
        return ["human", "mouse", "rat"]
    
    def get_supported_query_types(self) -> List[str]:
        """
        获取支持的查询类型
        """
        return ["gene", "expression", "tissue"]
    
    def get_example_entities(self) -> Dict[str, List[str]]:
        """
        获取示例实体
        """
        return {
            "gene": ["TP53", "BRCA1", "EGFR", "MYC", "KRAS"],
            "expression": ["TP53", "BRCA1", "EGFR", "VEGFA", "TNF"],
            "tissue": ["Brain", "Heart", "Liver", "Kidney", "Lung"]
        }
    
    def get_expression_info(self, gene_id: str, species: str = "human", force_refresh: bool = False) -> Dict[str, Any]:
        """
        获取基因表达信息（扩展功能）；同样带缓存
        这里将 entity 取为 gene_id，query_type 固定为 'lookup_id'
        """
        try:
            endpoint = f"{self.base_url}/lookup/id/{gene_id}?expand=1"
            response = self._fetch_with_cache(
                endpoint, entity=gene_id, query_type="lookup_id", species=species, force_refresh=force_refresh
            )
            if isinstance(response, dict):
                return {
                    "gene_id": gene_id,
                    "symbol": response.get("display_name", ""),
                    "description": response.get("description", ""),
                    "biotype": response.get("biotype", ""),
                    "species": species,
                    "chromosome": response.get("seq_region_name", ""),
                    "start": response.get("start"),
                    "end": response.get("end"),
                    "strand": response.get("strand")
                }
            return {}
        except Exception as e:
            print(f"获取表达信息失败: {e}")
            return {}

    # =========================
    # 实用工具方法（可选）
    # =========================
    def clear_cache(self) -> None:
        """清空当前工具的缓存目录"""
        try:
            if self.cache_dir.exists():
                for p in self.cache_dir.glob("*.json"):
                    p.unlink(missing_ok=True)
        except Exception as e:
            print(f"清空缓存失败: {e}")

    def get_cache_path(self) -> str:
        """返回缓存目录路径（字符串）"""
        return str(self.cache_dir.resolve())
    
    def get_gene_expression(self, gene: str):
        response_data = self.generate_atomic_task(gene, query_type="gene")
        print(f"基因任务: {response_data}")

        print("\n测试表达信息获取...")
        if response_data.get("id"):
            expr_info = self.get_expression_info(response_data["id"])
            print(f"表达信息: {expr_info}")

            return



def create_gtex_tool(**kwargs) -> GTExTool:
    """
    创建GTEx工具实例（支持传入 cache_dir, cache_ttl_sec）
    例如：create_gtex_tool(cache_ttl_sec=None)  # 缓存永不过期
    """
    return GTExTool(**kwargs)

GtexTool = create_gtex_tool(cache_ttl_sec=None)  # 永不过期示例



def fetch_gene(gene_query: str, use_cache: bool = True, **args) -> GeneRecord:
    """
    基于新的 GeneRecord 定义，从缓存或工具函数获取基因信息并标准化。
    参数 gene_query 可为基因符号（如 'AKT1'）或 Ensembl ID（如 'ENSG00000142208'）。
    """

    gene_query = safe_filename(gene_query.lower().strip())

    fname = DIR_GENE / f"{gene_query}.json"

    if use_cache and fname.exists():
        data: Dict[str, Any] = GeneRecord(**read_json(fname))

        return data
    else:
        data: Dict[str, Any] = GtexTool.generate_atomic_task(
            gene_query,
            query_type="gene",
            **args,
        )

    
    # 映射到新的 GeneRecord
    rec = GeneRecord(
        gene_id=data.get("id"),
        display_name=data.get("display_name"),
        description=data.get("description"),
        source=data.get("source"),
        version=data.get("version"),
        start=data.get("start"),
        end=data.get("end"),
        strand=data.get("strand"),
        seq_region_name=data.get("seq_region_name"),
        biotype=data.get("biotype"),
        species=data.get("species"),
        assembly_name=data.get("assembly_name"),
        canonical_transcript=data.get("canonical_transcript"),
        logic_name=data.get("logic_name"),
        db_type=data.get("db_type"),
        object_type=data.get("object_type"),
        raw=data,  # 保留完整原始结构（含 _cached_at 与 data）
    )

    gene_query = safe_filename(data.get("display_name").lower().strip())

    fname = DIR_GENE / f"{gene_query}.json"

    # 确保文件写入时目录存在
    fname.parent.mkdir(parents=True, exist_ok=True)
    dump_json(asdict(rec), fname)

    return rec

# =========================
# 测试函数
# =========================
def test_gtex_tool():
    """测试GTEx工具功能"""
    # TTL=None 表示永不过期
    tool = create_gtex_tool(cache_ttl_sec=None)
    
    print("缓存目录：", tool.get_cache_path())

    # 测试基因查询
    print("测试基因查询...")
    gene_task = tool.generate_atomic_task("TP53", query_type="gene", force_refresh=True)
    print(f"基因任务: {gene_task}")

    # 测试表达查询
    print("\n测试表达查询...")
    expr_task = tool.generate_atomic_task("TP53", query_type="expression", force_refresh=True)
    print(f"表达任务: {expr_task}")

    # 测试验证
    print("\n测试验证...")
    if gene_task.get("a"):
        validation_result = tool.validate_task(gene_task)
        print(f"验证结果: {validation_result}")

    if gene_task.get("a"):
        print("\n已解析的 Ensembl Gene ID:", gene_task['a'])

    # 测试表达信息获取
    print("\n测试表达信息获取...")
    if gene_task.get("a"):
        expr_info = tool.get_expression_info(gene_task["a"])
        print(f"表达信息: {expr_info}")

    # 测试强制刷新（跳过缓存）
    print("\n测试强制刷新（force_refresh=True）...")
    _ = tool.generate_atomic_task("TP53", query_type="gene", force_refresh=True)
    print("强制刷新完成")

    fetch_gene("TP53", query_type="expression", use_cache=True)

    # 如需清空缓存，取消下面两行注释
    # tool.clear_cache()
    # print("缓存已清空")

def test_genes():
    test_genes = [
        "TP53",    # 抑癌基因，表达最常测试
        "BRCA1",   # 乳腺癌相关
        "BRCA2",   # 乳腺癌/卵巢癌相关
        "EGFR",    # 表皮生长因子受体
        "MYC",     # 癌基因
        "KRAS",    # 肿瘤驱动基因
        "MTOR",    # mTOR 信号通路
        "PTEN",    # 抑癌基因
        "AKT1",    # PI3K/AKT 通路
        "TNF",     # 炎症因子
        "IL6",     # 免疫相关
        "GAPDH",   # 常用内参基因
        "ACTB",    # β-actin，常用内参
        "HBB",     # 血红蛋白 β 链
        "INS"      # 胰岛素
    ]

    tool = create_gtex_tool(cache_ttl_sec=None)

    for gene in test_genes:
        tool.get_gene_expression(gene)


def test_fetch_gene():
    """
    基于新的 GeneRecord / GTExTool 流程的测试：
      - 首次禁用缓存强制请求并落盘
      - 第二次启用缓存验证读盘路径
      - 打印关键字段，便于肉眼检查
    """
    test_genes = ["TP53", "BRCA1", "AKT1", "EGFR"]

    print("=== 首次请求（force_refresh=True，写入缓存） ===")
    for g in test_genes:
        rec = fetch_gene(g, use_cache=False, query_type="gene", force_refresh=True)
        print(f"[{g}] id={rec.gene_id} symbol={rec.display_name} biotype={rec.biotype} chr={rec.seq_region_name} "
              f"pos={rec.start}-{rec.end} strand={rec.strand}")
    print("（以上已写入 DIR_GENE/<gene>.json）\n")

if __name__ == "__main__":
    # test_gtex_tool()
    # test_genes

    test_fetch_gene()