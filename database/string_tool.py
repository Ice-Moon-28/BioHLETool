"""
STRING工具实现（带文件缓存；TTL 可设为永远）
STRING蛋白质相互作用网络数据库查询工具
支持蛋白质、基因相互作用信息查询
"""

from dataclasses import asdict
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from urllib.parse import quote, urlencode

from base.config import DIR_PROTEIN_NETWORK
from base.entity import ProteinInteraction, ProteinNetworkRecord
from util.edit_distance import is_similar_edit
from util.file import dump_json, read_json, safe_filename

from .base_tool import BaseTool


class StringTool(BaseTool):
    """STRING蛋白质相互作用数据库查询工具（支持文件缓存）"""
    
    def __init__(
        self,
        cache_dir: Optional[str] = None,
        cache_ttl_sec: Optional[int] = 24 * 3600
    ):
        """
        初始化STRING工具

        Args:
            cache_dir: 缓存目录（默认 network_cache/string）
            cache_ttl_sec: 缓存有效期（秒）；None 表示永不过期
        """
        super().__init__(
            tool_name="string",
            base_url="https://string-db.org/api",
            timeout=30
        )
        self.api_version = "v11.5"
        self.supported_entities = ["protein", "gene", "compound"]
        self.description = "STRING蛋白质相互作用网络数据库查询工具（带文件缓存）"
        
        # 请求头
        self.request_session.headers.update({
            'Accept': 'text/plain',  # STRING API返回TSV格式（/tsv/*）；/json/* 仍会返回 JSON
            'User-Agent': 'BioGen-STRING-Tool/1.1'
        })

        # 缓存设置（与 GTExTool/UniProtTool 风格一致）
        self.cache_ttl_sec = cache_ttl_sec
        default_cache = Path("network_cache") / "string"
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
        例如：TP53_protein_9606.json
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
                print("Read Protein Network From Cache", key)
                return cached

        data = self.make_api_request(endpoint)
        if data is not None:
            self._write_cache(key, data)
        return data

    # =========================
    # 任务流程
    # =========================
    def generate_atomic_task(
        self,
        entity: str,
        query_type: str = "protein",
        species: str = "9606",
        *,
        force_refresh: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成原子任务
        
        Args:
            entity: 查询实体（蛋白质名、基因名等）
            query_type: 查询类型 ("protein", "gene", "network")
            species: 物种NCBI分类ID，默认为人类(9606)
            force_refresh: 是否跳过缓存强制刷新
            **kwargs: 其他参数（预留）
        """
        try:
            question = self._build_question(entity, query_type)

            # 端点
            endpoint = self.get_api_endpoint(entity, query_type=query_type, species=species)

            # 请求（带缓存）
            response_data = self._fetch_with_cache(
                endpoint,
                entity=entity,
                query_type=query_type,
                species=species,
                force_refresh=force_refresh
            )

            return response_data
            
        except Exception as e:
            return {
                "tool": self.tool_name,
                "i_T": entity,
                "Q": question if 'question' in locals() else f"查询{entity}的STRING信息",
                "a": None,
                "C_excerpt": f"错误: {str(e)}",
                "meta": {"error": str(e), "query_type": query_type, "species": species, "force_refresh": force_refresh}
            }
    
    def validate_task(
        self,
        task_record: Dict[str, Any],
        *,
        force_refresh: bool = False
    ) -> bool:
        """
        验证任务有效性（A通道验证）
        
        Args:
            task_record: 任务记录
            force_refresh: 是否跳过缓存强制刷新
        """
        try:
            entity = task_record.get("i_T")
            meta = task_record.get("meta", {}) or {}
            query_type = meta.get("query_type", "protein")
            species = meta.get("species", "9606")
            endpoint = meta.get("endpoint")

            if not endpoint and entity:
                endpoint = self.get_api_endpoint(entity, query_type=query_type, species=species)
            if not endpoint:
                return False

            # 再次请求（可选择跳过缓存）
            response_data = self._fetch_with_cache(
                endpoint,
                entity=entity,
                query_type=query_type,
                species=species,
                force_refresh=force_refresh
            )

            predicted_answer = self.parse_api_response(response_data, entity, query_type)
            expected_answer = task_record.get("a")
            return self._compare_answers(predicted_answer, expected_answer)
        except Exception as e:
            print(f"STRING验证失败: {e}")
            return False
    
    # =========================
    # Endpoint 构造
    # =========================
    def get_api_endpoint(self, entity: str, query_type: str = "protein", species: Optional[str] = None) -> str:
        """
        获取API端点URL - 使用STRING API
        """
        identifiers = entity

        if query_type in ("protein", "gene", "resolve", "get_string_ids"):
            endpoint = f"{self.base_url}/tsv/get_string_ids"
            params = {"identifiers": identifiers}
            if species:
                params["species"] = species

        elif query_type == "network":
            endpoint = f"{self.base_url}/json/network"
            params = {"identifiers": identifiers, "required_score": 400}
            if species:
                params["species"] = species

        elif query_type == "enrichment":
            endpoint = f"{self.base_url}/tsv/enrichment"
            params = {
                "identifiers": identifiers,
                "caller_identity": "BioGen-STRING-Tool/1.1",
            }
            if species:
                params["species"] = species

        else:
            endpoint = f"{self.base_url}/tsv/get_string_ids"
            params = {"identifiers": identifiers}
            if species:
                params["species"] = species

        return f"{endpoint}?{urlencode(params)}"
    
    # === 实现 get_enrichment：返回结构化 list[dict]，并带简单的TSV解析 ===
    def get_enrichment(
        self,
        identifiers: List[str],
        species: Optional[str] = None,
        *,
        categories: Optional[List[str]] = None,
        caller_identity: Optional[str] = "BioGen-STRING-Tool/1.1",
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        调用 STRING 富集分析 /api/tsv/enrichment ，返回结构化的 list[dict]。
        - identifiers: 蛋白/基因（建议先做 get_string_ids 映射，但非必需）
        - species: 物种 NCBI TaxonId（None 表示不限定物种）
        - categories: 可选，按类别过滤（如 ["Process","Pathway","Component","Function","Pubmed"]）
        - caller_identity: 请求标识（官方建议提供）
        - force_refresh: 是否跳过本地缓存

        返回记录常见字段（不同类别字段略有差异）：
        category, term, description, number_of_genes, p_value, fdr, inputGenes, etc.
        """
        if not identifiers:
            return []

        # 关键：用回车连接，交给 urlencode 统一编码
        id_str = "\r".join([str(x).strip() for x in identifiers if str(x).strip()])

        # 组装查询参数（species=None 时不带 species）
        params = {
            "identifiers": id_str,
            "caller_identity": caller_identity or "BioGen-STRING-Tool/1.1",
        }
        if species:
            params["species"] = str(species)

        endpoint = f"{self.base_url}/tsv/enrichment?{urlencode(params)}"

        # 使用工具自带缓存；species 为空时，用 "all" 作为缓存键的 species 片段
        data_tsv = self._fetch_with_cache(
            endpoint,
            entity="__ENRICHMENT__" + self._sanitize_filename(id_str[:120]),
            query_type="enrichment",
            species=species or "all",
            force_refresh=force_refresh,
        )

        if not isinstance(data_tsv, str) or not data_tsv.strip():
            return []

        lines = [ln for ln in data_tsv.splitlines() if ln.strip()]
        if not lines:
            return []

        header = lines[0].split("\t")
        records: List[Dict[str, Any]] = []

        # 常见需要转为 float/int 的字段名（大小写不敏感）
        float_fields = {"p_value", "pvalue", "fdr", "false_discovery_rate", "strength"}
        int_fields = {"number_of_genes", "n_genes", "input_number", "bg_number"}

        def _norm_key(k: str) -> str:
            return k.strip()

        def _cast_value(k: str, v: str) -> Any:
            lk = k.lower()
            if lk in float_fields:
                try:
                    return float(v)
                except Exception:
                    return v
            if lk in int_fields:
                try:
                    return int(v)
                except Exception:
                    return v
            return v

        for ln in lines[1:]:
            cols = ln.split("\t")
            row: Dict[str, Any] = {}
            for i, col_name in enumerate(header):
                val = cols[i] if i < len(cols) else ""
                key = _norm_key(col_name)
                row[key] = _cast_value(key, val)
            records.append(row)

        # 类别过滤（可选；不区分大小写）
        if categories:
            cats_lower = {c.lower() for c in categories}
            def _get_cat(r: Dict[str, Any]) -> str:
                # 兼容不同标题大小写
                return str(r.get("category") or r.get("Category") or "").lower()
            records = [r for r in records if _get_cat(r) in cats_lower]

        return records
    # =========================
    # 响应解析
    # =========================
    def parse_api_response(self, response_data: Any, entity: str, query_type: str) -> Optional[str]:
        """
        解析API响应获取答案 - STRING API格式（支持TSV和JSON）
        """
        try:
            if query_type == "network":
                # network 接口返回 JSON（可能是 list[edge]）
                if isinstance(response_data, list) and response_data:
                    first_result = response_data[0]
                    if isinstance(first_result, dict):
                        if "stringId_A" in first_result:
                            return first_result["stringId_A"]
                        if "preferredName_A" in first_result:
                            return first_result["preferredName_A"]
                if isinstance(response_data, dict):
                    # 兜底：如果是单个 dict
                    return response_data.get("species", None)
                return None
            else:
                # resolve 接口通常返回 TSV 字符串
                if isinstance(response_data, str):
                    return self._parse_tsv_response(response_data, entity)
                elif isinstance(response_data, list) and response_data:
                    first_result = response_data[0]
                    if isinstance(first_result, dict):
                        if "stringId" in first_result:
                            return first_result["stringId"]
                        if "preferredName" in first_result:
                            return first_result["preferredName"]
                elif isinstance(response_data, dict):
                    if "stringId" in response_data:
                        return response_data["stringId"]
                    if "preferredName" in response_data:
                        return response_data["preferredName"]
                return None
        except Exception as e:
            print(f"STRING响应解析失败: {e}")
            return None
    
    def _parse_tsv_response(self, tsv_text: str, entity: str) -> Optional[str]:
        """
        解析TSV格式的响应
        """
        try:
            lines = tsv_text.strip().split('\n')
            if len(lines) < 2:
                return None
            
            header = lines[0].split('\t')
            string_id_idx = -1
            preferred_name_idx = -1
            
            for i, col_name in enumerate(header):
                if col_name == "stringId":
                    string_id_idx = i
                elif col_name == "preferredName":
                    preferred_name_idx = i
            
            for line in lines[1:]:
                if not line.strip():
                    continue
                columns = line.split('\t')
                min_required_cols = max(string_id_idx, preferred_name_idx) + 1
                if len(columns) < min_required_cols:
                    continue
                if string_id_idx >= 0 and len(columns) > string_id_idx and columns[string_id_idx]:
                    return columns[string_id_idx]
                if preferred_name_idx >= 0 and len(columns) > preferred_name_idx and columns[preferred_name_idx]:
                    return columns[preferred_name_idx]
            return None
        except Exception as e:
            print(f"TSV解析失败: {e}")
            return None
    
    def _compare_answers(self, predicted: Optional[str], expected: Optional[str]) -> bool:
        """
        比较预测答案和期望答案
        """
        if not predicted or not expected:
            return False
        return str(predicted).strip() == str(expected).strip()

    # =========================
    # 便捷方法（与 GTExTool/UniProtTool 对齐）
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

    # =========================
    # 批量任务
    # =========================
    def generate_batch_tasks(self, entities: List[str], query_type: str = "protein", 
                             species: str = "9606", max_batch_size: int = 5,
                             *, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        批量生成任务（支持 force_refresh）
        """
        tasks = []
        for i in range(0, len(entities), max_batch_size):
            batch = entities[i:i + max_batch_size]
            for e in batch:
                task = self.generate_atomic_task(e, query_type=query_type, species=species, force_refresh=force_refresh)
                if task.get("a"):
                    tasks.append(task)
        return tasks

    # =========================
    # 其他
    # =========================
    def _build_question(self, entity: str, query_type: str) -> str:
        if query_type == "protein":
            return f"蛋白质 {entity} 在STRING数据库中的主要相互作用伙伴ID是什么？"
        if query_type == "gene":
            return f"基因 {entity} 编码的蛋白质在STRING数据库中的标识ID是什么？"
        if query_type == "network":
            return f"{entity} 在STRING数据库中的蛋白质网络ID是什么？"
        return f"{entity} 在STRING数据库中对应的蛋白质ID是什么？"


def create_string_tool(**kwargs) -> StringTool:
    """
    创建STRING工具实例
    例如：create_string_tool(cache_ttl_sec=None)  # 缓存永不过期
    """
    return StringTool(**kwargs)

stringTool = create_string_tool(cache_ttl_sec=None)  # 永不过期示例

def fetch_protein_network(query: str,
                          use_cache: bool = True,
                          species: str = None,
                          force_refresh: bool = False,
                          min_score: float = 0.0,
                          **kwargs) -> ProteinNetworkRecord:
    """
    从 STRING 查询蛋白互作网络并标准化为 ProteinNetworkRecord
    """
    q_norm = safe_filename(query.lower())
    fname = DIR_PROTEIN_NETWORK / f"{q_norm}_network.json"
    fname.parent.mkdir(parents=True, exist_ok=True)

    # 读缓存
    if use_cache and fname.exists() and not force_refresh:
        data = read_json(fname)
        interactions = [ ProteinInteraction(**i) for i in data.get("interactions", [])]
        protein_network = ProteinNetworkRecord(**data)
        protein_network.interactions = interactions
        return protein_network

    # 工具调用
    raw = stringTool.generate_atomic_task(
        query, query_type="network", species=species, force_refresh=force_refresh, **kwargs
    )

    edges_raw = raw.get("data") if isinstance(raw, dict) else raw

    if not edges_raw:
        return ProteinNetworkRecord(seed_protein=query, taxon_id=species,
                                    interactions=[], neighbors=[], raw=raw)

    interactions: List[ProteinInteraction] = []
    neighbors: set[str] = set()

    for e in edges_raw:
        try:
            score_val = float(e.get("score", 0.0))
            if score_val < min_score:
                continue

            a_name = e.get("preferredName_A", "")
            b_name = e.get("preferredName_B", "")

            if not(is_similar_edit(
                a_name.lower(), 
                query.lower(),
            ) or is_similar_edit(
                b_name.lower(),
                query.lower(),
            )):
                continue

            enricement = stringTool.get_enrichment(
                [a_name, b_name],
                species=species,
                force_refresh=False
            )
            inter = ProteinInteraction(
                string_id_a=e.get("stringId_A", ""),
                string_id_b=e.get("stringId_B", ""),
                preferred_name_a=e.get("preferredName_A", ""),
                preferred_name_b=e.get("preferredName_B", ""),
                taxon_id=str(e.get("ncbiTaxonId", species)),
                score=score_val,
                nscore=float(e.get("nscore", 0.0)),
                fscore=float(e.get("fscore", 0.0)),
                pscore=float(e.get("pscore", 0.0)),
                ascore=float(e.get("ascore", 0.0)),
                escore=float(e.get("escore", 0.0)),
                dscore=float(e.get("dscore", 0.0)),
                tscore=float(e.get("tscore", 0.0)),
                enrichment=enricement,
            )

            a_name = e.get("preferredName_A", "")
            b_name = e.get("preferredName_B", "")
            int_fname = DIR_PROTEIN_NETWORK / f"{a_name}_{b_name}_interaction.json"

            int_fname.parent.mkdir(parents=True, exist_ok=True)

            dump_json(asdict(inter), int_fname)

            interactions.append(inter)
            neighbors.add(inter.preferred_name_a)
            neighbors.add(inter.preferred_name_b)
        except Exception:
            continue

    record = ProteinNetworkRecord(
        seed_protein=query,
        taxon_id=species,
        interactions=interactions,
        neighbors=sorted(neighbors - {query}),
        raw=raw,
    )

    dump_json(asdict(record), fname)
    return record


# ========== 测试函数 ==========
def test_fetch_protein_network():
    rec = fetch_protein_network("TP53", species="9606", force_refresh=True, min_score=0.6)
    print(f"Seed protein: {rec.seed_protein}")
    print(f"Taxon: {rec.taxon_id}")
    print(f"Neighbors (top 10): {rec.neighbors[:10]}")
    print(f"Total interactions: {len(rec.interactions)}")
    for inter in rec.interactions[:5]:
        print(" -", inter.preferred_name_a, "<->", inter.preferred_name_b, "| score:", inter.score)


def test_get_enrichment():
    """
    测试 STRING 富集分析（/api/tsv/enrichment）
    覆盖：跨物种、不指定类别、限定类别
    """
    tool = create_string_tool(cache_ttl_sec=None)  # 永不过期示例
    print("缓存目录：", tool.get_cache_path())

    # 典型 p53 相关集合
    ids = ["TP53", "MDM2"]

    # 1) 不指定物种（跨物种解析）
    rec_any = tool.get_enrichment(ids, species=None, force_refresh=True)

    # 2) 指定人类 9606
    rec_human = tool.get_enrichment(ids, species="9606", force_refresh=False)

    # 3) 只看 Process / Pathway（示例），并做按类别分桶展示
    rec_human_pp = tool.get_enrichment(ids,
                                       categories=["Process", "Pathway"],
                                       force_refresh=False)

    return rec_any


def test_string_tool():
    """测试STRING工具功能"""
    tool = create_string_tool(cache_ttl_sec=None)  # 永不过期示例
    print("缓存目录：", tool.get_cache_path())
    
    # 测试蛋白质查询（写缓存）
    print("测试蛋白质查询...")
    protein_task = tool.generate_atomic_task("TP53", query_type="protein", species="9606", force_refresh=True)
    print(f"蛋白质任务: {protein_task}")
    
    # 再次查询（命中缓存）
    print("\n再次查询（命中缓存）...")
    protein_task_cached = tool.generate_atomic_task("TP53", query_type="network", species="9606", force_refresh=False)
    print(f"蛋白质任务（缓存）: {protein_task_cached}")
    
    # 测试基因查询
    print("\n测试基因查询...")
    gene_task = tool.generate_atomic_task("BRCA1", query_type="gene", species="9606", force_refresh=True)
    print(f"基因任务: {gene_task}")


if __name__ == "__main__":
    test_string_tool()
    test_fetch_protein_network()
    print(
        test_get_enrichment()
    )