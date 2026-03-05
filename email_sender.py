import os
import time
import random
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SENDER_NAME = os.getenv("SENDER_NAME", "Brand Partnerships")
BRAND_NAME = os.getenv("BRAND_NAME", "Our Brand")
REPLY_EMAIL = os.getenv("REPLY_EMAIL", "")

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


def _build_raw_message(to: str, subject: str, body: str) -> str:
    msg = MIMEMultipart()
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def send_test_email(to: str):
    """发送测试邮件到指定地址"""
    from gmail_checker import get_gmail_service

    test_creator = {
        "username": "@test_creator",
        "nickname": "Test Creator",
        "followers": "1.0万",
        "avg_plays": "5000",
        "style_en": "unboxing and review",
        "email": to,
    }
    subject, body = build_email(test_creator)

    try:
        service = get_gmail_service()
        raw = _build_raw_message(to, f"[测试] {subject}", body)
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"[邮件] 测试邮件已发送至 {to}")
    except Exception as e:
        print(f"[邮件] 发送失败: {e}")


def run_email_campaign(min_followers=0, max_followers=float("inf"), min_avg_plays=0, dry_run=False):
    from creator_tracker import get_sheet
    from gmail_checker import get_gmail_service

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

    print(f"\n[邮件] 符合条件的博主共 {len(creators)} 位，本次发送 {len(creators)} 封")
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

    try:
        service = get_gmail_service()
    except Exception as e:
        print(f"[邮件] Gmail API 连接失败: {e}")
        return

    sent = 0
    for c in creators:
        subject, body = build_email(c)
        raw = _build_raw_message(c["email"], subject, body)
        try:
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
            sheet.update_cell(c["row"], 14, "已发送")
            sent += 1
            print(f"[邮件] ✓ {c['username']} ({c['email']})")
        except Exception as e:
            print(f"[邮件] ✗ {c['username']} 发送失败: {e}")

        if sent < len(creators):
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print(f"\n[邮件] 本次共发送 {sent} 封，表格触达状态已更新")
