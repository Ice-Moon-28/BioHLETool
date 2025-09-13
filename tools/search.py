import asyncio
import atexit
import json
import logging
import os
import pickle
import threading
import time
from typing import Dict, Optional
from serpapi import GoogleSearch
def get_serper_api():
    return {
        "url": "https://serpapi.com/search",
        "key": 'e570e579d7d540533b1938968fb6efd4fcedb0152168516403c06664f1fd968a'
    }
def get_serper_dev_api():
    return {
        "key": 'acab77c138957b01c62f278d06e0b7e93f310344'
    }
params = {
    "engine": "google_scholar",    # 指定使用 Scholar
    "q": "reinforcement learning", # 搜索关键词
    "api_key": "e570e579d7d540533b1938968fb6efd4fcedb0152168516403c06664f1fd968a", # 你的 SerpApi Key
    "hl": "en"                     # 可选，语言
}
import httpx
from cachetools import TTLCache

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

SERPER_TIMEOUT = 60

class SerperAPIError(Exception):
    """自定义异常：Serper/SerpAPI 请求失败"""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")

# --- Cache Backend --- #

class CacheBackend:
    def get(self, key: str) -> Optional[str]:
        raise NotImplementedError

    def set(self, key: str, value: str, ttl: Optional[int] = None):
        raise NotImplementedError

class InMemoryCache(CacheBackend):
    def __init__(self, file_path: str):
        self._cache = TTLCache(maxsize=1000000, ttl=3600)
        self._lock = threading.Lock()
        self.file_path = file_path
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        # Open the file in append mode, creating it if it doesn't exist.
        self._file_handler = open(self.file_path, "ab")
        self._load_from_file()
        atexit.register(self._close_file)

    def _load_from_file(self):
        """Loads the cache from a pickle file."""
        try:
            with open(self.file_path, "rb") as f:
                i = 0
                while True:
                    try:
                        entry = pickle.load(f)
                        key, value = list(entry.items())[0]
                        self._cache[key] = value
                        i += 1
                    except EOFError:
                        break
                    except (IndexError) as e:
                        logger.warning(
                            f"Skipping malformed entry {i+1} in {self.file_path}: {e}"
                        )
            logger.info(
                f"Cache loaded from {self.file_path}, containing {len(self._cache)} items."
            )
        except FileNotFoundError:
            logger.info(
                f"Cache file {self.file_path} not found. A new one will be created."
            )
        except Exception as e:
            logger.warning(f"Could not load cache from {self.file_path}: {e}")

    def _close_file(self):
        """Closes the file handler on exit."""
        if self._file_handler:
            self._file_handler.close()
            logger.info("Cache file handler closed.")

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: str, ttl: Optional[int] = None):
        """Sets a value in the cache and appends it to the pickle file."""
        with self._lock:
            if key not in self._cache:
                self._cache[key] = value
                try:
                    pickle.dump({key: value}, self._file_handler)
                    self._file_handler.flush()  # Ensure it's written to disk
                except IOError as e:
                    logger.error(f"Could not write to cache file {self.file_path}: {e}")

