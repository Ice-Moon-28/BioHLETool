import Levenshtein

def is_similar_edit(s1: str, s2: str, max_dist: int = 2) -> bool:
    """
    判断两个字符串编辑距离是否在容忍范围内
    """
    return Levenshtein.distance(s1, s2) <= max_dist

if __name__ == "__main__":
    print(is_similar_edit("hello", "hallo"))

    print(is_similar_edit("hello", "hallo", 1))

    print(is_similar_edit("hello", "hallo", 2))

    print(is_similar_edit("Homo sapiens".lower(), "homo_sapiens".lower(), 1))