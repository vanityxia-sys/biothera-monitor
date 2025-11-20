import feedparser
import requests
import os
import json
import time
from datetime import datetime, timedelta

# --- 配置 ---
# 关键词逻辑：同时监控中文名、英文名、股票代码
KEYWORDS = ['"Bio-Thera Solutions"', '"百奥泰"', '"688177"', 'Bio-Thera']
# Bark 推送接口
BARK_KEY = os.environ.get("BARK_KEY")
# 记录已读新闻的文件
HISTORY_FILE = "history.json"

def get_google_news():
    """获取 Google News RSS 数据"""
    # 构造查询语句，使用 OR 连接关键词
    query = " OR ".join(KEYWORDS)
    # 搜索全球新闻，hl=en-US 代表优先英文，gl=US 代表全球视角(也可以改为CN)
    # 为了覆盖全，我们可以不限制语言，依靠关键词匹配
    encoded_query = requests.utils.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    
    print(f"正在抓取 RSS: {rss_url}")
    return feedparser.parse(rss_url)

def load_history():
    """读取历史记录，防止重复推送"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    """保存最新的 100 条记录"""
    # 只保留最近 100 条，避免文件无限膨胀
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-100:], f, ensure_ascii=False, indent=2)

def send_bark(title, url, date):
    """发送 Bark 通知"""
    if not BARK_KEY:
        print("未配置 BARK_KEY，跳过推送")
        return
    
    # Bark URL 格式: https://api.day.app/{key}/{title}/{body}?url={url}
    # 标题和内容需要 URL 编码
    print(f"正在推送: {title}")
    
    base_url = f"https://api.day.app/{BARK_KEY}/"
    header = "百奥泰新动态"
    body = f"{title}\n{date}"
    
    # 发送请求
    try:
        # 使用 post 可以支持更长内容
        requests.post(base_url, data={
            "title": header,
            "body": body,
            "url": url,
            "group": "BioThera", # 消息分组
            "icon": "https://www.bio-thera.com/favicon.ico" # 尝试使用官网图标
        })
    except Exception as e:
        print(f"推送失败: {e}")

def main():
    feed = get_google_news()
    history = load_history()
    # 提取历史记录中的链接集合，方便比对
    seen_links = {item['link'] for item in history}
    
    new_items = []
    
    # 倒序遍历，确保老的新闻先被处理（如果都是新的）
    for entry in feed.entries[::-1]:
        link = entry.link
        title = entry.title
        published = entry.published
        
        if link not in seen_links:
            # 发现新新闻
            print(f"发现新内容: {title}")
            send_bark(title, link, published)
            
            # 记录下来
            new_items.append({"title": title, "link": link, "date": published})
            seen_links.add(link)
            
            # Bark 也就是每秒 5-10 次的限制，稍微停顿一下防止被封
            time.sleep(1)
    
    if new_items:
        # 更新历史记录
        history.extend(new_items)
        save_history(history)
        print(f"成功推送并记录了 {len(new_items)} 条新新闻。")
    else:
        print("暂无新消息。")

if __name__ == "__main__":
    main()
