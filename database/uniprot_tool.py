# """
# Proteins（UniProt/EBI）工具实现（简化版）
# 支持蛋白质条目查询（protein/isoform）和特征注释查询（feature）
# """

# import json
# import os
# from typing import Dict, Any, Optional, Union
# from urllib.parse import urlencode, quote

# from .base_tool import BaseTool


# class UniProtTool(BaseTool):
#     """EBI Proteins REST API 查询工具（支持 protein 与 feature）"""

#     def __init__(self):
#         super().__init__(
#             tool_name="proteins_api",
#             base_url="https://www.ebi.ac.uk/proteins/api",
#             timeout=30
#         )
#         self.description = "基于 EBI Proteins REST API 的查询工具，只支持 protein/isoform 和 feature 类型"
#         self.supported_entities = ["protein", "isoform", "feature"]

#         self.request_session.headers.update({
#             "Accept": "application/json",
#             "User-Agent": "BioGen-ProteinsAPI-Tool/1.0"
#         })

#     # -------------------------
#     # 任务与校验
#     # -------------------------
#     def generate_atomic_task(
#         self,
#         entity: str,
#         query_type: str = "protein",
#         speics: str = "Homo sapiens",
#         **kwargs
#     ) -> Dict[str, Any]:
#         """生成查询任务并执行一次 API 调用"""
#         question = self._build_question(entity, query_type)
#         try:
#             endpoint = self.get_api_endpoint(entity, query_type=query_type, **kwargs)
#             response_data = self.make_api_request(endpoint)

#             import pdb; pdb.set_trace()

#             # 保存到文件
#             os.makedirs("outputs", exist_ok=True)   # 建立 outputs 文件夹，避免文件乱放
#             file_path = os.path.join("outputs", f"a_sresponse.json")

#             with open(file_path, "w", encoding="utf-8") as f:
#                 json.dump(response_data, f, ensure_ascii=False, indent=2)
#             answer = self.parse_api_response(response_data, query_type=query_type, entity=entity)

#             return self.format_task_record(
#                 entity=entity,
#                 question=question,
#                 answer=answer,
#                 api_response=response_data,
#                 endpoint=endpoint,
#                 query_type=query_type,
#                 **kwargs
#             )
#         except Exception as e:
#             return {
#                 "tool": self.tool_name,
#                 "i_T": entity,
#                 "Q": question,
#                 "a": None,
#                 "C_excerpt": f"错误: {str(e)}",
#                 "meta": {"error": str(e), "query_type": query_type, **kwargs}
#             }

#     def validate_task(self, task_record: Dict[str, Any]) -> bool:
#         """重跑验证"""
#         try:
#             entity = task_record.get("i_T")
#             meta = task_record.get("meta", {})
#             query_type = meta.get("query_type", "protein")
#             endpoint = meta.get("endpoint") or self.get_api_endpoint(entity, query_type=query_type, **meta)

#             response_data = self.make_api_request(endpoint)
#             predicted_answer = self.parse_api_response(response_data, query_type=query_type, entity=entity)
#             expected_answer = task_record.get("a")
#             return self._compare_answers(predicted_answer, expected_answer)
#         except Exception as e:
#             print(f"ProteinsAPI 验证失败: {e}")
#             return False

#     # -------------------------
#     # Endpoint 构造
#     # -------------------------
#     def get_api_endpoint(self, entity: str, query_type: str = "protein", **kwargs) -> str:
#         """只支持 /proteins 和 /features 端点"""
#         offset = kwargs.get("offset")
#         size = kwargs.get("size")
#         fields = kwargs.get("fields")
#         types = kwargs.get("types")  # features types，如 "DOMAIN,VARIANT"

#         def _qs(params: Dict[str, Any]) -> str:
#             clean = {k: v for k, v in params.items() if v}
#             return f"?{urlencode(clean, doseq=True)}" if clean else ""

