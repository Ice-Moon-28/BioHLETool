import json
import time
import random
from openai import OpenAI
from typing import List, Dict, Any, Tuple, Optional

# 初始化 client
client = OpenAI(
    api_key="sk-Tf5jzgx5F8gj4acn36Z5FiyRJRJPZzryvCaIywCSwmBahB8y", 
    base_url="http://35.220.164.252:3888/v1/",
)
qwen_client = OpenAI(
            api_key='sk-b0ba29e85cac4cf9bfcb24d3a482cd17',
            base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
    )

def call_qwen_chat(messages, model='qwen2.5-72b-instruct', stream=False, max_retries=3, **kwargs):
    for attempt in range(max_retries + 1):
        try:
            completion = qwen_client.chat.completions.create(
                model=model,
                messages=messages,
                stream=stream,
                **kwargs
            )

            if not stream:
                content = completion.choices[0].message.content.strip()
                # 提取token使用信息
                usage = completion.usage
                token_info = {
                    "input_tokens": usage.prompt_tokens if usage else 0,
                    "output_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0
                }
                return content, token_info
            else:
                collected = []
                for chunk in completion:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        collected.append(chunk.choices[0].delta.content)
                content = ''.join(collected).strip()
                # 流式模式下可能没有usage信息，返回默认值
                token_info = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0
                }
                return content, token_info
                
        except Exception as e:
            error_msg = str(e)
            print(f"调用 OpenAI API 时出错 (尝试 {attempt + 1}/{max_retries + 1}): {error_msg}")
            
            # 如果是502错误或其他可重试的错误，等待后重试
            if attempt < max_retries and ("502" in error_msg or "InternalServerError" in error_msg or "timeout" in error_msg.lower()):
                wait_time = (2 ** attempt) + random.uniform(0, 1)  # 指数退避 + 随机延迟
                print(f"等待 {wait_time:.1f} 秒后重试...")
                time.sleep(wait_time)
                continue
            else:
                print(f"达到最大重试次数或不可重试的错误，放弃调用")
                return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

def call_openai_chat(messages, model="gpt-4o-mini", stream=False, max_retries=3, **kwargs):
    """
    调用 OpenAI 格式的 Chat Completions API，带重试机制

    Args:
        messages (list[dict]): [{"role": "system"/"user"/"assistant", "content": "xxx"}]
        model (str): 模型名称
        stream (bool): 是否流式
        max_retries (int): 最大重试次数
        **kwargs: 其他传给 API 的参数 (temperature, top_p, max_tokens ...)

    Returns:
        tuple: (模型回复内容, token使用信息)
        token使用信息格式: {"input_tokens": int, "output_tokens": int, "total_tokens": int}
    """
    for attempt in range(max_retries + 1):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=stream,
                **kwargs
            )

            if not stream:
                content = completion.choices[0].message.content.strip()
                # 提取token使用信息
                usage = completion.usage
                token_info = {
                    "input_tokens": usage.prompt_tokens if usage else 0,
                    "output_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0
                }
                return content, token_info
            else:
                collected = []
                for chunk in completion:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        collected.append(chunk.choices[0].delta.content)
                content = ''.join(collected).strip()
                # 流式模式下可能没有usage信息，返回默认值
                token_info = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0
                }
                return content, token_info
                
        except Exception as e:
            error_msg = str(e)
            print(f"调用 OpenAI API 时出错 (尝试 {attempt + 1}/{max_retries + 1}): {error_msg}")
            
            # 如果是502错误或其他可重试的错误，等待后重试
            if attempt < max_retries and ("502" in error_msg or "InternalServerError" in error_msg or "timeout" in error_msg.lower()):
                wait_time = (2 ** attempt) + random.uniform(0, 1)  # 指数退避 + 随机延迟
                print(f"等待 {wait_time:.1f} 秒后重试...")
                time.sleep(wait_time)
                continue
            else:
                print(f"达到最大重试次数或不可重试的错误，放弃调用")
                return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def chat_with_tools(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    model: str = "gpt-4o-mini",
    max_retries: int = 3
) -> Tuple[str, List[Dict[str, Any]], Dict[str, int]]:
    """
    用 OpenAI SDK 调用聊天模型，支持多个工具调用，带重试机制。
    
    参数:
        messages: 对话历史 [{"role": "user", "content": "xxx"}]
        tools: 工具定义（OpenAI function calling 格式），默认为 None
        model: 使用的模型名称，默认为 gpt-4o-mini
        max_retries: 最大重试次数
    
    返回:
        response_text: 模型文本回复
        tool_calls: 工具调用列表，每个元素是 {"name": str, "arguments": str}
        token_info: token使用信息 {"input_tokens": int, "output_tokens": int, "total_tokens": int}
    """
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto" if tools else None
            )
            break  # 成功则跳出重试循环
            
        except Exception as e:
            error_msg = str(e)
            print(f"调用 OpenAI API 时出错 (尝试 {attempt + 1}/{max_retries + 1}): {error_msg}")
            
            # 如果是502错误或其他可重试的错误，等待后重试
            if attempt < max_retries and ("502" in error_msg or "InternalServerError" in error_msg or "timeout" in error_msg.lower()):
                wait_time = (2 ** attempt) + random.uniform(0, 1)  # 指数退避 + 随机延迟
                print(f"等待 {wait_time:.1f} 秒后重试...")
                time.sleep(wait_time)
                continue
            else:
                print(f"达到最大重试次数或不可重试的错误，返回空结果")
                return "", [], {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    choice = response.choices[0].message

    # 普通文本回复
    response_text = choice.content if choice.content else ""

    # 工具调用（可能多个）
    tool_calls = []
    if choice.tool_calls:
        for tc in choice.tool_calls:
            try:
                args = json.loads(tc.function.arguments)  # 解析为 dict
            except Exception:
                args = tc.function.arguments  # 如果不是 JSON 字符串，就原样保留

            tool_calls.append({
                "name": tc.function.name,
                "arguments": args
            })
    
    # 提取token使用信息
    usage = response.usage
    token_info = {
        "input_tokens": usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0
    }
    
    return response_text, tool_calls, token_info


if __name__ == "__main__":
    messages = [
        {"role": "system", "content": "你是一个 helpful 助手。"},
        {"role": "user", "content": "帮我总结一下 Transformer 的核心思想。"}
    ]

    resp, token_info = call_openai_chat(messages, model="gpt-4o-mini", stream=False)
    print("回复:", resp)
    print("Token使用:", token_info)

    messages = [{"role": "user", "content": "帮我查一下北京和上海的天气"}]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "查询指定城市的天气",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "城市名称"}
                    },
                    "required": ["city"]
                }
            }
        }
    ]

    response_text, tool_calls, token_info = chat_with_tools(messages, tools)

    print("模型回复:", response_text)
    print("工具调用:")
    for call in tool_calls:
        print(call)
    print("Token使用:", token_info)

