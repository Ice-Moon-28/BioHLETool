import json
from openai import OpenAI
from typing import List, Dict, Any, Tuple, Optional

# 初始化 client
client = OpenAI(
    api_key="sk-Tf5jzgx5F8gj4acn36Z5FiyRJRJPZzryvCaIywCSwmBahB8y", 
    base_url="http://35.220.164.252:3888/v1/",
)

def call_openai_chat(messages, model="gpt-4o-mini", stream=False, **kwargs):
    """
    调用 OpenAI 格式的 Chat Completions API

    Args:
        messages (list[dict]): [{"role": "system"/"user"/"assistant", "content": "xxx"}]
        model (str): 模型名称
        stream (bool): 是否流式
        **kwargs: 其他传给 API 的参数 (temperature, top_p, max_tokens ...)

    Returns:
        str: 模型的完整回复
    """
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=stream,
        **kwargs
    )

    if not stream:
        return completion.choices[0].message.content.strip()
    else:
        collected = []
        for chunk in completion:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                collected.append(chunk.choices[0].delta.content)
        return ''.join(collected).strip()


def chat_with_tools(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    model: str = "gpt-4o-mini"
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    用 OpenAI SDK 调用聊天模型，支持多个工具调用。
    
    参数:
        messages: 对话历史 [{"role": "user", "content": "xxx"}]
        tools: 工具定义（OpenAI function calling 格式），默认为 None
        model: 使用的模型名称，默认为 gpt-4o-mini
    
    返回:
        response_text: 模型文本回复
        tool_calls: 工具调用列表，每个元素是 {"name": str, "arguments": str}
    """
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice="auto" if tools else None
    )

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
    return response_text, tool_calls


if __name__ == "__main__":
    messages = [
        {"role": "system", "content": "你是一个 helpful 助手。"},
        {"role": "user", "content": "帮我总结一下 Transformer 的核心思想。"}
    ]

    resp = call_openai_chat(messages, model="gpt-4o-mini", stream=False)
    print(resp)

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

    response_text, tool_calls = chat_with_tools(messages, tools)

    print("模型回复:", response_text)
    print("工具调用:")
    for call in tool_calls:
        print(call)

