import feedparser
import requests
import os
import json
import time
from datetime import datetime, timedelta
from time import mktime

# --- 配置 ---
# 关键词逻辑：同时监控中文名、英文名、股票代码
KEYWORDS = ['"Bio-Thera Solutions"', '"百奥泰"', '"688177"', 'Bio-Thera']
# Bark 推送接口
BARK_KEY = os.environ.get("BARK_KEY")
# 记录已读新闻的文件
HISTORY_FILE = "history.json"
# 时间限制：只看最近多少天
DAYS_LIMIT = 90

def get_google_news():
    """获取 Google News RSS 数据"""
    # 构造查询语句
    # 在查询中加入 when:90d 指令，让 Google 优先返回最近90天的结果
    base_query = " OR ".join(KEYWORDS)
    query = f"({base_query}) when:{DAYS_LIMIT}d"
    
    encoded_query = requests.utils.quote(query)
    # hl=en-US&gl=US 代表全球视角 (也可以改成 hl=zh-CN&gl=CN 看中文优先)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    
    print(f"正在抓取 RSS (限制最近{DAYS_LIMIT}天): {rss_url}")
    return feedparser.parse(rss_url)

def load_history():
    """读取历史记录"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    """保存最新的 100 条记录"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-100:], f, ensure_ascii=False, indent=2)

def send_bark(title, url, date_str):
    """发送 Bark 通知"""
    if not BARK_KEY:
        print("未配置 BARK_KEY，跳过推送")
        return
    
    print(f"正在推送: {title}")
    base_url = f"https://api.day.app/{BARK_KEY}/"
    header = "百奥泰新动态"
    body = f"{title}\n{date_str}"
    
    try:
        requests.post(base_url, data={
            "title": header,
            "body": body,
            "url": url,
            "group": "BioThera",
            "icon": "https://www.bio-thera.com/favicon.ico"
        })
    except Exception as e:
        print(f"推送失败: {e}")

def main():
    feed = get_google_news()
    history = load_history()
    seen_links = {item['link'] for item in history}
    
    new_items = []
    
    # 计算截止日期 (当前时间 - 90天)
    cutoff_date = datetime.now() - timedelta(days=DAYS_LIMIT)
    print(f"过滤时间截止线: {cutoff_date.strftime('%Y-%m-%d')}")

    # 倒序遍历，确保处理顺序
    for entry in feed.entries[::-1]:
        link = entry.link
        title = entry.title
        
        # --- 核心修改：时间过滤逻辑 ---
        # feedparser 会将时间解析为 struct_time，我们需要转为 datetime 对象进行比较
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            pub_dt = datetime.fromtimestamp(mktime(entry.published_parsed))
        else:
            # 如果没有时间信息，为了安全起见，默认视为符合条件（或者你可以选择跳过）
            pub_dt = datetime.now()

        # 如果新闻发布时间 早于 截止时间，直接跳过
        if pub_dt < cutoff_date:
            # print(f"跳过旧新闻 ({pub_dt}): {title}") # 调试用
            continue
        # ---------------------------

        if link not in seen_links:
            print(f"发现新内容 ({pub_dt.strftime('%Y-%m-%d')}): {title}")
            send_bark(title, link, entry.published)
            
            new_items.append({
                "title": title, 
                "link": link, 
                "date": entry.published
            })
            seen_links.add(link)
            time.sleep(1)
    
    if new_items:
        history.extend(new_items)
        save_history(history)
        print(f"成功推送并记录了 {len(new_items)} 条新新闻。")
    else:
        print("暂无符合条件的新消息。")

if __name__ == "__main__":
    main()
