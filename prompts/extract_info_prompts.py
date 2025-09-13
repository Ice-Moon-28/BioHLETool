EXTRACT_CONCEPTS ="""You are a biology expert who needs to extract upper-level concepts from the given supporting facts.
Subdomain: {subdomain}

Supporting Facts:
{supporting_facts}

Please analyze these supporting facts and extract 3-5 key upper-level concepts. Upper-level concepts should be broader, more abstract concepts that can encompass these specific facts.
An upper-level concept should be suitable as a research topic with sufficient generality.
For example:
- If the fact is "Traditional APCs (such as macrophages, dendritic cells) can take up antigens through phagocytosis and then present them to T cells on MHC II"
- The upper-level concept might be "Functional mechanisms of antigen-presenting cells (APCs)"

Please only return the list of upper-level concepts, one concept per line, without other explanations."""

EXTRACT_KEYWORDS = """You are a biologist who needs to extract keywords that can be searched on Wikipedia from the given statements. Return a list of keywords, one keyword per line, prioritizing the most relevant and general keywords.
Subdomain: {subdomain}
Related Statements:
{supporting_facts}
Example: Natural selection requires differences in fitness among phenotypes or genotypes; if all genotypes have equal fitness and the trait has no effect on fitness, then there is no selection on that phenotype.
Extraction Results:
Natural selection
Phenotype
Genotype
Please only return the keyword list, without other explanations."""



MERGE_FACTS = """
You are a biology expert who needs to merge and deduplicate the following list of biological facts.

Original Facts List:
{facts_text}

Please analyze these facts and perform the following operations:
1. Remove duplicate or highly similar facts
2. Merge related facts that can be combined
3. Retain the most valuable and accurate facts
4. Ensure each fact is an objective and accurate biological statement

Please return the merged results in JSON format as follows:
[
  {{
    "fact": "Merged factual statement"
  }},
  {{
    "fact": "Another merged fact"
  }},
  ...
]

Only return the JSON array, each object should only contain the "fact" field, do not include other content.
"""

FILTER_BIOLOGY_RELATED = """
You are a biology expert who needs to determine whether the following search results are related to biology.

Search Results:
{results_text}

Please analyze each search result and determine whether it is related to biology, biomedicine, life sciences, etc. Consider the following factors:
1. Whether the title and description contain biological concepts
2. Whether the content involves cells, molecules, genes, proteins, biological processes, etc.
3. Whether it is related to medicine, pharmacology, biotechnology, etc.
4. Whether it is related to organisms, ecosystems, evolution, etc.

Please return the results in JSON format as follows:
[
  {{
    "index": 1,
    "is_biology_related": true,
    "reason": "Contains cell biology and immunology related content"
  }},
  {{
    "index": 2,
    "is_biology_related": false,
    "reason": "Mainly computer technology related content"
  }},
  ...
]

Only return the JSON array, do not include other content.
"""

GENERATE_QUESTION_NEW_FACT = """You are a biology professor creating questions for college students.
You are a biology professor designing **advanced-level exam questions** for upper-level college students. 
Your task is to generate a new question with significantly higher difficulty than given question. 
Requirements:
1. Keep the same question type, but if the original question is single choice, you should make it multiple choice
2. Only use newly discovered facts as the basis for the question
3. Increase difficulty by:  
   - requiring multi-step reasoning or synthesis across multiple facts,  
   - adding plausible but incorrect distractors,  
   - incorporating less obvious relationships between concepts.
   - add some math calculation.
   - multiple choice question at least 7 options.
4. Provide a **clear, step-by-step solution approach** that explains how to derive the answer.

Please return in JSON format:
{{
    "question": "Question based on new facts",
    "answer": "Question answer",
    "rationale": "Solution approach and answer",
    "supporting_facts": ["Facts used"]
}}"""


SPECIFY_NEW_KEYWORDS = """
Please help me associate some biological concepts related to Amyloid (3-5, if you do not meet the following requirements, you can further reduce them). 
Each associated concept has a Wikipedia entry, and these concepts can be linked to each other to be used in the biology college final exam. 
Please only return the list of upper-level concepts, one concept per line, without other explanations.
"""