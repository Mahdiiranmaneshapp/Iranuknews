import os, json, hashlib, html, re
from pathlib import Path
from datetime import datetime, timezone, timedelta
import feedparser, requests

TOKEN=os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY=os.environ.get("OPENAI_API_KEY")
CHANNEL=os.environ.get("TELEGRAM_CHANNEL","@iranuknews")
STATE=Path("seen.json")
DAILY_LIMIT=15
RUN_LIMIT=3

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

def load_state():
    try:
        raw=json.loads(STATE.read_text())
        if isinstance(raw,list):
            return {"seen":raw,"posts":[]}
        return {"seen":raw.get("seen",[]),"posts":raw.get("posts",[])}
    except:
        return {"seen":[],"posts":[]}

def save_state(state):
    STATE.write_text(json.dumps({"seen":state["seen"][-2000:],"posts":state["posts"][-200:]},ensure_ascii=False))

def clean_text(s):
    return re.sub(r"<[^>]+>"," ",s or "").replace("&nbsp;"," ").strip()

def translate_and_summarise(title,summary):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    prompt=(
      "You are preparing a neutral Persian-language news channel about UK-Iran relations. "
      "Do not add opinions, predictions, persuasion, or facts not present in the supplied text. "
      "Return valid JSON only with keys fa_title and fa_summary. "
      "fa_title: accurate natural Persian translation of the headline. "
      "fa_summary: 2-3 concise Persian sentences summarising only the supplied information.\n\n"
      f"TITLE: {title}\nSUMMARY: {clean_text(summary)[:3000]}"
    )
    r=requests.post("https://api.openai.com/v1/responses",
      headers={"Authorization":f"Bearer {OPENAI_API_KEY}","Content-Type":"application/json"},
      json={"model":"gpt-5.6-luna","input":prompt,"max_output_tokens":350},
      timeout=45)
    r.raise_for_status()
    data=r.json()
    text=data.get("output_text","")
    if not text:
        parts=[]
        for out in data.get("output",[]):
            for c in out.get("content",[]):
                if c.get("type")=="output_text": parts.append(c.get("text",""))
        text="".join(parts)
    text=text.strip()
    if text.startswith("```"):
        text=re.sub(r"^```(?:json)?\s*|\s*```$","",text,flags=re.I)
    return json.loads(text)

def send(item,source):
    en_title=item.get("title","").strip()
    tr=translate_and_summarise(en_title,item.get("summary",""))
    link=item.get("link","")
    stamp=datetime.now(timezone.utc).strftime("%d %b %Y | %H:%M UTC")
    text=(
      f"🇬🇧 <b>{html.escape(en_title)}</b>\n\n"
      f"🇮🇷 <b>{html.escape(tr['fa_title'])}</b>\n"
      f"{html.escape(tr['fa_summary'])}\n\n"
      f"منبع: {html.escape(source)}\n"
      f"🕒 {stamp}\n"
      f"🔗 <a href=\"{html.escape(link)}\">مشاهده خبر اصلی</a>\n\n"
      "@iranuknews"
    )
    r=requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
      json={"chat_id":CHANNEL,"text":text,"parse_mode":"HTML","disable_web_page_preview":False},timeout=20)
    r.raise_for_status()

def main():
    if not TOKEN: raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
    state=load_state()
    seen=set(state["seen"])
    now=datetime.now(timezone.utc)
    cutoff=now-timedelta(hours=24)
    recent=[]
    for x in state["posts"]:
        try:
            if datetime.fromisoformat(x)>cutoff: recent.append(x)
        except: pass
    allowance=max(0,min(RUN_LIMIT,DAILY_LIMIT-len(recent)))
    if allowance==0:
        state["posts"]=recent; save_state(state); return

    sent=0
    for source,url in FEEDS:
        feed=feedparser.parse(url)
        for item in feed.entries[:30]:
            if sent>=allowance: break
            title=item.get("title",""); summary=item.get("summary","")
            if not relevant(title,summary): continue
            key=hashlib.sha256((item.get("link","")+title).encode()).hexdigest()
            if key in seen: continue
            send(item,source)
            seen.add(key); recent.append(now.isoformat()); sent+=1
        if sent>=allowance: break

    state["seen"]=list(seen); state["posts"]=recent
    save_state(state)

if __name__=="__main__": main()
