import os, json, html, requests

TOKEN=os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY=os.environ["OPENAI_API_KEY"]
CHANNEL=os.environ.get("TELEGRAM_CHANNEL","@iranuknews")

prompt="""Translate this test headline into natural Persian and write one short neutral Persian summary sentence.
Return valid JSON only with keys fa_title and fa_summary.
Headline: UK-Iran news bot translation test
Context: This is only a technical test confirming automatic Persian translation is working."""

r=requests.post("https://api.openai.com/v1/responses",
 headers={"Authorization":f"Bearer {OPENAI_API_KEY}","Content-Type":"application/json"},
 json={"model":"gpt-5.6-luna","input":prompt,"max_output_tokens":180},timeout=45)
r.raise_for_status()
data=r.json()
out=data.get("output_text","")
if not out:
    out="".join(c.get("text","") for o in data.get("output",[]) for c in o.get("content",[]) if c.get("type")=="output_text")
tr=json.loads(out.strip().replace("```json","").replace("```","").strip())
msg=(f"🧪 <b>UK-Iran news bot translation test</b>\n\n"
     f"🇮🇷 <b>{html.escape(tr['fa_title'])}</b>\n"
     f"{html.escape(tr['fa_summary'])}\n\n"
     "✅ تست فنی ترجمه خودکار")
t=requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
 json={"chat_id":CHANNEL,"text":msg,"parse_mode":"HTML"},timeout=20)
t.raise_for_status()
print("Translation and Telegram test succeeded")
