import requests

def search_papers(keyword, limit=10):
    """
    在 Semantic Scholar 搜索论文，并按引用数排序
    返回 title, url, abstract
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": keyword,
        "limit": limit,
        "fields": "title,url,abstract,citationCount"
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    # 按 citationCount 从高到低排序
    papers = sorted(data.get("data", []), key=lambda x: x.get("citationCount", 0), reverse=True)

    results = []
    for p in papers:
        results.append({
            "title": p.get("title"),
            "url": p.get("url"),
            "abstract": p.get("abstract", None),
            "citations": p.get("citationCount", 0)
        })

    return results


if __name__ == "__main__":
    keyword = "B cell receptor"   # 你要搜索的关键词
    papers = search_papers(keyword, limit=20)

    for i, p in enumerate(papers, 1):
        print(f"{i}. {p['title']}")
        print(f"   URL: {p['url']}")
        print(f"   Citations: {p['citations']}")
        if p['abstract']:
            print(f"   Abstract: {p['abstract'][:200]}...")  # 只打印前200字符
        print()
