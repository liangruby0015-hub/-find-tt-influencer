import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "gmail_credentials.json")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "gmail_token.json")


def get_gmail_service():
    """获取 Gmail API 服务（首次运行会打开浏览器授权）"""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"未找到 Gmail OAuth 凭证文件：{CREDENTIALS_FILE}\n"
                    "请前往 Google Cloud Console 创建 OAuth2 桌面端凭证并下载为 gmail_credentials.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def check_email_sent(service, email: str) -> bool:
    """检查是否向该邮箱发送过邮件"""
    try:
        result = service.users().messages().list(
            userId="me",
            q=f"in:sent to:{email}",
            maxResults=1,
        ).execute()
        return result.get("resultSizeEstimate", 0) > 0
    except Exception as e:
        print(f"[Gmail] 查询 {email} 失败: {e}")
        return False
