import feedparser
import requests
import os
import json
import time
from datetime import datetime, timedelta
from time import mktime

# --- 1. 基础配置 ---
# 监控对象
BASIC_KEYWORDS = ['"Bio-Thera Solutions"', '"百奥泰"', '"688177"', 'Bio-Thera']

# 时间限制：改为 365 天 (1年)
DAYS_LIMIT = 365

# --- 2. 智能分类词库 ---

# A类：临床与研发 (最核心)
CLINICAL_KEYWORDS = [
    "Clinical", "Trial", "Phase 1", "Phase 2", "Phase 3", "Phase I", "Phase II", "Phase III",
    "FDA", "NMPA", "EMA", "IND", "NDA", "BLA", "Approved", "Approval", "Study", "Endpoint",
    "R&D", "Pipeline", "Biosimilar", "Met primary endpoint",
    "临床", "试验", "一期", "二期", "三期", "获批", "受理", "药监局", 
    "数据", "终点", "入组", "首例", "研发", "管线", "生物类似药"
]

# B类：商业化、销售与合作伙伴 (你特别关心的)
# 包含主要合作伙伴：Organon, Hikma, Biogen, Sandoz, Cipla, Intas 等
COMMERCIAL_KEYWORDS = [
    "Sales", "Revenue", "Commercial", "Commercialization", "Launch", "Market", 
    "Agreement", "Partnership", "License", "Milestone", "Royalty", "Earnings", "Financial",
    "Organon", "Hikma", "Biogen", "Sandoz", "Cipla", "Intas", "Pharmapark", "SteinCares",
    "Tocilizumab", "Ustekinumab", "Avzivi", "Tofidence", "Pobevcy",  "Gedeon", "Stada", "Steincares",# 核心药物名
    "销售", "营收", "商业化", "上市", "市场", "合作", "协议", "授权", 
    "里程碑", "首付", "特许权", "财报", "业绩", "欧加隆", "百健", "山德士"，"山德士",
    "BAT1406","BAT2094","BAT5906","BAT4406F","BAT1706","BAT1806","BAT2206","BAT2306","BAT2406","BAT2506","BAT2606",
]

BARK_KEY = os.environ.get("BARK_KEY")
HISTORY_FILE = "history.json"

def get_google_news():
    """获取 Google News RSS 数据"""
    base_query = " OR ".join(BASIC_KEYWORDS)
    # 扩大搜索时间范围到 1 年 (when:1y)
    query = f"({base_query}) when:1y"
    
    encoded_query = requests.utils.quote(query)
    # hl=en-US&gl=US 确保能搜到海外合作伙伴(Hikma/Organon)发布的英文通稿
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    
    print(f"正在抓取 RSS (过去1年): {rss_url}")
    return feedparser.parse(rss_url)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    # 因为时间跨度大，保留最近 200 条记录防止重复
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-200:], f, ensure_ascii=False, indent=2)

def classify_news(title):
    """智能判断新闻类别"""
    title_lower = title.lower()
    
    # 优先判断临床 (通常临床消息对股价影响最直接)
    for kw in CLINICAL_KEYWORDS:
        if kw.lower() in title_lower:
            return "clinical"
            
    # 其次判断商业/合作
    for kw in COMMERCIAL_KEYWORDS:
        if kw.lower() in title_lower:
            return "commercial"
            
    return "general"

def send_bark(title, url, date_str, news_type):
    """根据新闻类别发送不同样式的通知"""
    if not BARK_KEY:
        return
    
    base_url = f"https://api.day.app/{BARK_KEY}/"
    
    # --- 视觉与声音区分 ---
    if news_type == "clinical":
        header = "🧬 百奥泰临床进展"
        body = f"**[研发重磅]** {title}\n{date_str}"
        group = "BioThera-Clinical"
        sound = "glass" # 清脆提示音
        icon = "https://cdn-icons-png.flaticon.com/512/2965/2965536.png" # DNA图标
        
    elif news_type == "commercial":
        header = "💰 百奥泰商业动态"
        body = f"**[合作/销售]** {title}\n{date_str}"
        group = "BioThera-Commercial"
        sound = "chime" # 悦耳提示音
        icon = "https://cdn-icons-png.flaticon.com/512/2454/2454282.png" # 钱袋/握手图标
        
    else:
        header = "📰 百奥泰日常资讯"
        body = f"{title}\n{date_str}"
        group = "BioThera-General"
        sound = "minuet" # 低调提示音
        icon = "https://www.bio-thera.com/favicon.ico"

    print(f"正在推送 [{news_type}]: {title}")
    
    try:
        requests.post(base_url, data={
            "title": header,
            "body": body,
            "url": url,
            "group": group,
            "level": "active", # 均为主动提醒
            "sound": sound,
            "icon": icon
        })
    except Exception as e:
        print(f"推送失败: {e}")

def main():
    feed = get_google_news()
    history = load_history()
    seen_links = {item['link'] for item in history}
    
    new_items = []
    cutoff_date = datetime.now() - timedelta(days=DAYS_LIMIT)
    print(f"过滤时间截止线: {cutoff_date.strftime('%Y-%m-%d')}")

    # 倒序处理，确保旧新闻先入库
    for entry in feed.entries[::-1]:
        link = entry.link
        title = entry.title
        
        # 时间解析
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            pub_dt = datetime.fromtimestamp(mktime(entry.published_parsed))
        else:
            pub_dt = datetime.now()

        # 严格的时间过滤
        if pub_dt < cutoff_date:
            continue

        if link not in seen_links:
            # 分类
            news_type = classify_news(title)
            
            # 推送
            send_bark(title, link, entry.published, news_type)
            
            new_items.append({
                "title": title, 
                "link": link, 
                "date": entry.published,
                "type": news_type
            })
            seen_links.add(link)
            # 稍微停顿，避免瞬时请求过多
            time.sleep(1)
    
    if new_items:
        history.extend(new_items)
        save_history(history)
        print(f"处理完成，新增 {len(new_items)} 条。")
    else:
        print("暂无新消息。")

if __name__ == "__main__":
    main()
