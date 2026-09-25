import os, json, hashlib, html
from pathlib import Path
from datetime import datetime, timezone
import feedparser, requests

TOKEN=os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL=os.environ.get("TELEGRAM_CHANNEL","@iranuknews")
STATE=Path("seen.json")

FEEDS=[
 ("GOV.UK","https://www.gov.uk/search/news-and-communications.atom?keywords=Iran"),
 ("UK Parliament","https://committees.parliament.uk/rss/"),
 ("BBC","https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
]
UK_TERMS=("uk","britain","british","united kingdom","london","foreign office","fcdo","home office","parliament","starmer","lammy","government")
IRAN_TERMS=("iran","iranian","tehran","irgc","persian gulf")

def relevant(title,summary):
    t=(title+" "+summary).lower()
    return any(x in t for x in IRAN_TERMS) and any(x in t for x in UK_TERMS)

def load_seen():
    try:return set(json.loads(STATE.read_text()))
    except:return set()

def save_seen(s): STATE.write_text(json.dumps(list(s)[-2000:]))

def send(item,source):
    title=html.escape(item.get("title","").strip())
    link=item.get("link","")
    stamp=datetime.now(timezone.utc).strftime("%d %b %Y | %H:%M UTC")
    text=f"🇬🇧🇮🇷 <b>{title}</b>\n\nمنبع: {html.escape(source)}\n🕒 {stamp}\n🔗 <a href=\"{html.escape(link)}\">مشاهده خبر اصلی</a>\n\n@iranuknews"
    r=requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",json={"chat_id":CHANNEL,"text":text,"parse_mode":"HTML","disable_web_page_preview":False},timeout=20)
    r.raise_for_status()

def main():
    if not TOKEN: raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
    seen=load_seen(); changed=False
    for source,url in FEEDS:
        feed=feedparser.parse(url)
        for item in feed.entries[:30]:
            title=item.get("title",""); summary=item.get("summary","")
            if not relevant(title,summary): continue
            key=hashlib.sha256((item.get("link","")+title).encode()).hexdigest()
            if key in seen: continue
            send(item,source); seen.add(key); changed=True
    if changed: save_seen(seen)

if __name__=="__main__": main()
