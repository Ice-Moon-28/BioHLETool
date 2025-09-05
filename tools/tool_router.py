import json
from typing import Any, Dict

# Database/tool imports
from database.gtex_tool import fetch_gene
from database.uniprot_tool import fetch_protein
from database.string_tool import fetch_protein_network, create_string_tool
from database.reactome_tool import create_reactome_tool
from database.drugbank_tool import create_drugbank_tool
from database.clinvar_tool import ClinVarTool

from tools.web_tools import (
    fetch_supplementary_info_from_doi,
    query_arxiv,
    query_scholar,
    query_pubmed,
    search_google,
    extract_url_content,
    extract_pdf_content,
)


def _as_text(obj: Any, limit: int = 6000) -> str:
    try:
        s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        s = str(obj)
    if len(s) > limit:
        return s[:limit] + "\n... <truncated>"
    return s


def execute_tool(name: str, arguments: Dict[str, Any]) -> Any:
    """Map OpenAI tool-calls to project functions and return raw output (no _as_text)."""

    # ---------- Knowledge/web tools ----------
    if name == "fetch_supplementary_info_from_doi":
        return fetch_supplementary_info_from_doi(**arguments)
    if name == "query_arxiv":
        return query_arxiv(**arguments)
    if name == "query_scholar":
        return query_scholar(**arguments)
    if name == "query_pubmed":
        return query_pubmed(**arguments)
    if name == "search_google":
        return search_google(**arguments)
    if name == "extract_url_content":
        return extract_url_content(**arguments)
    if name == "extract_pdf_content":
        return extract_pdf_content(**arguments)

    # ---------- Biology DB wrappers ----------
    if name == "fetch_gene":
        rec = fetch_gene(**arguments)
        return rec.__dict__ if rec is not None else None

    if name == "fetch_protein":
        rec = fetch_protein(**arguments)
        return rec.__dict__ if rec is not None else None

    if name == "fetch_protein_network":
        net = fetch_protein_network(**arguments)
        if net is None:
            return None
        d = net.__dict__.copy()
        # interactions are dataclasses; convert
        d["interactions"] = [i.__dict__ for i in net.interactions]
        return d

    if name == "string_get_enrichment":
        tool = create_string_tool(cache_ttl_sec=None)
        return tool.get_enrichment(**arguments)

    if name == "reactome_query":
        tool = create_reactome_tool()
        return tool.generate_atomic_task(
            arguments.get("entity"),
            query_type=arguments.get("query_type", "gene"),
            species=arguments.get("species", "Homo sapiens"),
        )

    if name == "chembl_query":
        tool = create_drugbank_tool()
        return tool.generate_atomic_task(
            arguments.get("entity"),
            query_type=arguments.get("query_type", "drug"),
        )

    if name == "clinvar_query":
        tool = ClinVarTool()
        return tool.generate_atomic_task(
            arguments.get("entity"),
            query_type=arguments.get("query_type", "gene"),
            significance_filter=arguments.get("significance_filter"),
        )

    return {"error": f"Unknown tool: {name}", "arguments": arguments}