import os
import time
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# 支持多账号，逗号分隔
_smtp_users = [u.strip() for u in os.getenv("SMTP_USER", "").split(",") if u.strip()]
_smtp_passwords = [p.strip() for p in os.getenv("SMTP_PASSWORD", "").split(",") if p.strip()]
SMTP_ACCOUNTS = list(zip(_smtp_users, _smtp_passwords))  # [(user, password), ...]

SENDER_NAME = os.getenv("SENDER_NAME", "Brand Partnerships")
BRAND_NAME = os.getenv("BRAND_NAME", "Our Brand")
REPLY_EMAIL = os.getenv("REPLY_EMAIL", "")

DAILY_SEND_LIMIT = 500   # 每个账号每日上限
DELAY_MIN = 2             # 每封最小间隔（秒）
DELAY_MAX = 5             # 每封最大间隔（秒）

STYLE_MAP = {
    "开箱测评": "unboxing and review",
    "收藏展示": "collection showcase",
    "购物分享": "shopping haul",
    "创意二创": "creative DIY",
    "日常Vlog": "lifestyle vlog",
    "潮玩内容": "designer toy",
}


def parse_number(s: str) -> int:
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

        style_en = " & ".join(
            STYLE_MAP.get(s.strip(), "designer toy")
            for s in row[12].split("/") if s.strip()
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
    from creator_tracker import get_sheet

    if not SMTP_ACCOUNTS:
        print("[邮件] 未配置 SMTP_USER 或 SMTP_PASSWORD，跳过")
        return

    try:
        sheet = get_sheet()
    except Exception as e:
        print(f"[邮件] 连接 Google Sheet 失败: {e}")
        return

    creators = get_eligible_creators(sheet, min_followers, max_followers, min_avg_plays)

    if not creators:
        print(f"[邮件] 没有符合条件的博主")
        print(f"       筛选条件：粉丝 {min_followers}~{int(max_followers) if max_followers != float('inf') else '不限'}，近月均播 ≥ {min_avg_plays}")
        return

    # 多账号总容量
    total_capacity = DAILY_SEND_LIMIT * len(SMTP_ACCOUNTS)
    send_count = min(len(creators), total_capacity)
    print(f"\n[邮件] 符合条件的博主共 {len(creators)} 位，本次发送 {send_count} 封")
    print(f"       可用账号 {len(SMTP_ACCOUNTS)} 个，总容量 {total_capacity} 封/天")
    for c in creators[:send_count]:
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
    account_idx = 0
    account_sent = 0  # 当前账号已发送数

    try:
        smtp_user, smtp_password = SMTP_ACCOUNTS[account_idx]
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(smtp_user, smtp_password)
        print(f"[邮件] 使用账号：{smtp_user}")

        for c in creators[:send_count]:
            # 当前账号达到上限，切换下一个
            if account_sent >= DAILY_SEND_LIMIT:
                account_idx += 1
                if account_idx >= len(SMTP_ACCOUNTS):
                    print("[邮件] 所有账号已达今日上限，停止发送")
                    break
                server.quit()
                smtp_user, smtp_password = SMTP_ACCOUNTS[account_idx]
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
                server.starttls()
                server.login(smtp_user, smtp_password)
                account_sent = 0
                print(f"[邮件] 切换账号：{smtp_user}")

            subject, body = build_email(c)
            msg = MIMEMultipart()
            msg["From"] = f"{SENDER_NAME} <{smtp_user}>"
            msg["To"] = c["email"]
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            try:
                server.sendmail(smtp_user, c["email"], msg.as_string())
                sheet.update_cell(c["row"], 14, "已发送")
                sent += 1
                account_sent += 1
                print(f"[邮件] ✓ {c['username']} ({c['email']})  [{smtp_user}]")
            except Exception as e:
                print(f"[邮件] ✗ {c['username']} 发送失败: {e}")

            if sent < send_count:
                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        server.quit()
    except smtplib.SMTPAuthenticationError:
        print(f"[邮件] SMTP 认证失败，请检查账号和应用专用密码")
        return
    except Exception as e:
        print(f"[邮件] SMTP 连接失败: {e}")
        return

    print(f"\n[邮件] 本次共发送 {sent} 封，表格触达状态已更新")
