from __future__ import annotations

import datetime as dt
import html
import json
import logging
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

APP_ID = os.getenv("FEISHU_APP_ID", "").strip()
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "").strip()
VERIFICATION_TOKEN = os.getenv("FEISHU_VERIFICATION_TOKEN", "").strip()
ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "").strip()
REPLY_ENABLED = os.getenv("FEISHU_REPLY_ENABLED", "true").strip().lower() in {"1", "true", "yes", "y"}

INBOX_DIR = Path(os.getenv("OBSIDIAN_INBOX_DIR", r"D:\==我的学习库==\00_入口收件箱\飞书同步"))
LOG_FILE = Path(os.getenv("OBSIDIAN_LOG_FILE", r"D:\==我的学习库==\90_系统\logs\feishu_receiver.log"))

INBOX_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def decode_content(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {"raw": value}
    except Exception:
        return {"raw": raw}


def content_to_text(message_type: str | None, content: dict[str, Any]) -> str:
    if message_type == "text":
        return str(content.get("text", "")).strip()
    if message_type == "post":
        return json.dumps(content, ensure_ascii=False, indent=2)
    if "text" in content:
        return str(content.get("text", "")).strip()
    return json.dumps(content, ensure_ascii=False, indent=2)


def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>\"]+", text)


def get_sender_id(event: P2ImMessageReceiveV1) -> str:
    sender = getattr(event.event, "sender", None)
    sender_id = getattr(sender, "sender_id", None)
    for attr in ("open_id", "user_id", "union_id"):
        value = getattr(sender_id, attr, None)
        if value:
            return value
    return ""


def append_event_to_daily_note(event: P2ImMessageReceiveV1) -> Path:
    received_at = now_local()
    message = event.event.message
    sender = event.event.sender
    content = decode_content(message.content)
    text = content_to_text(message.message_type, content)
    urls = extract_urls(text)
    note_path = INBOX_DIR / f"{received_at:%Y-%m-%d}.md"

    if not note_path.exists():
        note_path.write_text(f"# 飞书同步 {received_at:%Y-%m-%d}\n\n", encoding="utf-8")

    lines = [
        "---",
        f"## {received_at:%H:%M:%S} {message.message_type or 'unknown'}",
        "",
        f"- received_at: {received_at.isoformat(timespec='seconds')}",
        f"- message_id: `{message.message_id or ''}`",
        f"- chat_id: `{message.chat_id or ''}`",
        f"- chat_type: `{message.chat_type or ''}`",
        f"- sender_type: `{getattr(sender, 'sender_type', '')}`",
        f"- sender_id: `{get_sender_id(event)}`",
        f"- status: received",
    ]
    if urls:
        lines.extend(["", "### Links"])
        lines.extend(f"- {item}" for item in sorted(set(urls)))
    lines.extend(["", "### Content"])
    if text:
        lines.extend(["```text", html.unescape(text).replace("```", "` ` `"), "```"])
    else:
        lines.append("_empty_")
    lines.extend(["", "### Raw Content", "```json", json.dumps(content, ensure_ascii=False, indent=2), "```", ""])

    with note_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
        f.write("\n")

    return note_path


def make_api_client() -> lark.Client:
    return (
        lark.Client.builder()
        .app_id(APP_ID)
        .app_secret(APP_SECRET)
        .log_level(lark.LogLevel.INFO)
        .build()
    )


api_client: lark.Client | None = None


def reply_received(message_id: str) -> None:
    if not REPLY_ENABLED or not message_id:
        return
    global api_client
    if api_client is None:
        api_client = make_api_client()

    request = (
        ReplyMessageRequest.builder()
        .message_id(message_id)
        .request_body(
            ReplyMessageRequestBody.builder()
            .msg_type("text")
            .content(json.dumps({"text": "已收录"}, ensure_ascii=False))
            .uuid(str(uuid.uuid4()))
            .build()
        )
        .build()
    )
    response = api_client.im.v1.message.reply(request)
    if not response.success():
        logging.warning("failed to reply: code=%s msg=%s", response.code, response.msg)


def on_message(event: P2ImMessageReceiveV1) -> None:
    note_path = append_event_to_daily_note(event)
    message_id = event.event.message.message_id or ""
    logging.info("saved feishu message %s to %s", message_id, note_path)
    try:
        reply_received(message_id)
    except Exception:
        logging.exception("reply failed")


def main() -> None:
    if not APP_ID or not APP_SECRET:
        raise SystemExit("FEISHU_APP_ID and FEISHU_APP_SECRET are required in .env")

    event_handler = (
        lark.EventDispatcherHandler.builder(ENCRYPT_KEY, VERIFICATION_TOKEN)
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )

    client = lark.ws.Client(
        APP_ID,
        APP_SECRET,
        log_level=lark.LogLevel.INFO,
        event_handler=event_handler,
    )
    logging.info("feishu receiver starting with app_id=%s", APP_ID)
    logging.info("inbox_dir=%s", INBOX_DIR)
    client.start()


if __name__ == "__main__":
    main()
