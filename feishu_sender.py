import os
import httpx
from datetime import datetime


def send_feishu_report(tiktok_data: dict):
    """发送飞书日报（支持多个群）"""
    webhook_urls = [u.strip() for u in os.getenv("FEISHU_WEBHOOK_URL", "").split(",") if u.strip()]
    if not webhook_urls:
        print("[飞书] 未配置 FEISHU_WEBHOOK_URL，跳过推送")
        return

    today = datetime.now().strftime("%Y/%m/%d")
    content = _build_report_content(tiktok_data, today)

    payload = {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "body": {
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content,
                    }
                ]
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🎬 tt潮玩热门视频 · {today}",
                },
                "template": "orange",
            },
        },
    }

    try:
        for url in webhook_urls:
            resp = httpx.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            print(f"[飞书] 推送成功 ({url[-20:]}...): {resp.json().get('msg')}")
    except Exception as e:
        print(f"[飞书] 推送失败: {e}")


def _build_report_content(tiktok: dict, today: str) -> str:
    lines = []

    lines.append("**🎬 TikTok 热门视频**\n")
    videos = tiktok.get("videos", [])
    if videos:
        for i, v in enumerate(videos, 1):
            author = v.get("author", "")
            desc = v.get("desc", "").replace("\n", " ")
            plays = v.get("plays", "N/A")
            likes = v.get("likes", "N/A")
            comments = v.get("comments", "N/A")
            url = v.get("url", "")
            source = v.get("source", "")
            lines.append(
                f"{i}. {author}  👁 {plays}  ❤️ {likes}  💬 {comments}\n"
                f"   来源：{source}\n"
                f"   {desc}\n"
                f"   [查看视频]({url})\n"
            )
    else:
        lines.append("暂无数据\n")

    trending = tiktok.get("trending_tags", [])
    if trending:
        lines.append("\n**🔥 TikTok 热门话题**\n")
        tag_links = [
            f"[{tag}](https://www.tiktok.com/tag/{tag.lstrip('#')})"
            for tag in trending[:12]
        ]
        lines.append("  ".join(tag_links) + "\n")

    lines.append(f"\n*更新时间：{today}  · 数据来源：TikTok 美区*")

    return "\n".join(lines)
