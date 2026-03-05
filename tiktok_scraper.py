import os
import re
import asyncio
from collections import Counter
from dotenv import load_dotenv

load_dotenv()

TIKTOK_MS_TOKEN = os.getenv("TIKTOK_MS_TOKEN", "")

HASHTAGS = [
    "blindbox",
    "labubu",
    "molly",
    "dimoo",
    "blindboxcollector",
    "designertoy",
    "arttoy",
    "trendytoys",
]

BLOCKED_ACCOUNTS = {
    "popmart", "popmartglobal", "popmart_global", "popmartofficial",
    "popmartusa", "popmartworld", "popmart_official", "popmarteurope",
}

MAX_VIDEOS = 50

GENERIC_TAGS = {
    "fyp", "foryou", "foryoupage", "fypシ", "viral", "trending", "xyzbca",
    "tiktok", "capcut", "parati", "pourtoi", "4u", "fypシ゚viral", "explore",
    "fy", "foru", "humor", "funny", "lol", "omg",
}


def extract_hashtags(text: str) -> list[str]:
    tags = re.findall(r"#(\w+)", text.lower())
    return [t for t in tags if t not in GENERIC_TAGS and len(t) > 1]


def is_blocked(author: str) -> bool:
    name = author.lower().replace(".", "").replace("_", "").replace("-", "")
    for blocked in BLOCKED_ACCOUNTS:
        if blocked.replace("_", "").replace(".", "") in name:
            return True
    return False


def fmt_count(n) -> str:
    try:
        n = int(n)
        if n >= 100_000_000:
            return f"{n / 100_000_000:.1f}亿"
        if n >= 10_000:
            return f"{n / 10_000:.1f}万"
        return str(n)
    except Exception:
        return str(n)


async def _run_scraper_async(max_videos: int) -> dict:
    from TikTokApi import TikTokApi

    videos = []
    seen_urls = set()
    tag_counter = Counter()

    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[TIKTOK_MS_TOKEN] if TIKTOK_MS_TOKEN else [],
            num_sessions=1,
            sleep_after=3,
            headless=False,
            browser="webkit",
        )

        for tag in HASHTAGS:
            if len(videos) >= max_videos:
                break
            try:
                async for item in api.hashtag(name=tag).videos(count=30):
                    raw = item.as_dict or {}
                    desc = raw.get("desc", "")
                    for t in extract_hashtags(desc):
                        tag_counter[t] += 1

                    if len(videos) >= max_videos:
                        continue

                    username = item.author.username if item.author else ""
                    if not username or is_blocked(username):
                        continue

                    nickname = (item.author.as_dict or {}).get("nickname", username)
                    stats = item.stats or {}
                    video_id = item.id or raw.get("id", "")

                    parsed = {
                        "platform": "TikTok",
                        "source": f"#{tag}",
                        "author": f"@{username}",
                        "nickname": nickname,
                        "desc": desc[:120],
                        "plays": fmt_count(stats.get("playCount", 0)),
                        "likes": fmt_count(stats.get("diggCount", 0)),
                        "comments": fmt_count(stats.get("commentCount", 0)),
                        "url": f"https://www.tiktok.com/@{username}/video/{video_id}",
                    }

                    if parsed["url"] not in seen_urls:
                        seen_urls.add(parsed["url"])
                        videos.append(parsed)

            except Exception as e:
                print(f"[TikTok] #{tag} 抓取失败: {e}")

    trending_tags = [f"#{t}" for t, _ in tag_counter.most_common(15)]
    return {"videos": videos[:max_videos], "trending_tags": trending_tags}


def run_tiktok_scraper(max_videos: int = MAX_VIDEOS) -> dict:
    if not TIKTOK_MS_TOKEN:
        print("[TikTok] 未配置 TIKTOK_MS_TOKEN，请在 .env 中添加")
        return {"videos": [], "trending_tags": []}
    return asyncio.run(_run_scraper_async(max_videos))


if __name__ == "__main__":
    import json
    data = run_tiktok_scraper()
    print(json.dumps(data, ensure_ascii=False, indent=2))
