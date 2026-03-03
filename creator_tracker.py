import os
import re
import time
import httpx
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "tiktok-scraper7.p.rapidapi.com"
SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "google_credentials.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "TikTok账号", "昵称", "粉丝数", "获赞数",
    "邮箱", "简介", "Instagram", "Twitter",
    "主页链接", "来源话题", "发现时间", "近月均播", "视频风格", "是否触达", "备注",
]

# 视频风格关键词映射（按优先级排列）
STYLE_KEYWORDS = [
    ("开箱测评", ["unboxing", "unbox", "open", "opening", "开箱", "review", "worth it", "honest"]),
    ("收藏展示", ["collection", "display", "showcase", "shelf", "haul", "show off", "all my", "entire"]),
    ("购物分享", ["bought", "shopping", "shop with me", "found", "grail", "hunt", "thrift", "store"]),
    ("创意二创", ["diy", "custom", "repaint", "art", "draw", "create", "make", "craft", "design"]),
    ("日常Vlog", ["day", "vlog", "life", "daily", "morning", "night", "routine", "week"]),
]


def get_sheet():
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1
    if sheet.row_count == 0 or not sheet.row_values(1):
        sheet.append_row(HEADERS)
    return sheet


def get_existing_records(sheet) -> tuple[set, set]:
    records = sheet.get_all_values()
    usernames = set()
    emails = set()
    for row in records[1:]:
        if row:
            if row[0]:
                usernames.add(row[0].lstrip("@").lower())
            if len(row) > 4 and row[4]:
                for email in row[4].split(","):
                    e = email.strip().lower()
                    if e:
                        emails.add(e)
    return usernames, emails


def extract_emails(text: str) -> list[str]:
    pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    return list(set(re.findall(pattern, text or "")))


def get_user_info(username: str) -> dict:
    headers = {
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    try:
        resp = httpx.get(
            f"https://{RAPIDAPI_HOST}/user/info",
            params={"unique_id": username},
            headers=headers,
            timeout=15,
        )
        data = resp.json()
        if data.get("code") == 0:
            user = data.get("data", {}).get("user", {})
            stats = data.get("data", {}).get("stats", {})
            return {"user": user, "stats": stats}
    except Exception as e:
        print(f"[Creator] 获取 {username} 信息失败: {e}")
    return {}


def get_user_recent_stats(username: str, days: int = 30) -> dict:
    """获取博主近 N 天的平均播放量和视频风格"""
    headers = {
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    try:
        resp = httpx.get(
            f"https://{RAPIDAPI_HOST}/user/posts",
            params={"unique_id": username, "count": 30},
            headers=headers,
            timeout=20,
        )
        data = resp.json()
        if data.get("code") != 0:
            return {}

        videos = data.get("data", {}).get("videos", [])
        cutoff = time.time() - days * 86400
        recent = [v for v in videos if v.get("create_time", 0) >= cutoff]

        if not recent:
            # 如果近30天无视频，用全部返回的视频估算
            recent = videos

        if not recent:
            return {}

        avg_plays = int(sum(v.get("play_count", 0) for v in recent) / len(recent))
        style = _analyze_style(recent)

        return {
            "avg_plays": fmt_number(avg_plays),
            "style": style,
        }
    except Exception as e:
        print(f"[Creator] 获取 {username} 近期数据失败: {e}")
    return {}


def _analyze_style(videos: list[dict]) -> str:
    """根据视频标题和标签分析博主内容风格"""
    full_text = " ".join(v.get("title", "") for v in videos).lower()

    scores = {}
    for label, keywords in STYLE_KEYWORDS:
        score = sum(full_text.count(kw) for kw in keywords)
        if score > 0:
            scores[label] = score

    if not scores:
        return "潮玩内容"

    # 取得分最高的前两个风格
    top = sorted(scores, key=scores.get, reverse=True)[:2]
    return " / ".join(top)


def fmt_number(n) -> str:
    try:
        n = int(n)
        if n >= 100_000_000:
            return f"{n / 100_000_000:.1f}亿"
        if n >= 10_000:
            return f"{n / 10_000:.1f}万"
        return str(n)
    except Exception:
        return str(n)


def sync_creators_to_sheet(videos: list[dict]):
    """将抓取到的博主信息同步到 Google Sheet"""
    if not SHEET_ID:
        print("[Creator] 未配置 GOOGLE_SHEET_ID，跳过")
        return

    try:
        sheet = get_sheet()
        existing_usernames, existing_emails = get_existing_records(sheet)
    except Exception as e:
        print(f"[Creator] 连接 Google Sheet 失败: {e}")
        return

    # 尝试初始化 Gmail 服务，用于写入时同步校验触达状态
    gmail_service = None
    try:
        from gmail_checker import get_gmail_service, check_email_sent
        gmail_service = get_gmail_service()
        print("[Creator] Gmail 已连接，将同步校验触达状态")
    except Exception:
        print("[Creator] Gmail 未配置，触达状态默认填「否」")

    new_count = 0
    today = datetime.now().strftime("%Y-%m-%d")

    for video in videos:
        username = video.get("author", "").lstrip("@")
        if not username:
            continue

        if username.lower() in existing_usernames:
            print(f"[Creator] @{username} 已存在，跳过")
            continue

        info = get_user_info(username)
        if not info:
            continue

        user = info.get("user", {})
        stats = info.get("stats", {})

        # 粉丝数过滤
        raw_followers = int(stats.get("followerCount", 0))
        if raw_followers < 2000:
            print(f"[Creator] @{username} 粉丝数 {raw_followers} < 2000，跳过")
            continue

        signature = user.get("signature", "") or ""
        emails = extract_emails(signature)

        # 校验触达状态：优先查 Gmail 已发送，其次检查表格邮箱重复
        contacted = "否"
        if emails and gmail_service:
            if any(check_email_sent(gmail_service, e) for e in emails):
                contacted = "已发送"
                print(f"[Creator] @{username} 检测到 Gmail 已发送过邮件")
        if contacted == "否":
            already_in_sheet = any(e.lower() in existing_emails for e in emails)
            if already_in_sheet:
                contacted = "邮箱重复，请核查"
                print(f"[Creator] @{username} 邮箱已存在于表格，标记核查")

        # 获取近期播放和风格数据
        recent_stats = get_user_recent_stats(username)
        avg_plays = recent_stats.get("avg_plays", "")
        style = recent_stats.get("style", "")

        follower_count = fmt_number(stats.get("followerCount", 0))
        heart_count = fmt_number(stats.get("heartCount", 0))
        instagram = user.get("ins_id", "") or ""
        twitter = user.get("twitter_id", "") or ""
        profile_url = f"https://www.tiktok.com/@{username}"
        source = video.get("source", "")
        email_str = ", ".join(emails) if emails else ""

        row = [
            f"@{username}",
            user.get("nickname", username),
            follower_count,
            heart_count,
            email_str,
            signature[:200],
            instagram,
            twitter,
            profile_url,
            source,
            today,
            avg_plays,
            style,
            contacted,
            "",  # 备注
        ]

        try:
            sheet.append_row(row)
            existing_usernames.add(username.lower())
            for e in emails:
                existing_emails.add(e.lower())
            new_count += 1
            print(f"[Creator] 新增 @{username}，均播：{avg_plays or 'N/A'}，风格：{style or 'N/A'}，邮箱：{email_str or '未找到'}")
        except Exception as e:
            print(f"[Creator] 写入 @{username} 失败: {e}")

    print(f"[Creator] 本次新增 {new_count} 位博主到 Google Sheet")
