from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, Iterable, Callable

@dataclass
class GeneRecord:
    gene_id: str                      # 基因的 Ensembl ID，例如 "ENSG00000142208"
    display_name: Optional[str]       # 显示名/符号，例如 "AKT1"
    description: Optional[str]        # 描述，例如 "AKT serine/threonine kinase 1 ..."
    source: Optional[str]             # 来源，例如 "ensembl_havana"
    version: Optional[int]            # 版本号，例如 19
    start: Optional[int]              # 基因起始位置
    end: Optional[int]                # 基因终止位置
    strand: Optional[int]             # 链方向（1 或 -1）
    seq_region_name: Optional[str]    # 染色体号，例如 "14"
    biotype: Optional[str]            # 生物类型，例如 "protein_coding"
    species: Optional[str]            # 物种，例如 "homo_sapiens"
    assembly_name: Optional[str]      # 基因组版本，例如 "GRCh38"
    canonical_transcript: Optional[str]  # 代表性转录本，例如 "ENST00000649815.2"
    logic_name: Optional[str]         # 逻辑名，例如 "ensembl_havana_gene_homo_sapiens"
    db_type: Optional[str]            # 数据库类型，例如 "core"
    object_type: Optional[str]        # 对象类型，例如 "Gene"
    raw: Dict[str, Any]               # 原始完整返回数据

@dataclass
class ProteinRecord:
    accession: str                          # 主 accession，例如 "A0A034VR14"
    entry_id: Optional[str]                 # UniProt entry ID，例如 "A0A034VR14_BACDO"
    protein_existence: Optional[str]        # 存在性证据，例如 "Inferred from homology"

    # info 部分
    db_type: Optional[str]                  # 类型，例如 "TrEMBL"
    created: Optional[str]                  # 创建日期
    modified: Optional[str]                 # 修改日期
    version: Optional[int]                  # 版本号

    # 物种信息
    taxonomy_id: Optional[int]              # taxonomy ID，例如 27457
    organism_scientific: Optional[str]      # 学名，例如 "Bactrocera dorsalis"
    organism_common: Optional[str]          # 常用名，例如 "Oriental fruit fly"
    lineage: List[str]                      # 系统发育谱系

    # 蛋白名称
    protein_name: Optional[str]             # 全名，例如 "Cellular tumor antigen p53"
    gene_names: List[str]                   # 基因名，例如 ["P53"]

    # 功能注释
    comments: List[Dict[str, Any]]          # COFACTOR, SUBCELLULAR_LOCATION, SIMILARITY 等注释
    features: List[Dict[str, Any]]          # DOMAIN, REGION, BINDING, SITE 等特征
    keywords: List[str]                     # 关键词，例如 ["Activator", "Apoptosis", "Zinc"]

    # 交叉引用
    db_references: List[Dict[str, Any]]     # EMBL, RefSeq, AlphaFoldDB, GO, InterPro 等

    # 文献引用
    references: List[Dict[str, Any]]        # PubMed, DOI 等

    # 序列信息
    seq_version: Optional[int]
    seq_length: Optional[int]
    seq_mass: Optional[int]
    seq_modified: Optional[str]
    sequence: Optional[str]

    # 保留完整原始返回
    raw: Dict[str, Any]

@dataclass
class ProteinInteraction:
    string_id_a: str
    string_id_b: str
    preferred_name_a: str
    preferred_name_b: str
    taxon_id: str
    score: float         # 总分
    nscore: float        # neighborhood score
    fscore: float        # fusion score
    pscore: float        # phylogenetic profile score
    ascore: float        # co-expression score
    escore: float        # experimental score
    dscore: float        # database score
    tscore: float        # textmining score
    enrichment: List[Any]


@dataclass
class ProteinNetworkRecord:
    seed_protein: str                   # 起始蛋白，比如 "SIRT1"
    taxon_id: str                       # NCBI taxonomy ID，例如 "9606"
    interactions: List[ProteinInteraction]  # 全部边
    neighbors: List[str]                # 提取的邻居名字（preferredName_B 等）
    raw: Dict[str, Any]                 # 完整原始 JSON