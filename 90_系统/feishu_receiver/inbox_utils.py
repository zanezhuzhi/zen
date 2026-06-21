from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


TRACKING_PARAMS = {
    "app",
    "category_new",
    "module_name",
    "oc",
    "req_id",
    "req_id_new",
    "share_did",
    "share_token",
    "share_uid",
    "timestamp",
    "tt_from",
    "upstream_biz",
    "use_new_style",
}

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "AI": [
        "ai",
        "aigc",
        "agent",
        "llm",
        "大模型",
        "模型",
        "智能体",
        "自动化",
        "提示词",
        "token",
        "openai",
        "claude",
        "gemini",
        "混元",
    ],
    "互联网": [
        "微信",
        "小程序",
        "平台",
        "社区",
        "内容",
        "流量",
        "增长",
        "商业化",
        "产品",
        "用户",
        "抖音",
        "视频号",
        "公众号",
    ],
    "游戏": [
        "游戏",
        "玩家",
        "关卡",
        "玩法",
        "数值",
        "机制",
        "剧情",
        "叙事",
        "养成",
        "战斗",
        "steam",
    ],
    "投资": [
        "投资",
        "股票",
        "a股",
        "港股",
        "美股",
        "财报",
        "估值",
        "利润",
        "营收",
        "公司",
        "行业",
        "基金",
        "持仓",
        "买入",
        "卖出",
        "风险",
    ],
    "写作": [
        "写作",
        "选题",
        "标题",
        "表达",
        "文章",
        "脚本",
        "结构",
        "观点",
        "读者",
        "发布",
    ],
}

ACTION_BY_DOMAIN = {
    "AI": "AI/产品机会",
    "互联网": "互联网产品观察",
    "游戏": "游戏机制灵感",
    "投资": "投资观察",
    "写作": "写作选题",
}


@dataclass
class NormalizedMessage:
    title: str
    url: str
    source: str
    excerpt: str
    domains: list[str]
    suggested_action: str
    message_type: str
    canonical_url: str


def markdown_escape_block(text: str) -> str:
    return text.replace("```", "` ` `")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def truncate(text: str, limit: int = 240) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def extract_urls(text: str) -> list[str]:
    if not text:
        return []
    urls = re.findall(r"https?://[^\s<>\"]+", text)
    return [url.rstrip(").,，。；;\"'") for url in urls]


def decode_content(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {"raw": value}
    except Exception:
        return {"raw": raw}


def collect_text_values(value: Any, *, max_items: int = 24) -> list[str]:
    results: list[str] = []

    def visit(node: Any) -> None:
        if len(results) >= max_items:
            return
        if isinstance(node, dict):
            for key in ("title", "content", "text", "alt", "raw"):
                item = node.get(key)
                if isinstance(item, str):
                    cleaned = clean_text(item)
                    if cleaned:
                        results.append(cleaned)
                elif isinstance(item, dict):
                    visit(item)
            for nested_key in ("header", "elements", "extra", "card_link"):
                if nested_key in node:
                    visit(node[nested_key])
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return dedupe_keep_order(results)


def parse_user_dsl(content: dict[str, Any]) -> dict[str, Any] | None:
    raw = content.get("user_dsl")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        decoded = json.loads(raw)
        return decoded if isinstance(decoded, dict) else None
    except Exception:
        return None


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    url = url.replace("×tamp=", "timestamp=")
    parsed = urlparse(url)
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lower = key.lower()
        if lower.startswith("utm_") or lower in TRACKING_PARAMS:
            continue
        query.append((key, value))
    clean_query = urlencode(sorted(query), doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path, "", clean_query, ""))


def source_from_url(url: str) -> str:
    if not url:
        return ""
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def infer_domains(text: str) -> list[str]:
    haystack = text.lower()
    scores: list[tuple[int, str]] = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword.lower() in haystack)
        if score:
            scores.append((score, domain))
    scores.sort(key=lambda item: (-item[0], item[1]))
    return [domain for _, domain in scores[:3]]


def infer_action(domains: list[str], title: str, excerpt: str, url: str) -> str:
    joined = f"{title}\n{excerpt}\n{url}"
    if len(clean_text(joined)) < 18:
        return "人工判断"
    if "写作" in domains:
        return ACTION_BY_DOMAIN["写作"]
    if "投资" in domains:
        return ACTION_BY_DOMAIN["投资"]
    if "AI" in domains:
        return ACTION_BY_DOMAIN["AI"]
    if "游戏" in domains:
        return ACTION_BY_DOMAIN["游戏"]
    if "互联网" in domains:
        return ACTION_BY_DOMAIN["互联网"]
    if url:
        return "保留原料"
    return "人工判断"


