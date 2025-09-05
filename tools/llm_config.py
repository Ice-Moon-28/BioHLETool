"""
LLM 工具配置

将项目中可供 LLM function calling 使用的工具，按 OpenAI tools 规范定义：
[{"type": "function", "function": {"name", "description", "parameters"}}]

提示：这里只定义工具描述与参数模式（JSON Schema），具体的 Python 可调用函数名与绑定逻辑
由上层在收到 tool_calls 后自行路由到对应实现（如 database.* 或 tools.web_tools 中的函数）。
"""

from typing import List, Dict, Any


OPENAI_TOOLS: List[Dict[str, Any]] = [
    # =====================
    # 基因 / Ensembl (GTEx 风格)
    # =====================
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "fetch_gene",
    #         "description": "获取基因的 Ensembl 信息（GTEx 风格封装，带缓存与标准化落盘）",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "gene_query": {"type": "string", "description": "基因符号或 Ensembl 基因 ID，如 TP53 / ENSG..."},
    #                 "use_cache": {"type": "boolean", "description": "是否使用本地缓存", "default": True},
    #                 "force_refresh": {"type": "boolean", "description": "是否忽略缓存强制请求", "default": False},
    #                 "query_type": {"type": "string", "enum": ["gene", "expression", "tissue"], "description": "查询类型"},
    #                 "species": {"type": "string", "description": "物种（human/mouse/rat），默认 human", "default": "human"}
    #             },
    #             "required": ["gene_query"]
    #         }
    #     }
    # },

    # # =====================
    # # 蛋白 / UniProt (EBI Proteins)
    # # =====================
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "fetch_protein",
    #         "description": "获取蛋白条目（UniProt/EBI Proteins），带缓存与标准化落盘",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "query": {"type": "string", "description": "基因名或 accession，如 TP53 / P04637"},
    #                 "use_cache": {"type": "boolean", "description": "是否使用本地缓存", "default": True},
    #                 "species": {"type": "string", "description": "用于缓存键与物种过滤的标识，如 homo_sapiens，可为空"},
    #                 "force_refresh": {"type": "boolean", "description": "是否忽略缓存强制请求", "default": False}
    #             },
    #             "required": ["query"]
    #         }
    #     }
    # },

    # # =====================
    # # 蛋白互作网络 / STRING
    # # =====================
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "fetch_protein_network",
    #         "description": "从 STRING 获取蛋白互作网络（含富集分析与落盘）",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "query": {"type": "string", "description": "蛋白或基因名，如 TP53"},
    #                 "use_cache": {"type": "boolean", "description": "是否使用本地缓存", "default": True},
    #                 "species": {"type": "string", "description": "NCBI taxonomy ID，如 9606"},
    #                 "force_refresh": {"type": "boolean", "description": "是否忽略缓存强制请求", "default": False},
    #                 "min_score": {"type": "number", "description": "过滤交互边的最小 score（0-1）", "default": 0.0}
    #             },
    #             "required": ["query"]
    #         }
    #     }
    # },

    # # STRING 富集分析（TSV /api/tsv/enrichment）
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "string_get_enrichment",
    #         "description": "对给定蛋白/基因集合在 STRING 做富集分析，返回结构化结果",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "identifiers": {"type": "array", "items": {"type": "string"}, "description": "蛋白/基因名列表"},
    #                 "species": {"type": "string", "description": "NCBI taxonomy ID，可为空代表不限制"},
    #                 "categories": {"type": "array", "items": {"type": "string"}, "description": "过滤类别，如 Process/Pathway/Component/Function/Pubmed"},
    #                 "force_refresh": {"type": "boolean", "description": "是否忽略缓存强制请求", "default": False}
    #             },
    #             "required": ["identifiers"]
    #         }
    #     }
    # },

    # # =====================
    # # 通路 / Reactome
    # # =====================
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "reactome_query",
    #         "description": "在 Reactome 中检索基因/蛋白/通路等，返回稳定 ID 或最佳匹配",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "entity": {"type": "string", "description": "检索关键词，如 TP53 或 R-HSA-69488"},
    #                 "query_type": {"type": "string", "enum": ["gene", "pathway", "protein", "molecule"], "description": "查询类型"},
    #                 "species": {"type": "string", "description": "物种（学名），默认 Homo sapiens", "default": "Homo sapiens"}
    #             },
    #             "required": ["entity", "query_type"]
    #         }
    #     }
    # },

    # # =====================
    # # 药物/化合物 / ChEMBL（DrugBank 替代）
    # # =====================
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "chembl_query",
    #         "description": "使用 ChEMBL API 检索药物/化合物/靶点/适应症（DrugBank 替代）",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "entity": {"type": "string", "description": "检索词，如 Aspirin / EGFR"},
    #                 "query_type": {"type": "string", "enum": ["drug", "compound", "target", "indication"], "description": "查询类型"}
    #             },
    #             "required": ["entity", "query_type"]
    #         }
    #     }
    # },

    # # =====================
    # # 变异 / ClinVar（NCBI E-utilities）
    # # =====================
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "clinvar_query",
    #         "description": "查询基因或变异在 ClinVar 的记录，汇总临床意义与相关疾病",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "entity": {"type": "string", "description": "基因名/变异（HGVS/rsID）"},
    #                 "query_type": {"type": "string", "enum": ["gene", "variant", "hgvs", "rsid"], "description": "查询类型"},
    #                 "significance_filter": {"type": "string", "description": "按临床意义过滤，如 pathogenic/benign 等"}
    #             },
    #             "required": ["entity", "query_type"]
    #         }
    #     }
    # },

    # # =====================
    # # 文献 / 网页工具
    # # =====================
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "fetch_supplementary_info_from_doi",
    #         "description": "根据 DOI 抓取论文页面并尝试下载 Supplementary 文件，返回过程日志",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "doi": {"type": "string", "description": "论文 DOI"},
    #                 "output_dir": {"type": "string", "description": "输出目录（默认 supplementary_info）", "default": "supplementary_info"}
    #             },
    #             "required": ["doi"]
    #         }
    #     }
    # },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "query_arxiv",
    #         "description": "基于关键词检索 arXiv，返回若干篇论文的题目与摘要",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "query": {"type": "string", "description": "检索式"},
    #                 "max_papers": {"type": "integer", "description": "返回数量", "default": 10}
    #             },
    #             "required": ["query"]
    #         }
    #     }
    # },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "query_scholar",
    #         "description": "使用 scholarly 查询 Google Scholar，返回第一条结果的关键信息",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "query": {"type": "string", "description": "检索式"}
    #             },
    #             "required": ["query"]
    #         }
    #     }
    # },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "query_pubmed",
    #         "description": "检索 PubMed，必要时自动简化检索式重试，返回题录摘要",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "query": {"type": "string", "description": "检索式"},
    #                 "max_papers": {"type": "integer", "description": "最大返回数量", "default": 10},
    #                 "max_retries": {"type": "integer", "description": "简化检索重试次数", "default": 3}
    #             },
    #             "required": ["query"]
    #         }
    #     }
    # },
    {
        "type": "function",
        "function": {
            "name": "search_google",
            "description": "使用 googlesearch 获取若干条网页搜索结果（标题/URL/描述）",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索式"},
                    "num_results": {"type": "integer", "description": "返回条数", "default": 3},
                    "language": {"type": "string", "description": "语言代码，如 en/zh", "default": "en"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "extract_url_content",
            "description": "抓取网页并提取可读正文（移除脚本/导航等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "网页 URL"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "extract_pdf_content",
            "description": "下载并解析 PDF 文本（若为图片型 PDF 将提示需要 OCR）",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "PDF 或包含 PDF 链接的网页 URL"}
                },
                "required": ["url"]
            }
        }
    },
]

