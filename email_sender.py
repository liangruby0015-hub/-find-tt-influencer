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

        avg_plays_raw = row[11].strip()
        if not avg_plays_raw:
            continue  # 跳过近月均播为空的博主（近期活跃度未知）

        followers = parse_number(row[2])
        avg_plays = parse_number(avg_plays_raw)

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


TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), "email_template.txt")


def load_template() -> tuple[str, str]:
    """加载邮件模板，返回 (subject, body)"""
    if not os.path.exists(TEMPLATE_FILE):
        raise FileNotFoundError(f"未找到邮件模板文件：{TEMPLATE_FILE}")
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
    lines = content.splitlines()
    subject = ""
    body_lines = []
    for i, line in enumerate(lines):
        if line.startswith("subject:"):
            subject = line[len("subject:"):].strip()
        elif i > 0:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return subject, body


def build_email(creator: dict) -> tuple[str, str]:
    """将模板变量替换为博主实际信息"""
    subject_tpl, body_tpl = load_template()
    variables = {
        "{{name}}": creator["nickname"],
        "{{style}}": creator["style_en"],
        "{{brand}}": BRAND_NAME,
        "{{reply_email}}": REPLY_EMAIL,
        "{{sender_name}}": SENDER_NAME,
        "{{followers}}": creator["followers"],
        "{{avg_plays}}": creator["avg_plays"],
        "{{username}}": creator["username"],
    }
    subject = subject_tpl
    body = body_tpl
    for key, val in variables.items():
        subject = subject.replace(key, str(val))
        body = body.replace(key, str(val))
    return subject, body


def send_test_email(to: str):
    """发送测试邮件到指定地址"""
    if not SMTP_ACCOUNTS:
        print("[邮件] 未配置 SMTP_USER 或 SMTP_PASSWORD，跳过")
        return

    test_creator = {
        "username": "@test_creator",
        "nickname": "Test Creator",
        "followers": "1.0万",
        "avg_plays": "5000",
        "style_en": "unboxing and review",
        "email": to,
    }
    subject, body = build_email(test_creator)
    smtp_user, smtp_password = SMTP_ACCOUNTS[0]

    try:
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
            server.starttls()
        server.login(smtp_user, smtp_password)

        msg = MIMEMultipart()
        msg["From"] = f"{SENDER_NAME} <{smtp_user}>"
        msg["To"] = to
        msg["Subject"] = f"[测试] {subject}"
        msg.attach(MIMEText(body, "plain"))
        server.sendmail(smtp_user, to, msg.as_string())
        server.quit()
        print(f"[邮件] 测试邮件已发送至 {to}")
    except smtplib.SMTPAuthenticationError:
        print("[邮件] SMTP 认证失败，请检查账号和密码")
    except Exception as e:
        print(f"[邮件] 发送失败: {e}")


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