#         if query_type in ("protein", "isoform"):
#             params = {
#                 "accession": entity if self._looks_like_accession(entity) else None,
#                 "gene": entity if not self._looks_like_accession(entity) else None,
#                 "offset": offset,
#                 "size": size,
#                 "fields": fields
#             }
#             return f"{self.base_url}/proteins" + _qs(params)

#         if query_type == "feature":
#             acc = entity if self._looks_like_accession(entity) else kwargs.get("accession")
#             if not acc:
#                 raise ValueError("features 查询需要 accession")
#             path = f"features/{quote(acc)}"
#             return f"{self.base_url}/{path}" + _qs({"types": types, "offset": offset, "size": size, "fields": fields})

#         raise ValueError(f"不支持的 query_type: {query_type}")

#     # -------------------------
#     # 响应解析
#     # -------------------------
#     def parse_api_response(self, response_data: Any, query_type: str, entity: str) -> Optional[Union[str, Dict[str, Any]]]:
#         """解析 API 响应，提取关键信息"""
#         if isinstance(response_data, str):
#             try:
#                 response_data = json.loads(response_data)
#             except Exception:
#                 return response_data[:200]

#         if query_type in ("protein", "isoform"):
#             rec = response_data[0] if isinstance(response_data, list) and response_data else response_data
#             if not rec:
#                 return None
#             return {
#                 "accession": rec.get("accession"),
#                 "protein": (rec.get("protein") or {}).get("recommendedName", {}).get("fullName", {}).get("value")
#                             if isinstance(rec.get("protein"), dict) else None,
#                 "organism": (rec.get("organism") or {}).get("scientificName")
#             }

#         if query_type == "feature":
#             features = response_data if isinstance(response_data, list) else []
#             if not features:
#                 return None
#             f = features[0]
#             return {
#                 "type": f.get("type"),
#                 "desc": f.get("description"),
#                 "begin": f.get("begin"),
#                 "end": f.get("end")
#             }

#         return None

#     # -------------------------
#     # 工具方法
#     # -------------------------
#     def _build_question(self, entity: str, query_type: str) -> str:
#         if query_type in ("protein", "isoform"):
#             return f"检索 {entity} 的蛋白条目（及同工型）。"
#         if query_type == "feature":
#             return f"列出 {entity} 的主要序列特征（结构域/位点等）。"
#         return f"查询 {entity} 的 Proteins API 信息。"

#     def _looks_like_accession(self, s: str) -> bool:
#         """朴素判断 UniProtKB accession"""
#         s = s.strip()
#         if len(s) in (6, 10) and s[0].isalnum():
#             return True
#         if "-" in s and len(s.split("-")[0]) in (6, 10):  # isoform
#             return True
#         return False

#     def _compare_answers(self, predicted, expected) -> bool:
#         if predicted is None or expected is None:
#             return False
#         if isinstance(predicted, dict) and isinstance(expected, dict):
#             keys = set(predicted.keys()).intersection(expected.keys())
#             return all(predicted[k] == expected[k] for k in keys)
#         return str(predicted).strip() == str(expected).strip()
    

# def create_proteins_api_tool() -> UniProtTool:
#     return UniProtTool()


# # 测试
# def test_proteins_api_tool():
#     tool = create_proteins_api_tool()

#     print("测试基因名 TP53（protein 查询）...")
#     t1 = tool.generate_atomic_task("p53", query_type="protein")
#     print("结果:", t1.get("a"))

#     # print("测试 accession P04637（feature 查询）...")
#     # t2 = tool.generate_atomic_task("P04637", query_type="feature", types="DOMAIN,VARIANT", size=5)
#     # print("结果:", t2.get("a"))


# if __name__ == "__main__":
#     test_proteins_api_tool()


"""
Proteins（UniProt/EBI）工具实现（带文件缓存；TTL 可设为永远）
支持蛋白质条目查询（protein/isoform）和特征注释查询（feature）
缓存文件名基于 entity/query_type/species，与 GTExTool 风格保持一致
"""

