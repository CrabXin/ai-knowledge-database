"""定时采集模块（实训其他功能2）。

使用 APScheduler 实现"每日凌晨自动采集前一天的数据"。
采集任务在后台线程执行，不阻塞 Web 服务。
"""
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

import config
import crawler
import storage

_scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
# 手动采集用的线程引用，避免重复并发
_manual_thread = None


def _scheduled_job():
    """每日凌晨执行：采集数据并标记为前一天的日期。"""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    crawler.crawl(
        keyword=config.DEFAULT_KEYWORD,
        pages=config.DEFAULT_PAGES,
        crawl_date=yesterday,
    )


def start_scheduler():
    """启动定时器：每天 02:00 自动采集前一天数据。"""
    if not _scheduler.running:
        _scheduler.add_job(_scheduled_job, "cron", hour=2, minute=0, id="daily_crawl",
                           replace_existing=True)
        _scheduler.start()


def run_crawl_async(keyword, pages, delay, enrich, crawl_date=None) -> bool:
    """在后台线程发起一次手动采集；若已有采集在运行则返回 False。"""
    global _manual_thread
    status = storage.read_status()
    if status.get("running"):
        return False
    if _manual_thread and _manual_thread.is_alive():
        return False

    _manual_thread = threading.Thread(
        target=crawler.crawl,
        kwargs=dict(keyword=keyword, pages=pages, delay=delay,
                    enrich=enrich, crawl_date=crawl_date),
        daemon=True,
    )
    _manual_thread.start()
    return True
