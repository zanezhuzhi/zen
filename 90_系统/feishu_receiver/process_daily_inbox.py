from __future__ import annotations

import argparse
import datetime as dt
from collections import Counter, defaultdict
from pathlib import Path

from inbox_utils import NormalizedMessage, parse_daily_entries


BASE_DIR = Path(__file__).resolve().parent
VAULT_DIR = BASE_DIR.parent.parent
INBOX_DIR = VAULT_DIR / "00_入口收件箱" / "飞书同步"
RADAR_DIR = VAULT_DIR / "00_入口收件箱" / "每日雷达"

ACTION_PRIORITY = {
    "写作选题": 1,
    "投资观察": 2,
    "AI/产品机会": 3,
    "互联网产品观察": 4,
    "游戏机制灵感": 5,
    "保留原料": 6,
    "人工判断": 7,
}


def today_string() -> str:
    return dt.datetime.now().astimezone().strftime("%Y-%m-%d")


def card_link(title: str, url: str) -> str:
    if url:
        return f"[{title}]({url})"
    return title


def display_url(message: NormalizedMessage) -> str:
    return message.canonical_url or message.url


def message_link(message: NormalizedMessage) -> str:
    return card_link(message.title, display_url(message))


def is_noise(message: NormalizedMessage) -> bool:
    text = f"{message.title}\n{message.excerpt}".strip()
    if message.url:
        return False
    if len(text) <= 2:
        return True
    return text.lower() in {"test", "测试", "hello", "hi"}


def unique_useful_messages(messages: list[NormalizedMessage]) -> list[NormalizedMessage]:
    result: list[NormalizedMessage] = []
    seen: set[tuple[str, str]] = set()
    for message in messages:
        if is_noise(message):
            continue
        if message.canonical_url:
            key = ("url", message.canonical_url)
        else:
            key = ("title", message.title.strip())
        if key in seen:
            continue
        seen.add(key)
        result.append(message)
    return result


def markdown_list(items: list[str], empty: str = "暂无") -> list[str]:
    if not items:
        return [f"- {empty}"]
    return [f"- {item}" for item in items]


def detect_duplicates(messages: list[NormalizedMessage]) -> list[str]:
    by_url: defaultdict[str, list[NormalizedMessage]] = defaultdict(list)
    by_title: defaultdict[str, list[NormalizedMessage]] = defaultdict(list)
    for message in messages:
        if message.canonical_url:
            by_url[message.canonical_url].append(message)
        title_key = message.title.strip()
        if title_key and title_key != "未命名收件":
            by_title[title_key].append(message)

    lines: list[str] = []
    for group in list(by_url.values()) + list(by_title.values()):
        if len(group) < 2:
            continue
        first = group[0]
        label = message_link(first)
        lines.append(f"{label}：出现 {len(group)} 次")
    return sorted(set(lines))


def domain_summary(messages: list[NormalizedMessage]) -> list[str]:
    counter: Counter[str] = Counter()
    for message in messages:
        for domain in message.domains:
            if domain != "未分类":
                counter[domain] += 1
    return [f"{domain}：{count} 条" for domain, count in counter.most_common()]


def opportunity_lines(messages: list[NormalizedMessage]) -> list[str]:
    useful = unique_useful_messages(messages)
    useful.sort(key=lambda item: (ACTION_PRIORITY.get(item.suggested_action, 99), item.title))
    lines: list[str] = []
    for message in useful[:12]:
        domains = " / ".join(message.domains)
        label = message_link(message)
        excerpt = f"；{message.excerpt}" if message.excerpt else ""
        lines.append(f"**{message.suggested_action}** · {domains} · {label}{excerpt}")
    return lines


def connection_lines(messages: list[NormalizedMessage]) -> list[str]:
    lines: list[str] = []
    for message in unique_useful_messages(messages):
        if "AI" in message.domains and "互联网" in message.domains:
            lines.append(f"{message_link(message)}：连接 [[AI]] 与 [[互联网]]，适合观察 AI 产品化。")
        elif "AI" in message.domains and "游戏" in message.domains:
            lines.append(f"{message_link(message)}：连接 [[AI]] 与 [[游戏]]，适合转成玩法/内容生产问题。")
        elif "投资" in message.domains and ("AI" in message.domains or "互联网" in message.domains):
            lines.append(f"{message_link(message)}：连接 [[投资]] 与产业变化，适合记录反证信号。")
        elif "写作" in message.domains:
            lines.append(f"{message_link(message)}：可进入 [[写作]] 选题池，先写核心观点。")
    return lines[:10]


def manual_judgement_lines(messages: list[NormalizedMessage]) -> list[str]:
    lines = []
    for message in messages:
        if is_noise(message):
            lines.append(f"{message.title}：内容太短或像测试消息，建议删除或忽略。")
        elif message.suggested_action == "人工判断":
            lines.append(f"{message_link(message)}：缺少明确领域，需人工判断是否保留。")
    return lines


def build_radar(date: str) -> tuple[Path, str]:
    note_path = INBOX_DIR / f"{date}.md"
    entries = parse_daily_entries(note_path)
    messages = [entry["normalized"] for entry in entries]
    useful = unique_useful_messages(messages)
    useful_raw_count = len([message for message in messages if not is_noise(message)])

    RADAR_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RADAR_DIR / f"{date}.md"
    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")

    lines = [
        "---",
        "type: daily-radar",
        f"date: {date}",
        "status: review",
        "tags:",
        "  - daily-radar",
        "---",
        "",
        f"# 每日机会雷达 {date}",
        "",
        f"- generated_at: {generated_at}",
        f"- source: [[{date}]]",
        f"- total_items: {len(messages)}",
        f"- useful_items: {len(useful)}",
        f"- duplicate_or_noise_items: {len(messages) - len(useful)}",
        "",
        "## 今日值得保留",
        *markdown_list(
            [
                f"{message_link(message)} · {message.suggested_action} · {' / '.join(message.domains)}"
                for message in useful[:10]
            ]
        ),
        "",
        "## 可输出机会",
        *markdown_list(opportunity_lines(messages)),
        "",
        "## 可连接概念",
        *markdown_list(connection_lines(messages)),
        "",
        "## 今日主题分布",
        *markdown_list(domain_summary(messages)),
        "",
        "## 疑似重复主题",
        *markdown_list(detect_duplicates(messages)),
        "",
        "## 需要人工判断",
        *markdown_list(manual_judgement_lines(messages)),
        "",
        "## 明日最小动作",
        "- [ ] 从上面的可输出机会里挑 1 条，转成灵感卡片或投资观察。",
        "- [ ] 把 1 条有价值输入链接到 [[AI]] / [[互联网]] / [[游戏]] / [[投资]] / [[写作]]。",
        "- [ ] 删除或忽略明显测试消息。",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return output_path, f"items={len(messages)} useful={len(useful)} raw_useful={useful_raw_count}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a private daily opportunity radar from Feishu inbox notes.")
    parser.add_argument("--date", default=today_string(), help="Date in YYYY-MM-DD format. Defaults to today.")
    args = parser.parse_args()
    output_path, summary = build_radar(args.date)
    print(f"generated {output_path} ({summary})")


if __name__ == "__main__":
    main()