class SerperProxyServer:
    def __init__(self, cache_backend: CacheBackend):
        self.cache = cache_backend
        # For hit rate logging
        self.total_requests = 0
        self.cache_hits = 0
        self._stats_lock = threading.Lock()

    def _generate_cache_key(self, query: str) -> str:
        normalized_query = query.strip()
        return f"serper:{normalized_query}"

    def _log_hit_rate(self, *, hit: bool):
        """Logs the cache hit rate."""
        with self._stats_lock:
            self.total_requests += 1
            if hit:
                self.cache_hits += 1

            hit_rate = (
                (self.cache_hits / self.total_requests) * 100
                if self.total_requests > 0
                else 0
            )
            status = "HIT" if hit else "MISS"
            logger.info(
                f"Cache {status}. Rate: {hit_rate:.2f}% ({self.cache_hits}/{self.total_requests})"
            )

    async def process_request(self, request_data: dict, headers: dict) -> dict:
        start_time = time.time()

        query = request_data.get("q", "")
        original_num = request_data.get("num", 10)
        
        cache_key = self._generate_cache_key(query)

        try:
            cached_result_str = self.cache.get(cache_key)
            if cached_result_str:
                cached_result = json.loads(cached_result_str)
                cached_count = len(cached_result.get("organic", []))
                
                if cached_count >= original_num:
                    self._log_hit_rate(hit=True)
                    if "organic" in cached_result:
                        cached_result["organic"] = cached_result["organic"][:original_num]
                    logger.info(
                        f"Request processed from cache in {time.time() - start_time:.2f} seconds."
                    )
                    return cached_result
                else:
                    logger.info(f"Cache has {cached_count} results, need {original_num}. Searching for more.")
                    api_request_data = request_data.copy()
                    api_request_data["num"] = 100
            else:
                api_request_data = request_data.copy()
                if original_num <= 10:
                    api_request_data["num"] = 10
                else:
                    api_request_data["num"] = 100

            self._log_hit_rate(hit=False)
            logger.info(f"Forwarding to Serper API for key: {cache_key}")

            selected_serper_dev = get_serper_dev_api()

            serper_key = selected_serper_dev['key']

            logger.info(f"Using SerpAPI: https://serpapi.com/search with key: {serper_key[:10]}...")

            api_request_data = {
                "q": query,
                "num": original_num,
                "autocorrect": False
            }

            api_headers = {
                "Content-Type": "application/json",
                "X-API-KEY": serper_key,
            }

            async with httpx.AsyncClient(limits=httpx.Limits(max_connections=100)) as client:
                response = await client.post(
                    "https://google.serper.dev/search",
                    json=api_request_data,
                    headers=api_headers,
                    timeout=SERPER_TIMEOUT
                )
                response.raise_for_status()
                full_result = response.json()

                # Cache the full result (with 10 or 100 items)
                self.cache.set(cache_key, json.dumps(full_result))

                # Trim the results for the current response
                result_to_return = full_result.copy()
                if "organic" in result_to_return:
                    result_to_return["organic_results"] = result_to_return["organic"][
                        :original_num
                    ]

                logger.info(
                    f"Request processed via SerpAPI in {time.time() - start_time:.2f} seconds."
                )

                return result_to_return

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling Serper API: {e.response.status_code} {e.response.text}"
            )
            raise SerperAPIError(status_code=e.response.status_code, detail=e.response.text)
        except Exception as e:
            logger.error(f"Unexpected error during Serper API request: {str(e)}")
            raise SerperAPIError(
                status_code=500, detail=f"An unexpected error occurred: {str(e)}"
            )

    def sync_process_request(self, request_data: dict, headers: dict) -> dict:
        return asyncio.run(self.process_request(request_data, headers))

CACHE_FILE = "server/cache/serper_dev_api_cache_v2.pkl"
cache_backend = InMemoryCache(file_path=CACHE_FILE)
#google_serper_dev_server = SerperProxyServer(cache_backend=cache_backend)
"""
def search_serper_dev(query: str, num_results: int = 10):
    result = google_serper_dev_server.sync_process_request(
        request_data={
            'q': query,
            'num': num_results,
            'timeout': 100,
        },
        headers={}
    )
   
    print(json.dumps(result, ensure_ascii=False, indent=2))

    return result['organic']
"""

def search_scholar_by_citations(query, api_key, num_results=20):
    """
    在 Google Scholar 上搜索论文，并按引用数排序。

    参数:
        query (str): 搜索关键词
        api_key (str): SerpApi Key
        num_results (int): 返回的论文数量上限

    返回:
        List[dict]: 每个元素是 {'title', 'authors', 'year', 'citations', 'url'}
    """
    all_results = []
    start = 0
    while len(all_results) < num_results:
        params = {
            "engine": "google_scholar",
            "q": query,
            "api_key": api_key,
            "hl": "en",
            "start": start,
            "num": min(20, num_results - len(all_results))  # 每页最多20条
        }

        search = GoogleSearch(params)
        data = search.get_dict()
        papers = data.get('organic_results', [])

        if not papers:
            break  # 没有更多结果

        for paper in papers:
            cited_by = paper.get('cited_by', {}).get('value', 0)
            authors = paper.get('publication_info', {}).get('authors', [])
            year = paper.get('publication_info', {}).get('summary', '')
            all_results.append({
                'title': paper.get('title', ''),
                'authors': authors,
                'year': year,
                'citations': cited_by,
                'url': paper.get('link', '')
            })

        start += len(papers)

    # 按引用数降序排序
    all_results.sort(key=lambda x: x['citations'], reverse=True)
    return all_results[:num_results]

if __name__ == "__main__":

    #result = search_serper_dev("Natural selection", num_results=10)
    result = search_scholar_by_citations(query="T cells", api_key='acab77c138957b01c62f278d06e0b7e93f310344')
    print(result)