def normalize_content(message_type: str | None, content: dict[str, Any]) -> NormalizedMessage:
    if message_type == "text":
        text = clean_text(content.get("text") or content.get("raw"))
        urls = extract_urls(text)
        title_source = text.splitlines()[0] if text else ""
        title = truncate(title_source or (urls[0] if urls else "未命名收件"), 60)
        url = urls[0] if urls else ""
        excerpt = truncate(text, 280) if len(text) > 60 else ""
        domains = infer_domains("\n".join([title, excerpt, url]))
        action = infer_action(domains, title, excerpt, url)
        return NormalizedMessage(
            title=title,
            url=url,
            source=source_from_url(url),
            excerpt=excerpt,
            domains=domains or ["未分类"],
            suggested_action=action,
            message_type=message_type or "unknown",
            canonical_url=canonicalize_url(url),
        )

    user_dsl = parse_user_dsl(content)
    text_values = collect_text_values(content)
    if user_dsl:
        text_values.extend(collect_text_values(user_dsl))
        text_values = dedupe_keep_order(text_values)

    title = clean_text(content.get("title"))
    if not title and user_dsl:
        header = user_dsl.get("header", {})
        if isinstance(header, dict):
            title_values = collect_text_values(header, max_items=4)
            title = title_values[0] if title_values else ""
    if not title and text_values:
        title = truncate(text_values[0], 60)
    if not title:
        title = "未命名收件"

    explicit_url = ""
    card_link = content.get("card_link")
    if isinstance(card_link, dict):
        explicit_url = clean_text(
            card_link.get("url")
            or card_link.get("pc_url")
            or card_link.get("ios_url")
            or card_link.get("android_url")
        )
    all_text = "\n".join(text_values + [json.dumps(content, ensure_ascii=False)])
    urls = dedupe_keep_order([explicit_url] + extract_urls(all_text))
    url = urls[0] if urls else ""

    excerpt_candidates = [item for item in text_values if item != title and not item.startswith("http")]
    excerpt = truncate(excerpt_candidates[0] if excerpt_candidates else all_text, 280)
    domains = infer_domains("\n".join([title, excerpt, url]))
    action = infer_action(domains, title, excerpt, url)

    return NormalizedMessage(
        title=title,
        url=url,
        source=source_from_url(url),
        excerpt=excerpt,
        domains=domains or ["未分类"],
        suggested_action=action,
        message_type=message_type or "unknown",
        canonical_url=canonicalize_url(url),
    )


def content_to_text(message_type: str | None, content: dict[str, Any]) -> str:
    if message_type == "text":
        return clean_text(content.get("text"))
    if message_type == "post":
        return json.dumps(content, ensure_ascii=False, indent=2)
    if "text" in content and isinstance(content.get("text"), str):
        return clean_text(content.get("text"))
    return json.dumps(content, ensure_ascii=False, indent=2)


def parse_daily_entries(note_path: Path) -> list[dict[str, Any]]:
    if not note_path.exists():
        return []
    raw = note_path.read_text(encoding="utf-8")
    entries: list[dict[str, Any]] = []
    pattern = re.compile(
        r"^---\s*\n## (?P<time>\d{2}:\d{2}:\d{2}) (?P<message_type>\S+)\s*\n(?P<body>.*?)(?=^---\s*\n## |\Z)",
        re.M | re.S,
    )
    for match in pattern.finditer(raw):
        body = match.group("body")
        metadata: dict[str, str] = {}
        for line in body.splitlines():
            if not line.startswith("- ") or ": " not in line:
                continue
            key, value = line[2:].split(": ", 1)
            metadata[key.strip()] = value.strip().strip("`")

        raw_json = extract_fenced_section(body, "Raw Content", "json")
        content_block = extract_fenced_section(body, "Content", "text")
        content = decode_content(raw_json) if raw_json else {"text": content_block}
        normalized = normalize_content(match.group("message_type"), content)
        entries.append(
            {
                "time": match.group("time"),
                "message_type": match.group("message_type"),
                "metadata": metadata,
                "content": content,
                "normalized": normalized,
            }
        )
    return entries


def extract_fenced_section(body: str, heading: str, lang: str) -> str:
    pattern = re.compile(
        rf"^### {re.escape(heading)}\s*\n```(?:{re.escape(lang)})?\s*\n(.*?)\n```",
        re.M | re.S,
    )
    match = pattern.search(body)
    return match.group(1).strip() if match else ""