from dataclasses import asdict
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from urllib.parse import urlencode, quote

from base.config import DIR_PROTEIN
from base.entity import ProteinRecord
from util.edit_distance import is_similar_edit
from util.file import dump_json, read_json, safe_filename

from .base_tool import BaseTool


class UniProtTool(BaseTool):
    """EBI Proteins REST API 查询工具（支持 protein/isoform 和 feature），内置文件缓存（文件名基于 entity/query_type/species）"""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        cache_ttl_sec: Optional[int] = 24 * 3600
    ):
        """
        Args:
            cache_dir: 缓存目录（默认 network_cache/proteins）
            cache_ttl_sec: 缓存有效期（秒）；None 表示永不过期
        """
        super().__init__(
            tool_name="proteins_api",
            base_url="https://www.ebi.ac.uk/proteins/api",
            timeout=30
        )
        self.description = "基于 EBI Proteins REST API 的查询工具，只支持 protein/isoform 和 feature 类型（带文件缓存）"
        self.supported_entities = ["protein", "isoform", "feature"]

        # 请求头
        self.request_session.headers.update({
            "Accept": "application/json",
            "User-Agent": "BioGen-ProteinsAPI-Tool/1.1"
        })

        # 缓存设置（与 GTExTool 风格一致）
        self.cache_ttl_sec = cache_ttl_sec
        default_cache = Path("network_cache") / "uniprot"
        self.cache_dir = Path(cache_dir) if cache_dir else default_cache
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # =========================
    # 缓存辅助
    # =========================
    def _sanitize_filename(self, name: str) -> str:
        return re.sub(r'[^a-zA-Z0-9._-]', '_', name)

    def _cache_key(self, entity: str, query_type: str, species: str) -> str:
        """
        用 entity + query_type + species 生成缓存键（直接作为文件名）
        例如：TP53_protein_human.json
        """
        if species is not None:
            key = f"{entity}_{query_type}_{species}"
        else:
            key = f"{entity}_{query_type}"
        return self._sanitize_filename(key)

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, key: str) -> Optional[Any]:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            if self.cache_ttl_sec is None:
                return payload.get("data")
            ts = payload.get("_cached_at", 0)
            if (time.time() - ts) <= self.cache_ttl_sec:
                return payload.get("data")
            return None
        except Exception:
            return None

    def _write_cache(self, key: str, data: Any) -> None:
        path = self._cache_path(key)
        tmp_path = path.with_suffix(".json.tmp")
        payload = {"_cached_at": time.time(), "data": data}
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)  # 原子替换
        except Exception:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    def _fetch_with_cache(
        self,
        endpoint: str,
        *,
        entity: str,
        query_type: str,
        species: str,
        force_refresh: bool = False
    ) -> Any:
        """
        带缓存请求：
        - 缓存文件名基于 entity/query_type/species
        - 非 force_refresh：先查缓存，命中则直接返回
        - 未命中或强制刷新：请求接口并写入缓存
        """
        key = self._cache_key(entity, query_type, species)
        if not force_refresh:
            cached = self._read_cache(key)
            if cached is not None:
                print("Read Protein From Cache", key)
                return cached

        data = self.make_api_request(endpoint)
        if data is not None:
            self._write_cache(key, data)
        return data

    def generate_atomic_task(
        self,
        entity: str,
        query_type: str = "protein",
        species = None,
        *,
        force_refresh: bool = False,
        save_raw: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成查询任务；支持 force_refresh 跳过缓存
        species 仅用于生成缓存键（Proteins API 本身按 accession/gene 查询，与物种无强绑定）
        """
        try:
            endpoint = self.get_api_endpoint(entity, query_type=query_type, **kwargs)
            response_data = self._fetch_with_cache(
                endpoint,
                entity=entity,
                query_type=query_type,
                species=species,
                force_refresh=force_refresh
            )

            if response_data is None:
                raise Exception("API 请求失败")

            if species:
                filter_response_data = []

                for data in response_data:
                    for organism in data['organism']["names"]:
                        if is_similar_edit(organism['value'].lower(), species.lower(), 2):
                            print(
                                species,
                                organism['value'].lower()
                            )
                            filter_response_data.append(data)
                            break

                return filter_response_data
            else:
                return response_data
        except Exception as e:
            return None

    def validate_task(
        self,
        task_record: Dict[str, Any],
        *,
        force_refresh: bool = False
    ) -> bool:
        """重跑验证（可选择跳过缓存）"""
        try:
            entity = task_record.get("i_T")
            meta = task_record.get("meta", {}) or {}
            query_type = meta.get("query_type", "protein")
            species = meta.get("species", "human")
            endpoint = meta.get("endpoint") or self.get_api_endpoint(entity, query_type=query_type, **meta)

            response_data = self._fetch_with_cache(
                endpoint,
                entity=entity,
                query_type=query_type,
                species=species,
                force_refresh=force_refresh
            )
            predicted_answer = self.parse_api_response(response_data, query_type=query_type, entity=entity)
            expected_answer = task_record.get("a")
            return self._compare_answers(predicted_answer, expected_answer)
        except Exception as e:
            print(f"ProteinsAPI 验证失败: {e}")
            return False

    # =========================
    # Endpoint 构造
    # =========================
    def get_api_endpoint(self, entity: str, query_type: str = "protein", **kwargs) -> str:
        """只支持 /proteins 和 /features 端点"""
        offset = kwargs.get("offset")
        size = kwargs.get("size")
        fields = kwargs.get("fields")
        types = kwargs.get("types")  # feature types，如 "DOMAIN,VARIANT"
        accession = kwargs.get("accession", None)

        def _qs(params: Dict[str, Any]) -> str:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            return f"?{urlencode(clean, doseq=True)}" if clean else ""

        if query_type in ("protein", "isoform"):
            params = {
                "accession": accession,
                "gene": entity if not self._looks_like_accession(entity) else None,
                "offset": offset,
                "size": size,
                "fields": fields
            }
            return f"{self.base_url}/proteins" + _qs(params)

        if query_type == "feature":
            
            if not accession:
                raise ValueError("features 查询需要 accession（如 P04637 或 P04637-2）")
            path = f"features/{quote(accession)}"
            return f"{self.base_url}/{path}" + _qs({
                "types": types,
                "offset": offset,
                "size": size,
                "fields": fields
            })

        raise ValueError(f"不支持的 query_type: {query_type}")

    # =========================
    # 响应解析
    # =========================
    def parse_api_response(self, response_data: Any, query_type: str, entity: str) -> Optional[Union[str, Dict[str, Any]]]:
        """解析 API 响应，提取关键信息"""
        if isinstance(response_data, str):
            try:
                response_data = json.loads(response_data)
            except Exception:
                return response_data[:200]

        if query_type in ("protein", "isoform"):
            rec = response_data[0] if isinstance(response_data, list) and response_data else response_data
            if not rec:
                return None
            protein_name = None
            if isinstance(rec.get("protein"), dict):
                rn = rec["protein"].get("recommendedName") or {}
                full = rn.get("fullName") or {}
                protein_name = full.get("value")
            return {
                "accession": rec.get("accession"),
                "protein": protein_name,
                "organism": (rec.get("organism") or {}).get("scientificName")
            }

        if query_type == "feature":
            features = response_data if isinstance(response_data, list) else []
            if not features:
                return None
            f = features[0]
            return {
                "type": f.get("type"),
                "desc": f.get("description"),
                "begin": f.get("begin"),
                "end": f.get("end")
            }

        return None

    # =========================
    # 工具方法
    # =========================
    def _build_question(self, entity: str, query_type: str) -> str:
        if query_type in ("protein", "isoform"):
            return f"检索 {entity} 的蛋白条目（及同工型）。"
        if query_type == "feature":
            return f"列出 {entity} 的主要序列特征（结构域/位点等）。"
        return f"查询 {entity} 的 Proteins API 信息。"

    def _looks_like_accession(self, s: str) -> bool:
        """朴素判断 UniProtKB accession/isoform"""
        s = s.strip()
        if not s:
            return False
        head = s.split("-")[0]  # 兼容 isoform
        return (len(head) in (6, 10)) and head[0].isalnum()

    def _compare_answers(self, predicted, expected) -> bool:
        if predicted is None or expected is None:
            return False
        if isinstance(predicted, dict) and isinstance(expected, dict):
            keys = set(predicted.keys()).intersection(expected.keys())
            return all(predicted.get(k) == expected.get(k) for k in keys)
        return str(predicted).strip() == str(expected).strip()

    # =========================
    # 便捷方法（与 GTExTool 对齐）
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
        """返回缓存目录路径"""
        return str(self.cache_dir.resolve())


def create_uniprot_tool(**kwargs) -> UniProtTool:
    """
    创建 Proteins 工具实例（支持传入 cache_dir, cache_ttl_sec）
    例如：create_proteins_api_tool(cache_ttl_sec=None)  # 缓存永不过期
    """
    return UniProtTool(**kwargs)

UniProtTool = create_uniprot_tool(cache_ttl_sec=None)  # 永不过期示例

def _unwrap_uniprot_payload(raw: Any) -> List[Dict[str, Any]]:
    """
    统一把各种返回格式解包成 list[dict]
    支持：
      - {"_cached_at": ..., "data": [ {...}, ... ]}
      - {"_cached_at": ..., "data": {...}}
      - [ {...}, ... ]
      - {...}
    """
    if isinstance(raw, dict) and "data" in raw:
        data = raw["data"]
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw]
    return []

def _extract_protein_name(rec: Dict[str, Any]) -> Optional[str]:
    """
    优先 submittedName -> fullName.value；否则尝试 recommendedName.fullName.value
    """
    prot = rec.get("protein") or {}
    sub = prot.get("submittedName")
    if isinstance(sub, list) and sub:
        full = ((sub[0] or {}).get("fullName") or {}).get("value")
        if full:
            return full
    recm = prot.get("recommendedName")
    if isinstance(recm, dict):
        full = (recm.get("fullName") or {}).get("value")
        if full:
            return full
    return None

def _extract_gene_names(rec: Dict[str, Any]) -> List[str]:
    out = []
    for g in rec.get("gene") or []:
        if isinstance(g, dict):
            v = (g.get("name") or {}).get("value")
            if v:
                out.append(v)
    return out

def _extract_org_names(rec: Dict[str, Any]) -> (Optional[int], Optional[str], Optional[str], List[str]):
    org = rec.get("organism") or {}
    taxonomy_id = org.get("taxonomy")
    sci = None
    com = None
    for n in org.get("names") or []:
        if n.get("type") == "scientific" and not sci:
            sci = n.get("value")
        elif n.get("type") == "common" and not com:
            com = n.get("value")
    lineage = org.get("lineage") or []
    return taxonomy_id, sci, com, lineage

def fetch_protein(query: str,
                  use_cache: bool = True,
                  species: str = None,
                  force_refresh: bool = False,
                  **args) -> ProteinRecord:
    """
    从 UniProt/EBI Proteins API 获取蛋白条目，标准化为 ProteinRecord 并写入缓存文件。
    - query: 基因名或 accession（如 'TP53' 或 'P04637'）
    - species: 仅用于缓存键；具体物种过滤 UniProtTool 内已做（is_similar_edit）
    """
    q_norm = safe_filename(query.lower())
    fname = DIR_PROTEIN / f"{q_norm}.json"
    fname.parent.mkdir(parents=True, exist_ok=True)

    # 1) 获取原始数据（优先用文件；否则调工具）
    if use_cache and fname.exists() and not force_refresh:
        stored = ProteinRecord(**read_json(fname))
        
        # 若文件里已是标准化结构，直接返回对应的 dataclass 兼容字典（上层使用通常无差别）
        return stored
    else:
        raw = UniProtTool.generate_atomic_task(query, species=species, force_refresh=force_refresh, **args)

    records = _unwrap_uniprot_payload(raw)
    rec0: Dict[str, Any] = records[0] if records else {}

    if len(records) == 0:
        return None

    # 3) 字段抽取
    taxonomy_id, organism_scientific, organism_common, lineage = _extract_org_names(rec0)
    print(taxonomy_id, organism_scientific, organism_common, lineage)
    protein_name = _extract_protein_name(rec0)
    print('=== protein_name ===', protein_name)
    gene_names = _extract_gene_names(rec0)

    # 4) 构建标准化记录
    rec = ProteinRecord(
        accession=rec0.get("accession"),
        entry_id=rec0.get("id") or rec0.get("uniProtkbId"),
        protein_existence=rec0.get("proteinExistence"),
        db_type=(rec0.get("info") or {}).get("type"),
        created=(rec0.get("info") or {}).get("created"),
        modified=(rec0.get("info") or {}).get("modified"),
        version=(rec0.get("info") or {}).get("version"),
        taxonomy_id=taxonomy_id,
        organism_scientific=organism_scientific,
        organism_common=organism_common,           # 单值字符串（如需要列表可改为收集列表）
        lineage=lineage,
        protein_name=protein_name,
        gene_names=gene_names,
        comments=rec0.get("comments") or [],
        features=rec0.get("features") or [],
        keywords=[kw.get("value") for kw in (rec0.get("keywords") or []) if isinstance(kw, dict) and kw.get("value")],
        db_references=rec0.get("dbReferences") or [],
        references=rec0.get("references") or [],
        seq_version=(rec0.get("sequence") or {}).get("version"),
        seq_length=(rec0.get("sequence") or {}).get("length"),
        seq_mass=(rec0.get("sequence") or {}).get("mass"),
        seq_modified=(rec0.get("sequence") or {}).get("modified"),
        sequence=(rec0.get("sequence") or {}).get("sequence"),
        raw=raw,  # 保留完整原始结构（包含 _cached_at/data）
    )

    q_norm = safe_filename(protein_name.lower())
    fname = DIR_PROTEIN / f"{q_norm}.json"
    fname.parent.mkdir(parents=True, exist_ok=True)

    # 5) 写盘（标准化后的 dataclass -> dict）
    dump_json(asdict(rec), fname)
    return rec

# ====== 简单测试 ======
def test_fetch_protein():
    print("=== 测试 UniProt fetch_protein ===")
    rec = fetch_protein("TP53", use_cache=False, species="homo_sapiens", force_refresh=True)
    print(f"acc={rec.accession}, entry={rec.entry_id}, name={rec.protein_name}, genes={rec.gene_names[:3]}")

# =========================
# 简单测试
# =========================
def test_proteins_api_tool():
    tool = create_uniprot_tool(cache_ttl_sec=None)  # 永不过期示例
    print("缓存目录：", tool.get_cache_path())

    print("测试基因名 p53（protein 查询，写缓存）...")
    t1 = tool.generate_atomic_task("p53", query_type="protein", species="homo_sapiens", force_refresh=True)

    print("再次查询（命中缓存）...")
    t2 = tool.generate_atomic_task("p53", query_type="protein", species="homo_sapiens", force_refresh=True)

    t3 = tool.generate_atomic_task("p53", query_type="feature", species="homo_sapiens",  accession="A0A0C4KX50", force_refresh=True,)
    # print("测试 accession P04637（feature 查询）...")
    # t3 = tool.generate_atomic_task("P04637", query_type="feature", types="DOMAIN,VARIANT", size=5, species="human")
    # print("结果:", t3.get("a"))


if __name__ == "__main__":
    # test_proteins_api_tool()
    test_fetch_protein()