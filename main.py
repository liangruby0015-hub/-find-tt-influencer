import schedule
import time
from dotenv import load_dotenv

load_dotenv()

from tiktok_scraper import run_tiktok_scraper
from feishu_sender import send_feishu_report
from creator_tracker import sync_creators_to_sheet, update_contacted_status


def job_feishu():
    """抓取 TikTok 热门视频并推送飞书日报"""
    print("=" * 50)
    print("[飞书日报] 开始执行...")
    tiktok_data = run_tiktok_scraper(max_videos=5)
    print(f"  TikTok 视频: {len(tiktok_data.get('videos', []))} 条")
    send_feishu_report(tiktok_data)
    print("[飞书日报] 完成！")
    print("=" * 50)


def job_sync_creators():
    """抓取 TikTok 博主信息并同步到 Google Sheet"""
    print("=" * 50)
    print("[博主同步] 开始执行...")
    tiktok_data = run_tiktok_scraper(max_videos=50)
    print(f"  TikTok 视频: {len(tiktok_data.get('videos', []))} 条")
    sync_creators_to_sheet(tiktok_data.get("videos", []))
    print("[博主同步] 完成！")
    print("=" * 50)


def job_check_contacted():
    """比对 Gmail 已发送邮件，更新博主触达状态"""
    print("=" * 50)
    print("[触达更新] 开始执行...")
    update_contacted_status()
    print("=" * 50)


if __name__ == "__main__":
    import sys

    if "--feishu" in sys.argv or "--now" in sys.argv:
        job_feishu()
    elif "--sync-creators" in sys.argv:
        job_sync_creators()
    elif "--check-contacted" in sys.argv:
        dry_run = "--dry-run" in sys.argv
        update_contacted_status(dry_run=dry_run)
    else:
        # 定时模式：飞书日报 09:00 / 博主同步每 4 小时 / 触达状态每天 20:00
        schedule.every().day.at("09:00").do(job_feishu)
        schedule.every(4).hours.do(job_sync_creators)
        schedule.every().day.at("20:00").do(job_check_contacted)
        print("Bot 已启动：飞书日报 09:00 / 博主同步每 4 小时 / 触达更新 20:00。按 Ctrl+C 停止。")
        while True:
            schedule.run_pending()
            time.sleep(60)
