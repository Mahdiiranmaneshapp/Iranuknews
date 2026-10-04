import os, json, hashlib, html, re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus
import feedparser, requests

TOKEN=os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY=os.environ.get("OPENAI_API_KEY")\nAI_ENABLED=False  # Paused by owner; do not call OpenAI until explicitly re-enabled.
CHANNEL=os.environ.get("TELEGRAM_CHANNEL","@iranuknews")
STATE=Path("seen.json")
DAILY_LIMIT=15
RUN_LIMIT=3

FEEDS=[
 ("GOV.UK","https://www.gov.uk/search/news-and-communications.atom?keywords=Iran"),
 ("UK Parliament","https://committees.parliament.uk/rss/"),
 ("BBC Middle East","https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
 ("BBC UK","https://feeds.bbci.co.uk/news/uk/rss.xml"),
 ("Google News UK-Iran","https://news.google.com/rss/search?q="+quote_plus('Iran (UK OR Britain OR British OR London) when:1d')+"&hl=en-GB&gl=GB&ceid=GB:en"),
]
UK_TERMS=("uk","u.k.","britain","british","united kingdom","london","england","scotland","wales",
          "foreign office","fcdo","home office","parliament","downing street","raf","fairford",
          "british government","prime minister")
IRAN_TERMS=("iran","iranian","tehran","irgc","iran-linked","iranian government")

def relevant(title,summary):
    t=clean_text(title+" "+summary).lower()
    return any(x in t for x in IRAN_TERMS) and any(x in t for x in UK_TERMS)

def load_state():
    try:
        raw=json.loads(STATE.read_text())
        if isinstance(raw,list): return {"seen":raw,"posts":[],"stories":[]}
        return {"seen":raw.get("seen",[]),"posts":raw.get("posts",[]),"stories":raw.get("stories",[])}
    except: return {"seen":[],"posts":[],"stories":[]}

def save_state(state):
    STATE.write_text(json.dumps({
        "seen":state["seen"][-2000:],
        "posts":state["posts"][-200:],
        "stories":state.get("stories",[])[-300:]
    },ensure_ascii=False))

def clean_text(s):
    return re.sub(r"<[^>]+>"," ",s or "").replace("&nbsp;"," ").strip()

GENERIC_STORY_WORDS={
    "the","a","an","to","of","in","on","for","over","and","or","with","from","as","at","by",
    "after","before","new","says","say","uk","u","k","britain","british","england","iran",
    "iranian","iranians","news","com","fr"
}

STORY_NORMALISE={
    "nationals":"people","national":"people","men":"people","man":"people",
    "charged":"charge","charges":"charge","charging":"charge",
    "plotting":"plot","planned":"plot","planning":"plot","plots":"plot",
    "terrorism":"terror","terrorist":"terror","terrorists":"terror",
    "jews":"jewish","community":"community",
    "attacks":"attack","attacking":"attack","targeting":"target","targeted":"target"
}

def story_words(title):
    # Google News commonly appends " - Publisher"; publisher must not affect matching.
    title=re.sub(r"\s+-\s+[^-]+$","",clean_text(title).lower())
    words=re.findall(r"[a-z0-9]+",title)
    out=set()
    for w in words:
        if w in GENERIC_STORY_WORDS or len(w)<3:
            continue
        out.add(STORY_NORMALISE.get(w,w))
    return out

def same_story(a,b):
    A,B=story_words(a),story_words(b)
    if not A or not B:
        return False
    common=len(A & B)
    smaller=min(len(A),len(B))
    union=len(A | B)
    # Conservative threshold: several matching facts are needed.
    return common >= 4 and (common/smaller >= 0.50 or common/union >= 0.40)

def translate_and_summarise(title,summary):
    if not OPENAI_API_KEY: raise RuntimeError("OPENAI_API_KEY is missing")
    prompt=(
      "You are preparing a neutral Persian-language news channel about UK-Iran relations. "
      "Do not add opinions, predictions, persuasion, or facts not present in the supplied text. "
      "Clearly attribute allegations, denials and disputed claims. "
      "Return valid JSON only with keys fa_title and fa_summary. "
      "fa_title: accurate natural Persian translation of the headline. "
      "fa_summary: 2-3 concise Persian sentences summarising only the supplied information.\n\n"
      f"TITLE: {title}\nSUMMARY: {clean_text(summary)[:3000]}"
    )
    r=requests.post("https://api.openai.com/v1/responses",
      headers={"Authorization":f"Bearer {OPENAI_API_KEY}","Content-Type":"application/json"},
      json={
        "model":"gpt-5.6-luna",
        "input":prompt,
        "max_output_tokens":700,
        "text":{"format":{
          "type":"json_schema",
          "name":"iranuknews_translation",
          "strict":True,
          "schema":{
            "type":"object",
            "properties":{
              "fa_title":{"type":"string"},
              "fa_summary":{"type":"string"}
            },
            "required":["fa_title","fa_summary"],
            "additionalProperties":False
          }
        }}
      },timeout=45)
    r.raise_for_status()
    data=r.json(); text=data.get("output_text","")
    if not text:
        parts=[]
        for out in data.get("output",[]):
            for c in out.get("content",[]):
                if c.get("type")=="output_text": parts.append(c.get("text",""))
        text="".join(parts)
    text=text.strip()
    if text.startswith("```"): text=re.sub(r"^```(?:json)?\s*|\s*```$","",text,flags=re.I)
    return json.loads(text)

def send(item,source):
    en_title=item.get("title","").strip()
    tr=translate_and_summarise(en_title,item.get("summary",""))
    link=item.get("link","")
    stamp=datetime.now(timezone.utc).strftime("%d %b %Y | %H:%M UTC")
    text=(f"🇬🇧 <b>{html.escape(en_title)}</b>\n\n"
          f"🇮🇷 <b>{html.escape(tr['fa_title'])}</b>\n{html.escape(tr['fa_summary'])}\n\n"
          f"منبع: {html.escape(source)}\n🕒 {stamp}\n"
          f"🔗 <a href=\"{html.escape(link)}\">مشاهده خبر اصلی</a>\n\n@iranuknews")
    r=requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
      json={"chat_id":CHANNEL,"text":text,"parse_mode":"HTML","disable_web_page_preview":False},timeout=20)
    r.raise_for_status()

