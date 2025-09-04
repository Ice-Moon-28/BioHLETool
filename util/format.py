import json
from base.entity import ProteinRecord, ProteinInteraction, ProteinNetworkRecord, GeneRecord


def format_protein_info(protein: ProteinRecord) -> str:
    """
    格式化 UniProt 蛋白信息
    :param protein: ProteinRecord 对象
    :return: 格式化字符串
    """
    lines = []
    lines.append("🧬 蛋白信息")
    # lines.append(f"  - Accession: {protein.accession}")
    # lines.append(f"  - Entry ID: {protein.entry_id}")
    lines.append(f"  - 名称: {protein.protein_name}")
    # lines.append(f"  - 基因名: {', '.join(protein.gene_names) if protein.gene_names else 'N/A'}")
    # lines.append(f"  - 数据库类型: {protein.db_type} (Version {protein.version})")
    # lines.append(f"  - 蛋白存在证据: {protein.protein_existence}")
    # lines.append(f"  - 创建日期: {protein.created}, 更新日期: {protein.modified}")
    lines.append("")

    # 物种信息
    lines.append("📍 物种信息")
    lines.append(f"  - 学名: {protein.organism_scientific} (Taxonomy ID: {protein.taxonomy_id})")
    lines.append(f"  - 常用名: {protein.organism_common}")
    lines.append("")

    # 序列信息
    lines.append("🧾 序列信息")
    lines.append(f"  - 长度: {protein.seq_length} aa")
    lines.append(f"  - 分子量: {protein.seq_mass} Da")
    lines.append(f"  - 序列版本: {protein.seq_version} (修改时间: {protein.seq_modified})")
    seq = protein.sequence or ""
    lines.append(f"  - 序列片段: {seq}")
    lines.append("")

    return "\n".join(lines)

def format_gene_info(gene: GeneRecord) -> str:
    """
    格式化 Ensembl gene 信息为可读文本
    :param gene: GeneRecord 对象
    :return: 格式化字符串
    """
    lines = []
    lines.append("🧬 基因信息")
    lines.append(f"  - 基因名: {gene.display_name} ({gene.gene_id})")
    # lines.append(f"  - 描述: {gene.description}")
    # lines.append(f"  - 类型: {gene.biotype}")
    # lines.append(f"  - 来源: {gene.source} (v{gene.version})")
    lines.append("")

    # 基因组定位信息
    lines.append("📍 基因组位置")
    lines.append(f"  - 物种: {gene.species} (assembly: {gene.assembly_name})")
    lines.append(f"  - 染色体: {gene.seq_region_name}")
    lines.append(f"  - 起始位置: {gene.start}")
    lines.append(f"  - 结束位置: {gene.end}")
    strand_text = "正链 (+)" if gene.strand == 1 else "负链 (-)"
    lines.append(f"  - 链方向: {strand_text}")
    lines.append("")

    return "\n".join(lines)
def format_interaction(record: ProteinInteraction) -> str:
    lines = []
    lines.append("🔗 基因互作信息")
    lines.append(f"  - 基因A: {record.preferred_name_a} ({record.string_id_a})")
    lines.append(f"  - 基因B: {record.preferred_name_b} ({record.string_id_b})")
    lines.append(f"  - 物种: Taxon {record.taxon_id}")
    lines.append(f"  - 互作得分: {record.score:.3f}")
    lines.append("")

    if record.enrichment:
        lines.append("📊 特征分析结果:")
        for enr in record.enrichment:
            print(
                json.dumps(enr, ensure_ascii=False, indent=2)
            )
            lines.append(f"  - 类别: {enr['category']}")
            lines.append(f"  - 相互作用特征描述: {enr['description']}")
            # lines.append(f"    - Term: {enr.term}")
            # lines.append(f"    - 输入基因: {enr.inputGenes}")
            # lines.append(f"    - 背景基因数: {enr.number_of_genes_in_background}")
            # lines.append(f"    - P值: {enr.p_value} (FDR: {enr.fdr})")
            lines.append("")
    else:
        lines.append("📊 未检测到显著的富集结果")

    return "\n".join(lines)

