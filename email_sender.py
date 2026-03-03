import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SENDER_NAME = os.getenv("SENDER_NAME", "Brand Partnerships")
BRAND_NAME = os.getenv("BRAND_NAME", "Our Brand")
REPLY_EMAIL = os.getenv("REPLY_EMAIL", "")

# 视频风格中文 → 英文描述
STYLE_MAP = {
    "开箱测评": "unboxing and review",
    "收藏展示": "collection showcase",
    "购物分享": "shopping haul",
    "创意二创": "creative DIY",
    "日常Vlog": "lifestyle vlog",
    "潮玩内容": "designer toy",
}


def parse_number(s: str) -> int:
    """将格式化数字字符串转回整数（如 '1.4万' → 14000）"""
    if not s:
        return 0
    s = str(s).strip()
    try:
        if "亿" in s:
            return int(float(s.replace("亿", "")) * 100_000_000)
        if "万" in s:
            return int(float(s.replace("万", "")) * 10_000)
        return int(float(s))
    except Exception:
        return 0


def get_eligible_creators(sheet, min_followers=0, max_followers=float("inf"), min_avg_plays=0) -> list[dict]:
    """从 Google Sheet 获取符合条件的未触达博主"""
    rows = sheet.get_all_values()
    if len(rows) <= 1:
        return []

    creators = []
    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 14:
            continue

        email = row[4].strip()
        contacted = row[13].strip()
        if not email or contacted != "否":
            continue

        followers = parse_number(row[2])
        avg_plays = parse_number(row[11])

        if not (min_followers <= followers <= max_followers):
            continue
        if avg_plays < min_avg_plays:
            continue

        style_raw = row[12]
        style_en = " & ".join(
            STYLE_MAP.get(s.strip(), "designer toy")
            for s in style_raw.split("/") if s.strip()
        ) or "designer toy"

        creators.append({
            "row": i,
            "username": row[0],
            "nickname": row[1] or row[0].lstrip("@"),
            "followers": row[2],
            "avg_plays": row[11],
            "style_en": style_en,
            "email": email,
        })

    return creators


def build_email(creator: dict) -> tuple[str, str]:
    """生成个性化邮件主题和正文"""
    nickname = creator["nickname"]
    style_en = creator["style_en"]

    subject = f"Collaboration Opportunity — {BRAND_NAME} x {nickname}"

    body = f"""Hi {nickname},

I came across your TikTok and love your {style_en} content — it's exactly the kind of authentic, creative work we've been looking for!

I'm reaching out on behalf of {BRAND_NAME}, a brand specializing in designer toys and blind box collectibles. We'd love to explore a collaboration with you.

Here's what we have in mind:
- Send you some of our latest products to feature in your content
- Paid partnership opportunities for dedicated posts
- Long-term ambassador program (if it's a great fit!)

Would you be open to a quick chat? Feel free to reply to this email or reach out at {REPLY_EMAIL}.

Looking forward to connecting!

Best,
{SENDER_NAME}
{BRAND_NAME} | Creator Partnerships"""

    return subject, body


def run_email_campaign(min_followers=0, max_followers=float("inf"), min_avg_plays=0, dry_run=False):
    """执行邮件发送任务"""
    from gmail_checker import get_gmail_service
    from creator_tracker import get_sheet

    try:
        sheet = get_sheet()
    except Exception as e:
        print(f"[邮件] 连接 Google Sheet 失败: {e}")
        return

    try:
        gmail_service = get_gmail_service()
    except Exception as e:
        print(f"[邮件] Gmail 连接失败: {e}")
        return

    creators = get_eligible_creators(sheet, min_followers, max_followers, min_avg_plays)

    if not creators:
        print(f"[邮件] 没有符合条件的博主")
        print(f"       筛选条件：粉丝 {min_followers}~{int(max_followers) if max_followers != float('inf') else '不限'}，近月均播 ≥ {min_avg_plays}")
        return

    print(f"\n[邮件] 符合条件的博主共 {len(creators)} 位：")
    for c in creators:
        print(f"  {c['username']}  粉丝：{c['followers']}  均播：{c['avg_plays']}  邮箱：{c['email']}")

    if dry_run:
        print(f"\n[邮件] dry-run 模式，不实际发送。以下为示例邮件：\n")
        subject, body = build_email(creators[0])
        print(f"收件人：{creators[0]['email']}")
        print(f"主题：{subject}")
        print("-" * 40)
        print(body)
        return

    sent = 0
    for c in creators:
        subject, body = build_email(c)
        try:
            message = MIMEMultipart()
            message["to"] = c["email"]
            message["subject"] = subject
            message.attach(MIMEText(body, "plain"))
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            gmail_service.users().messages().send(userId="me", body={"raw": raw}).execute()
            sheet.update_cell(c["row"], 14, "已发送")
            sent += 1
            print(f"[邮件] ✓ {c['username']} ({c['email']})")
        except Exception as e:
            print(f"[邮件] ✗ {c['username']} 发送失败: {e}")

    print(f"\n[邮件] 本次共发送 {sent} 封，表格触达状态已更新")