def main():
    if not TOKEN: raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
    state=load_state(); seen=set(state["seen"]); now=datetime.now(timezone.utc); cutoff=now-timedelta(hours=24)
    story_cutoff=now-timedelta(hours=36)
    stories=[]
    for s in state.get("stories",[]):
        try:
            if datetime.fromisoformat(s["time"])>story_cutoff:
                stories.append(s)
        except:
            pass
    recent=[]
    for x in state["posts"]:
        try:
            if datetime.fromisoformat(x)>cutoff: recent.append(x)
        except: pass
    allowance=max(0,min(RUN_LIMIT,DAILY_LIMIT-len(recent)))
    if allowance==0:
        state["posts"]=recent; save_state(state); print("Daily limit reached"); return

    sent=0
    for source,url in FEEDS:
        feed=feedparser.parse(url)
        print(f"{source}: {len(feed.entries)} entries")
        for item in feed.entries[:50]:
            if sent>=allowance: break
            title=item.get("title",""); summary=item.get("summary","")
            if not relevant(title,summary): continue
            key=hashlib.sha256((item.get("link","")+title).encode()).hexdigest()
            if key in seen:
                continue
            if any(same_story(title,s.get("title","")) for s in stories):
                print("Duplicate story skipped:",title)
                seen.add(key)
                continue
            try:
                send(item,source)
                seen.add(key); recent.append(now.isoformat()); sent+=1
                stories.append({"title":title,"time":now.isoformat()})
                print("Published:",title)
            except Exception as e:
                print(f"Skipped failed item: {title} | {type(e).__name__}: {e}")
                continue
        if sent>=allowance: break
    state["seen"]=list(seen); state["posts"]=recent; state["stories"]=stories; save_state(state)
    print(f"Published {sent} item(s)")

if __name__=="__main__": main()
