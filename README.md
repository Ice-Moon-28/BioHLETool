# BioHLETool

一个面向生物医药信息抽取与对接的小工具集合，封装了多类生物数据库与文献网页检索能力，包含基因/蛋白/通路/药物/变异等查询与结构化落盘，以及网页、PDF 与文献站点的实用抓取函数。项目以轻量工具形态提供，便于在脚本或 Notebook 中快速调用。


## 目录结构
- `database/`: 各数据库工具实现（GTEx/Ensembl、UniProt、STRING、Reactome、ChEMBL、ClinVar 等）
- `tools/`: 网页与文献检索/抽取工具（DOI 附件、arXiv、Scholar、PubMed、Google、HTML/PDF 提取）
- `base/`: 通用配置与数据结构（`config.py`、`entity.py`）
- `util/`: 文件与字符串小工具（`file.py`、`edit_distance.py` 等）
- `entity/`: 标准化实体输出目录（自动生成）
  - `gene/`: `GeneRecord` JSON
  - `protein/`: `ProteinRecord` JSON
  - `protein_network/`: `ProteinNetworkRecord` JSON
- `network_cache/`: 各工具的网络响应缓存（例如 `gtex/`、`uniprot/`、`string/`）
- `supplementary_info/`: DOI 附件抓取的文件示例

## 环境与安装
- Python 版本：建议 Python 3.10+（项目中使用了 `list[dict]` 等 PEP 585 语法）
- 安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 额外依赖（util/edit_distance 使用）：
pip install python-Levenshtein
```

requirements.txt 列表：`urllib3`, `PyPDF2`, `requests`, `arxiv`, `scholarly`, `beautifulsoup4`, `googlesearch-python`, `pymed`。

提示：
- `scholarly` 与 `googlesearch-python` 可能触发反爬/验证码；若受限请降低频率或配置代理。
- `pymed` 查询 PubMed 时需设置 email（代码中已示例，建议改成有效邮箱）。

## 快速开始
以下演示以 Python 交互或脚本方式直接调用。大多数工具包含 `if __name__ == "__main__"` 的演示用例，也可直接运行对应文件。

### 1) 基因信息（Ensembl/GTEx 风格）
```python
from database.gtex_tool import fetch_gene
rec = fetch_gene("TP53", use_cache=True, query_type="gene", force_refresh=False)
print(rec.gene_id, rec.display_name, rec.biotype)
# 输出同时落盘到 entity/gene/<symbol>.json
```

### 2) 蛋白信息（UniProt/EBI Proteins）
```python
from database.uniprot_tool import fetch_protein
rec = fetch_protein("TP53", use_cache=True, species="homo_sapiens", force_refresh=False)
print(rec.accession, rec.entry_id, rec.protein_name)
# 输出落盘到 entity/protein/<protein_name>.json
```

### 3) 蛋白互作网络与富集（STRING）
```python
from database.string_tool import fetch_protein_network
net = fetch_protein_network("TP53", species="9606", force_refresh=False, min_score=0.6)
print(net.seed_protein, len(net.interactions), net.neighbors[:10])
# 网络结果落盘到 entity/protein_network/
```

### 4) 通路稳定 ID（Reactome）
```python
from database.reactome_tool import create_reactome_tool
tool = create_reactome_tool()
rec = tool.generate_atomic_task("TP53", query_type="gene")
print(rec["a"], rec["meta"]["endpoint"])  # 解析到的稳定ID及访问端点
```

### 5) 药物/化合物/靶点（ChEMBL 代替 DrugBank）
```python
from database.drugbank_tool import create_drugbank_tool
tool = create_drugbank_tool()
chembl_id = tool.generate_atomic_task("Aspirin", query_type="drug")["a"]
print(chembl_id)
```

### 6) 变异与临床意义（ClinVar）
```python
from database.clinvar_tool import ClinVarTool
tool = ClinVarTool()
ans = tool.generate_atomic_task("BRCA1", query_type="gene")["a"]
print(ans)
```

### 7) 文献/网页工具（DOI 附件、arXiv、PubMed、Google、网页/PDF）
```python
from tools.web_tools import (
    fetch_supplementary_info_from_doi, query_arxiv, query_pubmed,
    search_google, extract_url_content, extract_pdf_content,
)
print(fetch_supplementary_info_from_doi("10.1038/s41586-020-2649-2"))
print(query_arxiv("large language models alignment", max_papers=2))
print(query_pubmed("CRISPR gene editing", max_papers=2))
print(search_google("best practices prompt engineering", num_results=2))
print(extract_url_content("https://huggingface.co/datasets/futurehouse/hle-gold-bio-chem"))
print(extract_pdf_content("https://arxiv.org/pdf/1706.03762.pdf"))
```

## 缓存与输出
- 文件缓存：GTEx/UniProt/STRING 工具均提供缓存；缓存键通常由 `entity/query_type/species` 组成，存放于 `network_cache/<tool>/`。
- 标准化落盘：高层封装 `fetch_gene`、`fetch_protein`、`fetch_protein_network` 会将结构化记录写至 `entity/` 目录便于复用与版本管理。
- 控制缓存：大部分工具支持 `force_refresh` 跳过缓存强制请求；`cache_ttl_sec=None` 表示缓存永不过期。

## 常见问题
- 依赖缺失：`util/edit_distance.py` 依赖 `python-Levenshtein`，需手动 `pip install python-Levenshtein`。
- 网络与速率限制：外网接口可能不稳定或限流；建议添加合理的 `User-Agent`、间隔访问并配置代理。
- Scholar/Google：可能触发验证码或屏蔽；如遇到，请减少频率或改用学术镜像/代理。
- PubMed 邮箱：`tools/web_tools.py` 中 `PubMed(tool=..., email=...)` 建议配置为有效邮箱。
- 平台差异：Windows 下路径分隔符不同，代码中已使用 `pathlib`/`os.path` 规避大部分问题。

## 开发与扩展
- 工具基类：`BaseTool` 统一了 `generate_atomic_task`、`validate_task`、`get_api_endpoint` 与 `parse_api_response` 等接口；也提供 `make_api_request`、`format_task_record` 与元数据获取等通用能力。
- 注册表：`ToolRegistry` 可集中管理工具实例（部分工具示例已展示直接创建与调用）。
- 新工具接入：
  1. 在 `database/` 新增 `<your_tool>_tool.py`，继承 `BaseTool`；
  2. 实现端点构造、响应解析、任务/验证逻辑；
  3. 视需要加入文件缓存与标准化落盘；
  4. 在 `requirements.txt` 补充依赖并在 README 添加用法。

## 免责声明
- 本项目仅用于科研/学习目的。外部数据库与服务的可用性、返回格式与授权策略可能变化，请以各自官方文档为准，并遵守使用条款与访问频控要求。
- 结果解析逻辑为示例范式，生产环境建议根据业务场景做更严格的匹配、错误处理与单元测试。

