import feedparser
import requests
import os
import json
import time
from datetime import datetime, timedelta
from time import mktime

# --- 基础配置 ---
# 1. 搜索范围：公司名 + 股票代码
# 我们保持搜索范围宽泛，确保不漏掉任何信息，然后在代码里做分类
BASIC_KEYWORDS = ['"Bio-Thera Solutions"', '"百奥泰"', '"688177"', 'Bio-Thera']

# 2. 临床/重磅 关键词库 (命中这些词的新闻会被高亮标记)
# 涵盖：临床各阶段、药监局审批、核心产品获批、新药申请等
CLINICAL_KEYWORDS = [
    "Clinical", "Trial", "Phase 1", "Phase I", "Phase 2", "Phase II", "Phase 3", "Phase III",
    "FDA", "NMPA", "EMA", "IND", "NDA", "BLA", "Biosimilar", "Approved", "Approval",
    "Study", "Results", "Endpoint", "Recruitment",
    "临床", "试验", "一期", "二期", "三期", "获批", "受理", "上市", 
    "申请", "药监局", "数据", "终点", "入组", "首例", "给药"
]

BARK_KEY = os.environ.get("BARK_KEY")
HISTORY_FILE = "history.json"
DAYS_LIMIT = 90  # 只看最近90天

def get_google_news():
    """获取 Google News RSS 数据"""
    # 构造查询语句
    base_query = " OR ".join(BASIC_KEYWORDS)
    # 增加 when:90d 限制
    query = f"({base_query}) when:{DAYS_LIMIT}d"
    
    encoded_query = requests.utils.quote(query)
    # hl=en-US&gl=US 保证全球视野 (涵盖FDA消息)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    
    print(f"正在抓取 RSS: {rss_url}")
    return feedparser.parse(rss_url)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-100:], f, ensure_ascii=False, indent=2)

def check_if_clinical(title):
    """检查标题是否包含临床关键词"""
    for kw in CLINICAL_KEYWORDS:
        # 不区分大小写
        if kw.lower() in title.lower():
            return True
    return False

def send_bark(title, url, date_str, is_clinical):
    """发送 Bark 通知，区分临床和普通新闻"""
    if not BARK_KEY:
        return
    
    base_url = f"https://api.day.app/{BARK_KEY}/"
    
    # --- 视觉区分逻辑 ---
    if is_clinical:
        # 临床新闻：使用 DNA 图标，标题加粗加红(Bark支持部分Markdown)
        header = "🧬 百奥泰临床进展!"
        body = f"**[重磅]** {title}\n{date_str}"
        group = "BioThera-Clinical" # 手机上会单独分组
        level = "active" # 设置为时效性消息
        sound = "glass" # 不同的提示音
    else:
        # 普通新闻
        header = "📰 百奥泰新动态"
        body = f"{title}\n{date_str}"
        group = "BioThera-General"
        level = "timeSensitive"
        sound = "minuet"

    print(f"正在推送 ({'临床' if is_clinical else '普通'}): {title}")
    
    try:
        requests.post(base_url, data={
            "title": header,
            "body": body,
            "url": url,
            "group": group,
            "level": level,
            "sound": sound,
            "icon": "https://www.bio-thera.com/favicon.ico"
        })
    except Exception as e:
        print(f"推送失败: {e}")

def main():
    feed = get_google_news()
    history = load_history()
    seen_links = {item['link'] for item in history}
    
    new_items = []
    cutoff_date = datetime.now() - timedelta(days=DAYS_LIMIT)

    # 倒序处理
    for entry in feed.entries[::-1]:
        link = entry.link
        title = entry.title
        
        # 时间过滤
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            pub_dt = datetime.fromtimestamp(mktime(entry.published_parsed))
        else:
            pub_dt = datetime.now()

        if pub_dt < cutoff_date:
            continue

        if link not in seen_links:
            # 核心步骤：判断是否为临床新闻
            is_clinical_news = check_if_clinical(title)
            
            send_bark(title, link, entry.published, is_clinical_news)
            
            new_items.append({
                "title": title, 
                "link": link, 
                "date": entry.published,
                "tag": "clinical" if is_clinical_news else "general"
            })
            seen_links.add(link)
            time.sleep(1)
    
    if new_items:
        history.extend(new_items)
        save_history(history)
        print(f"处理完成，新增 {len(new_items)} 条。")
    else:
        print("暂无新消息。")

if __name__ == "__main__":
    main()
