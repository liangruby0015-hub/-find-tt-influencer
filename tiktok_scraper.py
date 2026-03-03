import os
import json
import re
from collections import Counter
import httpx
from dotenv import load_dotenv

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "tiktok-scraper7.p.rapidapi.com"

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


# 通用无意义标签，过滤掉
GENERIC_TAGS = {
    "fyp", "foryou", "foryoupage", "fypシ", "viral", "trending", "xyzbca",
    "tiktok", "capcut", "parati", "pourtoi", "4u", "fypシ゚viral", "explore",
    "fy", "foru", "humor", "funny", "lol", "omg",
}


def extract_hashtags(text: str) -> list[str]:
    """从视频标题中提取 hashtag"""
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


def get_challenge_id(tag: str) -> str:
    headers = {
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    try:
        resp = httpx.get(
            f"https://{RAPIDAPI_HOST}/challenge/info",
            params={"challenge_name": tag},
            headers=headers,
            timeout=15,
        )
        data = resp.json()
        if data.get("code") == 0:
            return data["data"]["id"]
    except Exception as e:
        print(f"[TikTok] 获取 #{tag} challenge_id 失败: {e}")
    return ""


def fetch_challenge_videos(challenge_id: str, count: int = 30) -> list[dict]:
    headers = {
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    try:
        resp = httpx.get(
            f"https://{RAPIDAPI_HOST}/challenge/posts",
            params={"challenge_id": challenge_id, "count": count},
            headers=headers,
            timeout=20,
        )
        data = resp.json()
        if data.get("code") == 0:
            return data.get("data", {}).get("videos", [])
    except Exception as e:
        print(f"[TikTok] 获取话题视频失败: {e}")
    return []


def parse_video(item: dict, source: str):
    try:
        if item.get("region", "") != "US":
            return None

        author = item.get("author", {})
        username = author.get("unique_id", author.get("uniqueId", ""))
        nickname = author.get("nickname", username)

        if not username or is_blocked(username):
            return None

        video_id = item.get("video_id", item.get("aweme_id", ""))
        desc = (item.get("title", "") or "").strip()

        return {
            "platform": "TikTok",
            "source": source,
            "author": f"@{username}",
            "nickname": nickname,
            "desc": desc[:120],
            "plays": fmt_count(item.get("play_count", 0)),
            "likes": fmt_count(item.get("digg_count", 0)),
            "comments": fmt_count(item.get("comment_count", 0)),
            "url": f"https://www.tiktok.com/@{username}/video/{video_id}",
        }
    except Exception as e:
        print(f"[TikTok] 解析视频失败: {e}")
        return None


def run_tiktok_scraper(max_videos: int = MAX_VIDEOS) -> dict:
    if not RAPIDAPI_KEY:
        print("[TikTok] 未配置 RAPIDAPI_KEY")
        return {"videos": [], "trending_tags": []}

    videos = []
    seen_urls = set()
    tag_counter = Counter()

    for tag in HASHTAGS:
        if len(videos) >= max_videos:
            break

        challenge_id = get_challenge_id(tag)
        if not challenge_id:
            print(f"[TikTok] #{tag} 未找到 challenge_id，跳过")
            continue

        items = fetch_challenge_videos(challenge_id)
        for item in items:
            # 从所有视频标题中提取 hashtag 并计数（不受 max_videos 限制）
            title = item.get("title", "") or ""
            for t in extract_hashtags(title):
                tag_counter[t] += 1

            if len(videos) >= max_videos:
                continue
            parsed = parse_video(item, f"#{tag}")
            if parsed and parsed["url"] not in seen_urls:
                seen_urls.add(parsed["url"])
                videos.append(parsed)

    # 取频次最高的 15 个话题
    trending_tags = [f"#{t}" for t, _ in tag_counter.most_common(15)]

    return {
        "videos": videos[:max_videos],
        "trending_tags": trending_tags,
    }


if __name__ == "__main__":
    data = run_tiktok_scraper()
    print(json.dumps(data, ensure_ascii=False, indent=2))
