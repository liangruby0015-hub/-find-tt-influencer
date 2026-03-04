import os
import re
import time
import asyncio
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

TIKTOK_MS_TOKEN = os.getenv("TIKTOK_MS_TOKEN", "")
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


def _analyze_style(videos: list[dict]) -> str:
    full_text = " ".join(v.get("title", "") for v in videos).lower()
    scores = {}
    for label, keywords in STYLE_KEYWORDS:
        score = sum(full_text.count(kw) for kw in keywords)
        if score > 0:
            scores[label] = score
    if not scores:
        return "潮玩内容"
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


async def _get_user_info_async(api, username: str) -> dict:
    try:
        user_obj = api.user(username=username)
        await user_obj.info()
        raw = user_obj.as_dict or {}
        # TikTokApi 返回结构: {"userInfo": {"user": {...}, "stats": {...}}}
        user_info = raw.get("userInfo", {})
        user = user_info.get("user", {})
        stats = user_info.get("stats", {})
        if not user and not stats:
            # 兼容另一种结构
            user = raw.get("user", {})
            stats = raw.get("stats", {})
        return {"user": user, "stats": stats}
    except Exception as e:
        print(f"[Creator] 获取 {username} 信息失败: {e}")
    return {}


async def _get_user_recent_stats_async(api, username: str, days: int = 30) -> dict:
    try:
        cutoff = time.time() - days * 86400
        videos = []
        async for video in api.user(username=username).videos(count=30):
            raw = video.as_dict or {}
            create_time = raw.get("createTime", 0)
            play_count = int((video.stats or {}).get("playCount", 0) or 0)
            title = raw.get("desc", "")
            videos.append({
                "create_time": create_time,
                "play_count": play_count,
                "title": title,
            })

        recent = [v for v in videos if v["create_time"] >= cutoff]
        if not recent:
            recent = videos
        if not recent:
            return {}

        avg_plays = int(sum(v["play_count"] for v in recent) / len(recent))
        style = _analyze_style(recent)
        return {
            "avg_plays": fmt_number(avg_plays),
            "style": style,
        }
    except Exception as e:
        print(f"[Creator] 获取 {username} 近期数据失败: {e}")
    return {}


async def _process_creators_async(videos, existing_usernames, existing_emails, gmail_service, today):
    from TikTokApi import TikTokApi

    new_rows = []

    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[TIKTOK_MS_TOKEN] if TIKTOK_MS_TOKEN else [],
            num_sessions=1,
            sleep_after=3,
            headless=False,
        )

        for video in videos:
            username = video.get("author", "").lstrip("@")
            if not username:
                continue

            if username.lower() in existing_usernames:
                print(f"[Creator] @{username} 已存在，跳过")
                continue

            info = await _get_user_info_async(api, username)
            if not info:
                continue
            await asyncio.sleep(1)

            user = info.get("user", {})
            stats = info.get("stats", {})

            raw_followers = int(stats.get("followerCount", 0))
            if raw_followers < 2000:
                print(f"[Creator] @{username} 粉丝数 {raw_followers} < 2000，跳过")
                continue

            signature = user.get("signature", "") or ""
            emails = extract_emails(signature)

            contacted = "否"
            if emails and gmail_service:
                from gmail_checker import check_email_sent
                if any(check_email_sent(gmail_service, e) for e in emails):
                    contacted = "已发送"
                    print(f"[Creator] @{username} 检测到 Gmail 已发送过邮件")
            if contacted == "否":
                if any(e.lower() in existing_emails for e in emails):
                    contacted = "邮箱重复，请核查"
                    print(f"[Creator] @{username} 邮箱已存在于表格，标记核查")

            recent_stats = await _get_user_recent_stats_async(api, username)
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
                "",
            ]

            new_rows.append((row, username, emails))
            print(f"[Creator] 新增 @{username}，均播：{avg_plays or 'N/A'}，风格：{style or 'N/A'}，邮箱：{email_str or '未找到'}")

    return new_rows


def _update_existing_contacted(sheet, gmail_service):
    """扫描表格中状态为「否」且有邮箱的行，重新查 Gmail 更新触达状态"""
    from gmail_checker import check_email_sent
    try:
        rows = sheet.get_all_values()
    except Exception as e:
        print(f"[Creator] 读取表格失败: {e}")
        return

    updated = 0
    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 14:
            continue
        email_str = row[4].strip()
        contacted = row[13].strip()
        if not email_str or contacted != "否":
            continue
        emails = [e.strip() for e in email_str.split(",") if e.strip()]
        if any(check_email_sent(gmail_service, e) for e in emails):
            try:
                sheet.update_cell(i, 14, "已发送")
                updated += 1
                print(f"[Creator] 更新 {row[0]} 触达状态 → 已发送")
            except Exception as e:
                print(f"[Creator] 更新 {row[0]} 失败: {e}")

    print(f"[Creator] 历史触达状态更新完成，共更新 {updated} 条")


def _dedup_sheet(sheet):
    """删除表格中重复的博主行（保留第一次出现的）"""
    rows = sheet.get_all_values()
    seen = {}
    to_delete = []
    for i, row in enumerate(rows[1:], start=2):
        username = row[0].strip().lower() if row else ""
        if not username:
            continue
        if username in seen:
            to_delete.append(i)
        else:
            seen[username] = i
    for row_idx in sorted(to_delete, reverse=True):
        sheet.delete_rows(row_idx)
    if to_delete:
        print(f"[Creator] 去重完成，删除 {len(to_delete)} 个重复行")


def sync_creators_to_sheet(videos: list[dict]):
    if not SHEET_ID:
        print("[Creator] 未配置 GOOGLE_SHEET_ID，跳过")
        return

    if not TIKTOK_MS_TOKEN:
        print("[Creator] 未配置 TIKTOK_MS_TOKEN，跳过")
        return

    try:
        sheet = get_sheet()
        existing_usernames, existing_emails = get_existing_records(sheet)
        _dedup_sheet(sheet)
    except Exception as e:
        print(f"[Creator] 连接 Google Sheet 失败: {e}")
        return

    gmail_service = None
    try:
        from gmail_checker import get_gmail_service
        gmail_service = get_gmail_service()
        print("[Creator] Gmail 已连接，将同步校验触达状态")
        _update_existing_contacted(sheet, gmail_service)
    except Exception:
        print("[Creator] Gmail 未配置，触达状态默认填「否」")

    today = datetime.now().strftime("%Y-%m-%d")

    try:
        new_rows = asyncio.run(_process_creators_async(
            videos, existing_usernames, existing_emails, gmail_service, today
        ))
    except Exception as e:
        print(f"[Creator] 处理博主数据失败: {e}")
        return

    new_count = 0
    for row, username, emails in new_rows:
        try:
            sheet.append_row(row)
            existing_usernames.add(username.lower())
            for e in emails:
                existing_emails.add(e.lower())
            new_count += 1
        except Exception as e:
            print(f"[Creator] 写入 @{username} 失败: {e}")

    print(f"[Creator] 本次新增 {new_count} 位博主到 Google Sheet")
