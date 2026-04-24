import json
import re
from typing import Any, List, Dict

from openai import APITimeoutError, OpenAI


AI_PARSE_TIMEOUT = 300
AI_VALIDATE_TIMEOUT = 30


def is_reasoning_model(model: str) -> bool:
    normalized = (model or "").strip().lower()
    keywords = ("reasoner", "reasoning", "thinking", "r1")
    return any(keyword in normalized for keyword in keywords)


def build_prompt(content: str, previous_result: str = "无") -> str:
    return f"""
上一章解析结果如下，只能作为人物名称、称呼和关系一致性的参考；不要复述上一章内容：
{previous_result}

请把当前章节解析成适合手机群聊阅读的对话流 JSON 数组。

解析规则：
1. 准确识别对话的说话者。若原文未明确指明，可结合上下文推断；若完全无法判断，人物字段根据当前场景判断填写，不能留空。
2. 旁白内容保持原文表述，无需改写或缩写。
3. 连续出现的多段旁白必须分段保留，避免单段过长，以语义自然为主。
4. 对话中的引号内容只保留说话文本，去除引号符号本身。
5. 仅返回纯 JSON 数组，不得包含解释、注释或 Markdown 代码块。
6. 有引号和冒号的地方重点判断是否为对话，不能漏掉！
7. 出现我，你，他，她这些词时根据当前场景和上下文自行推断人物字段。
输出示例：
[
  {{"character": "旁白", "text": "门被猛地推开，李雷喘着气冲了进来。"}},
  {{"character": "李雷", "text": "韩梅梅！你听我解释！"}},
  {{"character": "旁白", "text": "他的声音在空荡的房间里回响。韩梅梅背对着他，肩膀轻轻颤抖，没有转身。"}}
]

当前章节：
{content}
"""


def send_ai(content: str, previous_result: str = "无", ai_config: Dict[str, str] | None = None) -> str:
    """Call the user's database-configured model and return raw JSON-like text."""
    config = ai_config or {}
    api_key = (config.get("api_key") or "").strip()
    base_url = (config.get("base_url") or "").strip()
    model = (config.get("model") or "").strip()
    if not api_key:
        raise ValueError("数据库中没有该用户的大模型 API Key，请先完成模型设置")
    if not base_url:
        raise ValueError("数据库中没有该用户的大模型 Base URL，请先完成模型设置")
    if not model:
        raise ValueError("数据库中没有该用户的大模型名称，请先完成模型设置")

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=AI_PARSE_TIMEOUT)
    system_prompt = "你是一个小说文本解析器。请严格把小说章节解析为 JSON 数组，每个元素包含 character 和 text。"
    user_prompt = build_prompt(content, previous_result)
    messages = (
        [{"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}]
        if is_reasoning_model(model)
        else [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=False,
        )
    except APITimeoutError as exc:
        raise TimeoutError(f"大模型解析超时，已等待 {AI_PARSE_TIMEOUT} 秒。建议先选择较少章节解析，或换响应更快的模型。") from exc
    return str(response.choices[0].message.content or "")


def clean_json_text(json_text: str) -> str:
    """Remove common Markdown wrappers and keep only the JSON array."""
    text = (json_text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return text.strip()


def parse_dialogue_json(json_text: str) -> List[Dict[str, Any]]:
    """Parse and normalize model output into dialogue rows."""
    cleaned = clean_json_text(json_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        snippet = (json_text or "").strip().replace("\n", " ")[:500]
        raise ValueError(f"AI 返回内容不是合法 JSON：{exc.msg}；返回片段：{snippet}") from exc
    if not isinstance(data, list):
        raise ValueError("AI 返回内容不是 JSON 数组")

    dialogues = []
    for item in data:
        if not isinstance(item, dict):
            continue
        character = str(item.get("character") or "旁白").strip() or "旁白"
        text = str(item.get("text") or "").strip()
        if text:
            dialogues.append({"character": character, "text": text})

    if not dialogues:
        raise ValueError("AI 返回的 JSON 数组没有有效内容")
    return dialogues


def convert_chapter(content: str, previous_result: str = "无", ai_config: Dict[str, str] | None = None) -> List[Dict[str, Any]]:
    raw = send_ai(content, previous_result, ai_config)
    return parse_dialogue_json(raw)


def validate_ai_config(ai_config: Dict[str, str]) -> None:
    api_key = (ai_config.get("api_key") or "").strip()
    base_url = (ai_config.get("base_url") or "").strip()
    model = (ai_config.get("model") or "").strip()
    if not api_key:
        raise ValueError("请填写 API Key")
    if not base_url:
        raise ValueError("请填写 Base URL")
    if not model:
        raise ValueError("请选择或填写模型名称")

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=AI_VALIDATE_TIMEOUT)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "请只回复 ok"}],
            stream=False,
        )
    except APITimeoutError as exc:
        raise TimeoutError(f"模型验证超时，已等待 {AI_VALIDATE_TIMEOUT} 秒，请检查接口地址、网络或模型服务状态。") from exc
    if not (response.choices and response.choices[0].message.content):
        raise ValueError("模型接口没有返回有效内容")
