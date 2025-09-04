
import json
import random
from base.entity import ProteinRecord, ProteinInteraction, ProteinNetworkRecord, GeneRecord


def format_protein_info(protein: ProteinRecord, k: int) -> str:
    """
    Format UniProt protein information (randomly select up to k attributes)
    :param protein: ProteinRecord object
    :param k: number of attributes to display (excluding section titles)
    :return: formatted string
    """
    # 准备候选条目（分组 + 行文本）
    candidates = []

    # Protein Information
    protein_items = [
        ("🧬 Protein Information", f"  - Name: {protein.protein_name}", protein.protein_name),
        # ("🧬 Protein Information", f"  - Accession: {protein.accession}"),
        # ("🧬 Protein Information", f"  - Entry ID: {protein.entry_id}"),
        # ("🧬 Protein Information", f"  - Gene Names: {', '.join(protein.gene_names) if protein.gene_names else 'N/A'}"),
        # ("🧬 Protein Information", f"  - Database Type: {protein.db_type} (Version {protein.version})"),
        # ("🧬 Protein Information", f"  - Protein Existence: {protein.protein_existence}"),
        # ("🧬 Protein Information", f"  - Created: {protein.created}, Last Modified: {protein.modified}"),
    ]
    # candidates.extend([(sec, line, answers) for sec, line, answers in protein_items ])

    # Organism Information
    org_items = [
        ("📍 Organism Information", f"  - Scientific Name: {protein.organism_scientific}", protein.organism_scientific),
        ("📍 Organism Information", f"  - Common Name: {protein.organism_common}", protein.organism_common),
    ]
    candidates.extend([(sec, line, answer) for sec, line, answer in org_items ])

    # Sequence Information
    seq = protein.sequence or ""
    seq_items = [
        ("🧾 Sequence Information", f"  - Length: {protein.seq_length} aa", protein.seq_length),
        ("🧾 Sequence Information", f"  - Molecular Weight: {protein.seq_mass} Da", protein.seq_mass),
        # ("🧾 Sequence Information", f"  - Sequence Version: {protein.seq_version} (Last Modified: {protein.seq_modified})"),
        ("🧾 Sequence Information", f"  - Sequence Fragment: {seq}", seq),
    ]
    candidates.extend([(sec, line, answer) for sec, line, answer in seq_items ])

    if not candidates:
        return "No data available."

    chosen = random.sample(candidates, min(k, len(candidates))) + protein_items

    # 渲染：仅输出包含被选条目的分组标题
    lines = []
    groups = {}
    for sec, line, _ in chosen:
        groups.setdefault(sec, []).append(line)
    for sec in ["🧬 Protein Information", "📍 Organism Information", "🧾 Sequence Information"]:
        if sec in groups:
            lines.append(sec)
            lines.extend(groups[sec])
            lines.append("")

    answers = [ans for _, _, ans in chosen if ans]

    return "\n".join(lines).rstrip() or "No data available.", answers



def format_gene_info(gene: GeneRecord, k: int) -> str:
    """
    Format Ensembl gene information into readable text (randomly select up to k attributes)
    :param gene: GeneRecord object
    :param k: number of attributes to display (excluding section titles)
    :return: formatted string
    """
    candidates = []

    # Gene Information
    gene_items = [
        ("🧬 Gene Information", f"  - Gene Name: {gene.display_name}", gene.display_name),
        # ("🧬 Gene Information", f"  - Description: {gene.description}"),
        # ("🧬 Gene Information", f"  - Biotype: {gene.biotype}"),
        # ("🧬 Gene Information", f"  - Source: {gene.source} (v{gene.version})"),
    ]
    

    # Genomic Location
    # strand_text = (
    #     "Forward Strand (+)" if getattr(gene, "strand", None) == 1
    #     else ("Reverse Strand (-)" if getattr(gene, "strand", None) == -1 else "")
    # )
    loc_items = [
        ("📍 Genomic Location", f"  - Species: {gene.species}", gene.species),
        ("📍 Genomic Location", f"  - Assembly Name: {gene.assembly_name}", gene.assembly_name),
        ("📍 Genomic Location", f"  - Chromosome: {gene.seq_region_name}", gene.seq_region_name),
        ("📍 Genomic Location", f"  - Start: {gene.start}" + f"  - End: {gene.end}", f"{gene.start} {gene.end}"),
        # ("📍 Genomic Location", f"  - Strand: {strand_text}"),
    ]
    candidates.extend([(sec, line, answer) for sec, line, answer in loc_items])

    if not candidates:
        return "No data available."

    chosen = random.sample(candidates, min(k, len(candidates))) + gene_items

    lines = []
    groups = {}
    print(chosen)
    for sec, line, _ in chosen:
        groups.setdefault(sec, []).append(line)
    for sec in ["🧬 Gene Information", "📍 Genomic Location"]:
        if sec in groups:
            lines.append(sec)
            lines.extend(groups[sec])
            lines.append("")

    return "\n".join(lines).rstrip() or "No data available."

def format_interaction(record: ProteinInteraction) -> str:
    """
    Format protein-protein interaction information.
    Always display basic interaction info, 
    and randomly select up to k enrichment attributes (if available).
    """
    lines = []

    # --- Always show base interaction info ---
    lines.append("🔗 Protein Interaction Information")
    lines.append(f"  - Gene A: {record.preferred_name_a} ({record.string_id_a})")
    lines.append(f"  - Gene B: {record.preferred_name_b} ({record.string_id_b})")
    lines.append(f"  - Species: Taxon {record.taxon_id}")
    if getattr(record, "score", None) is not None:
        lines.append(f"  - Interaction Score: {record.score:.3f}")
    lines.append("")

    # --- Enrichment: optional random selection ---
    enrich_lines = []
    if getattr(record, "enrichment", None):
        for enr in record.enrichment:
            try:
                cat = enr.get("category")
                desc = enr.get("description")
                if cat or desc:
                    enrich_lines.append(f"  - Category: {cat or 'N/A'}; Description: {desc or 'N/A'}")
            except Exception:
                enrich_lines.append(f"  - Raw: {json.dumps(enr, ensure_ascii=False)}")

    if enrich_lines:
        lines.append("📊 Enrichment Analysis Results:")
        lines.extend(enrich_lines)
        lines.append("")
    else:
        lines.append("📊 No significant enrichment results detected")

    return "\n".join(lines).rstrip()