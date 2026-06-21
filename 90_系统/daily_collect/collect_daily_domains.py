from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
VAULT_DIR = BASE_DIR.parent.parent
FEISHU_UTILS_DIR = VAULT_DIR / "90_系统" / "feishu_receiver"
if str(FEISHU_UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(FEISHU_UTILS_DIR))

from inbox_utils import canonicalize_url, clean_text, source_from_url, truncate  # noqa: E402


CATALOG_PATH = BASE_DIR / "source_catalog.json"
CONFIG_DIR = VAULT_DIR / "90_系统" / "config"
FEEDBACK_PATH = CONFIG_DIR / "daily_collect_feedback.json"
SEEN_PATH = CONFIG_DIR / "daily_collect_seen.json"
OUTPUT_DIR = VAULT_DIR / "00_入口收件箱" / "每日信息候选"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ZenDailyCollector/1.0"
COMMON_NEGATIVE_KEYWORDS = ["广告", "软文", "招商", "加盟", "课程", "培训", "下载", "破解"]


@dataclass
class Candidate:
    domain: str
    title: str
    url: str
    source: str
    excerpt: str
    published_at: str
    source_label: str
    query: str
    matched_keywords: list[str]
    negative_keywords: list[str]
    score: float
    reasons: list[str] = field(default_factory=list)

    @property
    def canonical_url(self) -> str:
        return canonicalize_url(self.url)

    @property
    def host(self) -> str:
        host = source_from_url(self.canonical_url or self.url)
        if host == "news.google.com" and self.source:
            return self.source
        return host

    @property
    def item_id(self) -> str:
        key = self.canonical_url or f"{self.domain}:{self.title}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def today_string() -> str:
    return dt.datetime.now().astimezone().strftime("%Y-%m-%d")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def fetch_url(url: str, timeout: int = 15) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def google_news_url(query: str, market: str) -> str:
    gl = "CN" if market.lower().startswith("zh") else "US"
    ceid = f"{gl}:zh-Hans" if gl == "CN" else f"{gl}:en"
    if "when:" not in query:
        query = f"{query} when:7d"
    params = {
        "q": query,
        "hl": "zh-CN" if gl == "CN" else "en-US",
        "gl": gl,
        "ceid": ceid,
    }
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def strip_markup(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return clean_text(text)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def first_child_text(node: ET.Element, name: str) -> str:
    for child in list(node):
        if local_name(child.tag) == name:
            return clean_text(child.text or "")
    return ""


def link_from_item(node: ET.Element) -> str:
    link_text = first_child_text(node, "link")
    if link_text:
        return link_text
    for child in list(node):
        if local_name(child.tag) == "link":
            href = child.attrib.get("href")
            if href:
                return href
    return ""


def parse_date(value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone().isoformat(timespec="minutes")
    except Exception:
        return value


def parse_feed(xml_text: str, domain: str, source_label: str, query: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    raw_items: list[ET.Element] = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
    items: list[dict[str, str]] = []
    for item in raw_items:
        title = strip_markup(first_child_text(item, "title"))
        url = link_from_item(item)
        excerpt = strip_markup(first_child_text(item, "description") or first_child_text(item, "summary"))
        published_at = (
            first_child_text(item, "pubDate")
            or first_child_text(item, "published")
            or first_child_text(item, "updated")
        )
        source = first_child_text(item, "source") or source_from_url(url)
        if not title or not url:
            continue
        items.append(
            {
                "domain": domain,
                "title": title,
                "url": url,
                "source": source,
                "excerpt": excerpt,
                "published_at": parse_date(published_at),
                "source_label": source_label,
                "query": query,
            }
        )
    return items


def contains_keyword(text: str, keyword: str) -> bool:
    return keyword.lower() in text.lower()


def matched_keywords(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if contains_keyword(text, keyword)]


def freshness_score(published_at: str, date: str) -> tuple[float, str]:
    age = age_days(published_at, date)
    if age is None:
        return 0.0, ""
    if age <= 1:
        return 1.5, "近 24-48 小时"
    if age <= 3:
        return 0.8, "近 3 天"
    return 0.0, ""


def age_days(published_at: str, date: str) -> int | None:
    if not published_at:
        return None
    try:
        published = dt.datetime.fromisoformat(published_at)
        target = dt.datetime.fromisoformat(date).astimezone()
        return abs((target.date() - published.date()).days)
    except Exception:
        return None


def feedback_score(candidate: Candidate, feedback: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    host_stat = feedback.get("hosts", {}).get(candidate.host, {})
    host_keep = int(host_stat.get("keep", 0))
    host_drop = int(host_stat.get("drop", 0))
    if host_keep > host_drop:
        score += min(2.5, 0.6 * (host_keep - host_drop))
        reasons.append(f"历史常收录来源：{candidate.host}")
    elif host_drop > host_keep:
        score -= min(3.5, 0.8 * (host_drop - host_keep))
        reasons.append(f"历史常移除来源：{candidate.host}")

    text = f"{candidate.title}\n{candidate.excerpt}"
    for term, stat in feedback.get("terms", {}).items():
        if not contains_keyword(text, term):
            continue
        keep = int(stat.get("keep", 0))
        drop = int(stat.get("drop", 0))
        if keep > drop:
            score += min(1.5, 0.35 * (keep - drop))
        elif drop > keep:
            score -= min(2.0, 0.45 * (drop - keep))

    domain_stat = feedback.get("domains", {}).get(candidate.domain, {})
    domain_keep = int(domain_stat.get("keep", 0))
    domain_drop = int(domain_stat.get("drop", 0))
    if domain_keep > domain_drop:
        score += min(1.0, 0.2 * (domain_keep - domain_drop))
    elif domain_drop > domain_keep:
        score -= min(1.0, 0.25 * (domain_drop - domain_keep))

    return score, reasons


def score_item(
    raw: dict[str, str],
    domain_config: dict[str, Any],
    feedback: dict[str, Any],
    seen: dict[str, Any],
    date: str,
) -> Candidate:
    text = clean_text(f"{raw['title']}\n{raw.get('excerpt', '')}")
    positives = matched_keywords(text, list(domain_config.get("positive_keywords", [])))
    negatives = matched_keywords(text, list(domain_config.get("negative_keywords", [])) + COMMON_NEGATIVE_KEYWORDS)
    candidate = Candidate(
        domain=raw["domain"],
        title=truncate(raw["title"], 120),
        url=raw["url"],
        source=raw.get("source", ""),
        excerpt=truncate(raw.get("excerpt", ""), 260),
        published_at=raw.get("published_at", ""),
        source_label=raw.get("source_label", ""),
        query=raw.get("query", ""),
        matched_keywords=positives,
        negative_keywords=negatives,
        score=0.0,
    )

    score = 1.0
    reasons = [f"匹配查询：{candidate.source_label}"]
    if positives:
        score += min(8.0, len(positives) * 1.25)
        reasons.append("关键词：" + " / ".join(positives[:6]))
    if negatives:
        score -= min(8.0, len(negatives) * 2.0)
        reasons.append("需谨慎关键词：" + " / ".join(negatives[:4]))

    fresh_score, fresh_reason = freshness_score(candidate.published_at, date)
    score += fresh_score
    if fresh_reason:
        reasons.append(fresh_reason)

    key = candidate.canonical_url or candidate.title
    seen_info = seen.get("items", {}).get(key, {})
    if seen_info and seen_info.get("first_seen") != date:
        score -= 2.5
        reasons.append(f"曾在 {seen_info.get('first_seen')} 出现")

    learned_score, learned_reasons = feedback_score(candidate, feedback)
    score += learned_score
    reasons.extend(learned_reasons)

    candidate.score = round(score, 2)
    candidate.reasons = reasons
    return candidate


def is_too_old(candidate: Candidate, date: str, max_age_days: int) -> bool:
    age = age_days(candidate.published_at, date)
    return age is not None and age > max_age_days


def dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    best_by_key: dict[str, Candidate] = {}
    for candidate in candidates:
        key = candidate.canonical_url or f"{candidate.domain}:{candidate.title.lower()}"
        existing = best_by_key.get(key)
        if existing is None or candidate.score > existing.score:
            best_by_key[key] = candidate
    return list(best_by_key.values())


def fetch_domain_candidates(
    domain: str,
    domain_config: dict[str, Any],
    catalog_market: str,
    feedback: dict[str, Any],
    seen: dict[str, Any],
    date: str,
    errors: list[str],
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for query_config in domain_config.get("queries", []):
        label = query_config.get("label", query_config.get("query", "未命名查询"))
        query = query_config.get("query", "")
        if not query:
            continue
        url = google_news_url(query, catalog_market)
        try:
            xml_text = fetch_url(url)
            raw_items = parse_feed(xml_text, domain, label, query)
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as exc:
            errors.append(f"{domain} / {label}: {exc}")
            continue
        for raw in raw_items:
            candidates.append(score_item(raw, domain_config, feedback, seen, date))
    return dedupe_candidates(candidates)


def markdown_escape(text: str) -> str:
    return text.replace("\n", " ").replace("|", "\\|").replace("`", "'")


def render_candidate(candidate: Candidate, index: int) -> list[str]:
    url = candidate.canonical_url or candidate.url
    keywords = ", ".join(candidate.matched_keywords) if candidate.matched_keywords else "-"
    cautious = ", ".join(candidate.negative_keywords) if candidate.negative_keywords else "-"
    reasons = "；".join(candidate.reasons) if candidate.reasons else "-"
    return [
        f"### {index}. {candidate.title}",
        f"- id: `{candidate.item_id}`",
        f"- domain: {candidate.domain}",
        f"- score: {candidate.score}",
        f"- source: {candidate.source or candidate.host or '-'}",
        f"- host: {candidate.host or '-'}",
        f"- published_at: {candidate.published_at or '-'}",
        f"- url: {url}",
        f"- matched_keywords: {keywords}",
        f"- cautious_keywords: {cautious}",
        f"- reason: {reasons}",
        f"- [ ] 收录 `{candidate.item_id}`",
        f"- [ ] 移除 `{candidate.item_id}`",
        "",
        f"[{markdown_escape(candidate.title)}]({url})",
        "",
        f"> {markdown_escape(candidate.excerpt) if candidate.excerpt else '暂无摘要'}",
        "",
    ]


def render_markdown(
    date: str,
    catalog: dict[str, Any],
    candidates_by_domain: dict[str, list[Candidate]],
    errors: list[str],
) -> str:
    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    total = sum(len(items) for items in candidates_by_domain.values())
    lines = [
        "---",
        "type: daily-domain-brief",
        f"date: {date}",
        "status: review",
        "tags:",
        "  - daily-domain-brief",
        "---",
        "",
        f"# 每日五领域信息候选 {date}",
        "",
        f"- generated_at: {generated_at}",
        f"- total_candidates: {total}",
        "- usage: 勾选每条下面的 `收录` 或 `移除`，晚上运行反馈学习脚本后会沉淀到筛选规则。",
        "- note: 投资相关内容只作为观察候选，不构成投资建议。",
        "",
        "## 今日处理入口",
        "- [ ] 每个领域最多挑 1 条收录。",
        "- [ ] 明显低质、重复、标题党内容勾选移除。",
        "- [ ] 不确定的内容保持未勾选，不会影响筛选规则。",
        "",
        "## 今日总览",
    ]
    for domain, items in candidates_by_domain.items():
        top_titles = "；".join(item.title for item in items[:3]) or "暂无"
        lines.append(f"- [[{domain}]]：{len(items)} 条候选。{top_titles}")
    lines.append("")

    for domain, domain_config in catalog.get("domains", {}).items():
        items = candidates_by_domain.get(domain, [])
        lines.extend([f"## {domain}", ""])
        lines.append("### 核心问题")
        for question in domain_config.get("core_questions", []):
            lines.append(f"- {question}")
        lines.append("")
        if not items:
            lines.extend(["- 暂无候选。", ""])
            continue
        for index, candidate in enumerate(items, start=1):
            lines.extend(render_candidate(candidate, index))

    lines.extend(["## 采集错误", ""])
    if errors:
        lines.extend(f"- {markdown_escape(error)}" for error in errors)
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


def update_seen(seen: dict[str, Any], candidates_by_domain: dict[str, list[Candidate]], date: str) -> dict[str, Any]:
    seen.setdefault("items", {})
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    for items in candidates_by_domain.values():
        for candidate in items:
            key = candidate.canonical_url or candidate.title
            info = seen["items"].setdefault(
                key,
                {
                    "first_seen": date,
                    "title": candidate.title,
                    "domain": candidate.domain,
                    "host": candidate.host,
                },
            )
            info["last_seen"] = date
            info["updated_at"] = now
    return seen


def build_daily_brief(date: str, max_per_domain: int | None = None, min_score: float = 1.0) -> tuple[Path, str]:
    catalog = load_json(CATALOG_PATH, {})
    feedback = load_json(FEEDBACK_PATH, {"version": 1})
    seen = load_json(SEEN_PATH, {"version": 1, "items": {}})
    errors: list[str] = []
    market = catalog.get("market", "zh-CN")
    candidates_by_domain: dict[str, list[Candidate]] = {}

    for domain, domain_config in catalog.get("domains", {}).items():
        candidates = fetch_domain_candidates(domain, domain_config, market, feedback, seen, date, errors)
        max_age_days = int(domain_config.get("max_age_days", 14))
        candidates = [candidate for candidate in candidates if not is_too_old(candidate, date, max_age_days)]
        candidates = [candidate for candidate in candidates if candidate.score >= min_score]
        candidates.sort(key=lambda item: (-item.score, item.title))
        limit = max_per_domain or int(domain_config.get("daily_limit", 8))
        candidates_by_domain[domain] = candidates[:limit]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{date}.md"
    output_path.write_text(render_markdown(date, catalog, candidates_by_domain, errors), encoding="utf-8", newline="\n")

    seen = update_seen(seen, candidates_by_domain, date)
    write_json(SEEN_PATH, seen)

    total = sum(len(items) for items in candidates_by_domain.values())
    return output_path, f"domains={len(candidates_by_domain)} candidates={total} errors={len(errors)}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect daily candidate information for the five knowledge domains.")
    parser.add_argument("--date", default=today_string(), help="Date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--max-per-domain", type=int, default=None, help="Override per-domain candidate limit.")
    parser.add_argument("--min-score", type=float, default=2.0, help="Minimum score to include.")
    args = parser.parse_args()
    output_path, summary = build_daily_brief(args.date, args.max_per_domain, args.min_score)
    print(f"generated {output_path} ({summary})")


if __name__ == "__main__":
    main()
