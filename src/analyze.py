# -*- coding: utf-8 -*-
"""Quant Signal Agent v4 -- Victor Kane Daily Stock Report"""

import os, json, re, urllib.request, urllib.error, smtplib, ssl, time, subprocess, sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
EMAIL_FROM        = os.environ["EMAIL_FROM"]
EMAIL_PASSWORD    = os.environ["EMAIL_PASSWORD"]
EMAIL_TO          = os.environ["EMAIL_TO"]

_raw  = os.environ.get("PERSONAL_WATCHLIST", "")
_extra= os.environ.get("EXTRA_TICKERS", "")
PERSONAL_WATCHLIST = [t.strip().upper() for t in _raw.split(",")   if t.strip()]
EXTRA_TICKERS      = [t.strip().upper() for t in _extra.split(",") if t.strip()]
ALL_PERSONAL       = list(dict.fromkeys(PERSONAL_WATCHLIST + EXTRA_TICKERS))

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# Broad discovery universe -- scans these every day regardless of personal watchlist
DISCOVERY_UNIVERSE = [
    "NVDA","META","MSFT","GOOGL","AMZN",
    "PLTR","ARM","CRWD","SNOW","DDOG",
    "AMD","AVGO","TSM","SMCI","ANET",
    "TSLA","UBER","SHOP","ABNB","COIN",
    "LLY","UNH","ABBV","MRK","ISRG",
    "JPM","GS","V","MA","PYPL",
]

# =============================================================================
# DATA FETCHING
# =============================================================================
def install_yfinance():
    subprocess.check_call([sys.executable,"-m","pip","install","yfinance","--quiet","--break-system-packages"])

def fetch_stock_data(tickers):
    try:
        import yfinance as yf
    except ImportError:
        install_yfinance()
        import yfinance as yf

    results = {}
    print(f"  -> Fetching {len(tickers)} tickers...")
    for ticker in tickers:
        try:
            t    = yf.Ticker(ticker)
            info = t.info or {}
            hist = t.history(period="1y", interval="1d")
            price     = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
            prev      = float(info.get("previousClose") or price)
            chg       = round((price-prev)/prev*100,2) if prev else 0
            rsi = 50
            if len(hist) >= 15:
                d = hist["Close"].diff()
                g = d.clip(lower=0).rolling(14).mean()
                l = (-d.clip(upper=0)).rolling(14).mean()
                rs= g / l.replace(0,0.0001)
                r = 100-(100/(1+rs))
                rsi = round(float(r.iloc[-1]),1) if not r.empty else 50
            ma50  = round(float(hist["Close"].rolling(50).mean().iloc[-1]),2)  if len(hist)>=50  else 0
            ma200 = round(float(hist["Close"].rolling(200).mean().iloc[-1]),2) if len(hist)>=200 else 0
            vol_t = int(hist["Volume"].iloc[-1])        if not hist.empty else 0
            vol_a = int(hist["Volume"].tail(30).mean()) if len(hist)>=30  else 0
            wk52h = float(info.get("fiftyTwoWeekHigh",price) or price)
            results[ticker] = {
                "ticker": ticker,
                "name":   info.get("longName", ticker),
                "sector": info.get("sector","Unknown"),
                "price":  round(price,2),
                "chg_pct":chg,
                "mktcap_b":round((info.get("marketCap",0) or 0)/1e9,1),
                "pe":     round(info.get("trailingPE",0) or 0,1),
                "fwd_pe": round(info.get("forwardPE",0) or 0,1),
                "peg":    round(info.get("pegRatio",0) or 0,2),
                "eps":    round(info.get("trailingEps",0) or 0,2),
                "eps_g":  round((info.get("earningsGrowth",0) or 0)*100,1),
                "rev_g":  round((info.get("revenueGrowth",0) or 0)*100,1),
                "gm":     round((info.get("grossMargins",0) or 0)*100,1),
                "om":     round((info.get("operatingMargins",0) or 0)*100,1),
                "nm":     round((info.get("profitMargins",0) or 0)*100,1),
                "roe":    round((info.get("returnOnEquity",0) or 0)*100,1),
                "de":     round(info.get("debtToEquity",0) or 0,2),
                "cash_b": round((info.get("totalCash",0) or 0)/1e9,1),
                "wk52h":  round(wk52h,2),
                "wk52l":  round(float(info.get("fiftyTwoWeekLow",0) or 0),2),
                "vs52h":  round((price-wk52h)/wk52h*100,1) if wk52h else 0,
                "rsi":    rsi,
                "vs50ma": round((price-ma50)/ma50*100,1)   if ma50  else 0,
                "vs200ma":round((price-ma200)/ma200*100,1) if ma200 else 0,
                "vol":    vol_t,
                "avgvol": vol_a,
                "volr":   round(vol_t/vol_a,2) if vol_a else 1,
                "cons":   info.get("recommendationKey","N/A"),
                "atgt":   round(info.get("targetMeanPrice",0) or 0,2),
                "nans":   int(info.get("numberOfAnalystOpinions",0) or 0),
                "inst":   round((info.get("heldPercentInstitutions",0) or 0)*100,1),
                "earn":   str((info.get("earningsDate",["N/A"])[0])) if info.get("earningsDate") else "N/A",
            }
            print(f"    ok {ticker}: ${price:.2f} RSI:{rsi} PE:{results[ticker]['pe']} RevG:{results[ticker]['rev_g']}%")
        except Exception as e:
            print(f"    fail {ticker}: {e}")
            results[ticker] = {"ticker":ticker,"name":ticker,"error":str(e)}
    return results

def fetch_market():
    try:
        import yfinance as yf
        spy = yf.Ticker("SPY").history(period="2d")
        qqq = yf.Ticker("QQQ").history(period="2d")
        vix = yf.Ticker("^VIX").history(period="1d")
        sp  = round((spy["Close"].iloc[-1]-spy["Close"].iloc[-2])/spy["Close"].iloc[-2]*100,2) if len(spy)>=2 else 0
        nq  = round((qqq["Close"].iloc[-1]-qqq["Close"].iloc[-2])/qqq["Close"].iloc[-2]*100,2) if len(qqq)>=2 else 0
        vx  = round(float(vix["Close"].iloc[-1]),2) if not vix.empty else 0
        return {"sp":sp,"nq":nq,"vix":vx}
    except Exception as e:
        print(f"  market fetch error: {e}")
        return {"sp":0,"nq":0,"vix":0}

# =============================================================================
# CLAUDE CALLS
# =============================================================================
def call_claude(prompt, label):
    print(f"  -> Claude: {label}...")
    payload = json.dumps({
        "model": "claude-sonnet-4-5",
        "max_tokens": 3500,
        "messages": [{"role":"user","content":prompt}]
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=payload,
        headers={"Content-Type":"application/json","x-api-key":ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01"},
        method="POST"
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            print(f"  x {e.code}: {body[:150]}")
            if e.code in (429,500,502,503,529) and attempt < 3:
                w = 30*(attempt+1)
                print(f"  -> retry in {w}s...")
                time.sleep(w); continue
            return {}
        except Exception as e:
            print(f"  x network: {e}")
            if attempt < 3:
                time.sleep(30); continue
            return {}

    text = "".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text").strip()
    text = re.sub(r"^```(?:json)?\s*","",text,flags=re.MULTILINE)
    text = re.sub(r"\s*```$","",text,flags=re.MULTILINE)
    s = text.find("{"); e2 = text.rfind("}")+1
    if s==-1:
        print(f"  x no JSON. preview: {text[:200]}")
        return {}
    js = re.sub(r",\s*([}\]])",r"\1",text[s:e2])
    try:
        return json.loads(js)
    except json.JSONDecodeError as ex:
        print(f"  x JSON error at {ex.pos}: ...{js[max(0,ex.pos-50):ex.pos+50]}...")
        return {}


def discovery_prompt(data_json, mkt):
    return (
        f"You are Victor Kane, Wall St quant analyst, 25 years experience. Date:{TODAY}. "
        f"Market: S&P{mkt['sp']:+.2f}% Nasdaq{mkt['nq']:+.2f}% VIX{mkt['vix']:.1f}\n\n"
        f"LIVE STOCK DATA (from yfinance):\n{data_json}\n\n"
        f"TASK: Select the 3-4 BEST buying opportunities. For each pick:\n"
        f"- Score 0-100: technical(30)+fundamental(25)+catalyst(20)+macro(15)+rr(10)\n"
        f"- Only include if score >= 65\n"
        f"- GROWTH = rev_g > 20%, BALANCED = rev_g 5-20%\n"
        f"- Set realistic entry range, targets (1m/6m/1y), stop loss\n"
        f"- For WHY_BUY: write 2-3 sentences explaining the investment thesis clearly. "
        f"  Include: what the company does, why NOW is a good entry, key catalyst or trend driving it. "
        f"  Be specific -- mention actual numbers from the data.\n"
        f"- For RISKS: 2 specific risks that could invalidate this thesis\n\n"
        f"Reply ONLY with this JSON, no other text:\n"
        f'{{"top_picks":['
        f'{{"ticker":"","name":"","category":"GROWTH","sector":"",'
        f'"price":0,"chg_pct":0,"signal":"BUY","score":0,'
        f'"score_breakdown":{{"technical":0,"fundamental":0,"catalyst":0,"macro":0,"rr":0}},'
        f'"entry_low":0,"entry_high":0,"t1m":0,"t6m":0,"t1y":0,"stop":0,'
        f'"upr_1m":0,"upr_6m":0,"upr_1y":0,"prob_1m":0,"prob_6m":0,"prob_1y":0,"rr_ratio":0,'
        f'"pe":0,"fwd_pe":0,"peg":0,"eps_g":0,"rev_g":0,"gm":0,"om":0,"nm":0,"roe":0,'
        f'"de":0,"cash_b":0,"mktcap_b":0,'
        f'"rsi":0,"vs50ma":0,"vs200ma":0,"volr":0,"wk52h":0,"wk52l":0,"vs52h":0,'
        f'"cons":"","atgt":0,"nans":0,"inst":0,"earn":"",'
        f'"why_buy":"2-3 sentence thesis with specific data points",'
        f'"technical_read":"1-2 sentences on chart setup and key levels",'
        f'"risks":"Risk1; Risk2",'
        f'"catalyst":"key upcoming catalyst",'
        f'"macro_factor":"relevant macro/sector tailwind"}}],'
        f'"macro_summary":"2-sentence market overview with specific observations",'
        f'"risk_level":"LOW|MODERATE|HIGH",'
        f'"sector_rotation":"which sectors seeing inflows today and why",'
        f'"market_mood":"BULLISH|NEUTRAL|BEARISH",'
        f'"full_scan_brief":[{{"ticker":"","bias":"BULLISH|NEUTRAL|BEARISH","reason":"1 sentence"}}]}}'
    )


def watchlist_prompt(data_json, mkt):
    return (
        f"You are Victor Kane, Wall St quant analyst. Date:{TODAY}. "
        f"S&P{mkt['sp']:+.2f}% Nasdaq{mkt['nq']:+.2f}% VIX{mkt['vix']:.1f}\n\n"
        f"WATCHLIST DATA:\n{data_json}\n\n"
        f"TASK: Analyse each stock. For each:\n"
        f"- Score 0-100, give signal (STRONG BUY/BUY/WATCH/HOLD/AVOID)\n"
        f"- Set entry range, 1-year target, stop loss\n"
        f"- Write 2-sentence note: what you see in the data AND a specific action recommendation. "
        f"  Reference actual numbers (RSI, PE, revenue growth, price vs target, etc.)\n\n"
        f"Reply ONLY with this JSON:\n"
        f'{{"watchlist":[{{"ticker":"","name":"","category":"GROWTH|BALANCED",'
        f'"price":0,"chg_pct":0,"signal":"WATCH","score":0,'
        f'"entry_low":0,"entry_high":0,"t1y":0,"stop":0,"upr_1y":0,'
        f'"pe":0,"rsi":0,"wk52h":0,"wk52l":0,"atgt":0,"cons":"",'
        f'"note":"2-sentence analysis with specific data points and clear action"}}]}}'
    )

# =============================================================================
# HTML BUILDER
# =============================================================================
def sig_col(s):
    s=(s or "").upper()
    if "STRONG BUY" in s: return "#059669"
    if "BUY" in s:        return "#10b981"
    if "WATCH" in s:      return "#f59e0b"
    if "HOLD" in s:       return "#6366f1"
    return "#ef4444"

def chg_col(v):
    try: return "#10b981" if float(v)>=0 else "#ef4444"
    except: return "#94a3b8"

def cat_col(c):
    c=(c or "").upper()
    if c=="GROWTH":   return ("bg:#7c3aed","#ede9fe","#7c3aed")
    if c=="BALANCED": return ("bg:#0369a1","#e0f2fe","#0369a1")
    return ("bg:#374151","#f1f5f9","#374151")

def score_bar(score, breakdown):
    s   = int(score or 0)
    col = "#059669" if s>=80 else "#10b981" if s>=65 else "#f59e0b" if s>=50 else "#ef4444"
    lbl = "STRONG BUY" if s>=80 else "BUY" if s>=65 else "WATCH" if s>=50 else "AVOID"
    lbl_bg = "#d1fae5" if s>=65 else "#fef3c7" if s>=50 else "#fee2e2"
    lbl_col= "#065f46" if s>=65 else "#92400e" if s>=50 else "#991b1b"
    rows = ""
    for n,v,mx in [("Technical",breakdown.get("technical",0),30),
                   ("Fundamental",breakdown.get("fundamental",0),25),
                   ("Catalyst",breakdown.get("catalyst",0),20),
                   ("Macro",breakdown.get("macro",0),15),
                   ("Risk/Reward",breakdown.get("rr",0),10)]:
        pct = int(v/mx*100) if mx else 0
        rows += (f'<div style="margin-bottom:5px">'
                 f'<div style="display:flex;justify-content:space-between;font-size:10px;color:#64748b;margin-bottom:2px">'
                 f'<span>{n}</span><span style="font-weight:600;color:{col}">{v}/{mx}</span></div>'
                 f'<div style="height:5px;background:#e2e8f0;border-radius:3px">'
                 f'<div style="height:5px;width:{pct}%;background:{col};border-radius:3px"></div></div></div>')
    return (f'<div style="display:flex;gap:16px;align-items:flex-start;padding:16px 20px;border-bottom:1px solid #f1f5f9">'
            f'<div style="text-align:center;min-width:60px">'
            f'<div style="font-size:32px;font-weight:800;color:{col};line-height:1">{s}</div>'
            f'<div style="font-size:9px;color:#94a3b8;margin-top:2px">/100</div>'
            f'<div style="margin-top:6px;font-size:10px;font-weight:700;padding:3px 8px;border-radius:12px;'
            f'background:{lbl_bg};color:{lbl_col}">{lbl}</div></div>'
            f'<div style="flex:1">{rows}</div></div>')

def stat_box(label, value, color="#0f172a", sub=""):
    return (f'<div style="padding:10px 8px;text-align:center;border-right:1px solid #f1f5f9">'
            f'<div style="font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px">{label}</div>'
            f'<div style="font-size:13px;font-weight:700;color:{color}">{value}</div>'
            f'{"<div style=font-size:9px;color:#94a3b8;margin-top:1px>" + sub + "</div>" if sub else ""}'
            f'</div>')

def pick_card(p, idx):
    t     = p.get("ticker","?")
    nm    = p.get("name","")
    cat   = p.get("category","BALANCED")
    sec   = p.get("sector","")
    price = p.get("price",0)
    chg   = p.get("chg_pct",0)
    sig   = p.get("signal","BUY")
    score = p.get("score",0)
    bd    = p.get("score_breakdown",{})
    _,cbg,cborder = cat_col(cat)

    upr1y = p.get("upr_1y",0)
    upr_col = "#10b981" if float(upr1y or 0) > 0 else "#ef4444"

    def f(v,d=2):
        try: return f"{float(v):.{d}f}" if v not in (None,"","N/A") else "N/A"
        except: return str(v) if v else "N/A"
    def fp(v):
        try:
            n=float(v); return f"{'+'if n>=0 else ''}{n:.1f}%"
        except: return "N/A"

    return f"""
<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;margin-bottom:20px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06)">
  <!-- Header -->
  <div style="padding:16px 20px;background:linear-gradient(135deg,#f8fafc,#f1f5f9);border-bottom:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:flex-start">
    <div>
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap">
        <span style="font-size:11px;color:#6b7280;font-weight:500">#{idx}</span>
        <span style="font-size:22px;font-weight:800;color:#0f172a;letter-spacing:-.02em">{t}</span>
        <span style="font-size:10px;padding:2px 8px;border-radius:10px;font-weight:700;background:{cbg};color:{cborder};border:1px solid {cborder}">{cat}</span>
        <span style="font-size:10px;color:#94a3b8">{sec}</span>
      </div>
      <div style="font-size:12px;color:#64748b">{nm}</div>
    </div>
    <div style="text-align:right">
      <div style="font-size:24px;font-weight:800;color:#0f172a">${f(price)}</div>
      <div style="font-size:12px;font-weight:600;color:{chg_col(chg)}">{fp(chg)} today</div>
      <div style="font-size:11px;font-weight:700;color:{sig_col(sig)};margin-top:3px">{sig}</div>
    </div>
  </div>

  <!-- Confidence score -->
  {score_bar(score, bd)}

  <!-- Price targets -->
  <div style="display:grid;grid-template-columns:repeat(5,1fr);border-bottom:1px solid #f1f5f9">
    {stat_box("Entry range",f"${f(p.get('entry_low'))}",  "#0369a1")}
    {stat_box("entry to",   f"${f(p.get('entry_high'))}", "#0369a1")}
    {stat_box("1-month",    f"${f(p.get('t1m'))}",        "#10b981", fp(p.get('upr_1m')))}
    {stat_box("6-month",    f"${f(p.get('t6m'))}",        "#10b981", fp(p.get('upr_6m')))}
    {stat_box("1-year",     f"${f(p.get('t1y'))}",        upr_col,   fp(p.get('upr_1y'))+" | RR:"+f(p.get('rr_ratio'),1)+"x")}
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid #f1f5f9">
    {stat_box("Stop loss",      f"${f(p.get('stop'))}",    "#ef4444")}
    {stat_box("Analyst target", f"${f(p.get('atgt'))}",    "#6366f1", str(p.get('nans','?'))+" analysts")}
    {stat_box("Next earnings",  str(p.get('earn','N/A')),  "#94a3b8")}
  </div>

  <!-- Key stats row -->
  <div style="display:grid;grid-template-columns:repeat(6,1fr);border-bottom:1px solid #f1f5f9;background:#fafafa">
    {stat_box("P/E",      f"{f(p.get('pe'))}x",    "#0f172a")}
    {stat_box("Fwd P/E",  f"{f(p.get('fwd_pe'))}x","#0f172a")}
    {stat_box("Rev growth",fp(p.get('rev_g')),      "#10b981" if float(p.get('rev_g') or 0)>15 else "#0f172a")}
    {stat_box("EPS growth",fp(p.get('eps_g')),      "#10b981" if float(p.get('eps_g') or 0)>0 else "#ef4444")}
    {stat_box("Gross margin",fp(p.get('gm')),       "#0f172a")}
    {stat_box("Net margin",fp(p.get('nm')),         "#0f172a")}
  </div>
  <div style="display:grid;grid-template-columns:repeat(6,1fr);border-bottom:1px solid #f1f5f9;background:#fafafa">
    {stat_box("RSI (14)",   str(p.get('rsi','N/A')), "#f59e0b" if float(p.get('rsi') or 50)>70 else "#10b981" if float(p.get('rsi') or 50)<35 else "#0f172a")}
    {stat_box("Vs 50MA",   fp(p.get('vs50ma')),     chg_col(p.get('vs50ma')))}
    {stat_box("Vs 200MA",  fp(p.get('vs200ma')),    chg_col(p.get('vs200ma')))}
    {stat_box("Vol ratio", f"{f(p.get('volr'))}x",  "#10b981" if float(p.get('volr') or 1)>1.3 else "#0f172a")}
    {stat_box("52W high",  f"${f(p.get('wk52h'))}", "#0f172a")}
    {stat_box("Vs 52W hi", fp(p.get('vs52h')),      chg_col(p.get('vs52h')))}
  </div>

  <!-- Victor's thesis -->
  <div style="padding:16px 20px;border-bottom:1px solid #f1f5f9">
    <div style="font-size:10px;font-weight:700;color:#7c3aed;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Victor Kane's Investment Thesis</div>
    <p style="font-size:13px;color:#1e293b;line-height:1.7;margin:0 0 12px">{p.get("why_buy","N/A")}</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px">
        <div style="font-size:9px;font-weight:700;color:#166534;text-transform:uppercase;margin-bottom:5px">Technical Setup</div>
        <p style="font-size:12px;color:#166534;line-height:1.6;margin:0">{p.get("technical_read","N/A")}</p>
      </div>
      <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:12px">
        <div style="font-size:9px;font-weight:700;color:#1e40af;text-transform:uppercase;margin-bottom:5px">Key Catalyst</div>
        <p style="font-size:12px;color:#1e40af;line-height:1.6;margin:0">{p.get("catalyst","N/A")}</p>
      </div>
    </div>
    <div style="margin-top:10px;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:10px">
      <div style="font-size:9px;font-weight:700;color:#92400e;text-transform:uppercase;margin-bottom:4px">Macro / Sector Tailwind</div>
      <p style="font-size:12px;color:#92400e;line-height:1.6;margin:0">{p.get("macro_factor","N/A")}</p>
    </div>
  </div>
  <div style="padding:10px 20px;background:#fef2f2">
    <span style="font-size:9px;font-weight:700;color:#991b1b;text-transform:uppercase">Risks: </span>
    <span style="font-size:11px;color:#991b1b">{p.get("risks","N/A")}</span>
  </div>
</div>"""


def watchlist_card(w):
    t     = w.get("ticker","?")
    nm    = w.get("name","")
    cat   = w.get("category","BALANCED")
    price = w.get("price",0)
    chg   = w.get("chg_pct",0)
    sig   = w.get("signal","WATCH")
    score = w.get("score",0)
    _,cbg,cborder = cat_col(cat)

    def f(v,d=2):
        try: return f"{float(v):.{d}f}" if v not in (None,"","N/A") else "N/A"
        except: return str(v) if v else "N/A"
    def fp(v):
        try:
            n=float(v); return f"{'+'if n>=0 else ''}{n:.1f}%"
        except: return "N/A"

    score_col = "#059669" if score>=80 else "#10b981" if score>=65 else "#f59e0b" if score>=50 else "#ef4444"

    return f"""
<div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;margin-bottom:12px;overflow:hidden">
  <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#f8fafc;border-bottom:1px solid #f1f5f9;flex-wrap:wrap;gap:8px">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span style="font-size:17px;font-weight:800;color:#0f172a">{t}</span>
      <span style="font-size:9px;padding:2px 7px;border-radius:8px;font-weight:700;background:{cbg};color:{cborder}">{cat}</span>
      <span style="font-size:10px;font-weight:600;color:{sig_col(sig)}">{sig}</span>
      <span style="font-size:10px;color:#94a3b8">{nm[:30]}</span>
    </div>
    <div style="display:flex;align-items:center;gap:12px">
      <div style="text-align:right">
        <div style="font-size:16px;font-weight:700;color:#0f172a">${f(price)}</div>
        <div style="font-size:11px;color:{chg_col(chg)}">{fp(chg)}</div>
      </div>
      <div style="text-align:center;min-width:44px;padding:6px 10px;background:{score_col}15;border-radius:8px;border:1px solid {score_col}40">
        <div style="font-size:16px;font-weight:800;color:{score_col}">{score}</div>
        <div style="font-size:8px;color:#94a3b8">/100</div>
      </div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(7,1fr);border-bottom:1px solid #f1f5f9">
    {stat_box("Entry", f"${f(w.get('entry_low'))}-${f(w.get('entry_high'))}", "#0369a1")}
    {stat_box("1Y target", f"${f(w.get('t1y'))}", "#10b981", fp(w.get('upr_1y')))}
    {stat_box("Stop", f"${f(w.get('stop'))}", "#ef4444")}
    {stat_box("P/E", f"{f(w.get('pe'))}x", "#0f172a")}
    {stat_box("RSI", str(w.get('rsi','N/A')), "#f59e0b" if float(w.get('rsi') or 50)>70 else "#10b981" if float(w.get('rsi') or 50)<35 else "#0f172a")}
    {stat_box("Analyst tgt", f"${f(w.get('atgt'))}", "#6366f1")}
    {stat_box("Consensus", str(w.get('cons','N/A')), "#0f172a")}
  </div>
  <div style="padding:12px 16px;background:#f8fafc">
    <span style="font-size:9px;font-weight:700;color:#475569;text-transform:uppercase">Victor: </span>
    <span style="font-size:12px;color:#1e293b;font-style:italic">{w.get("note","N/A")}</span>
  </div>
</div>"""


def build_email(picks, watchlist, scan_brief, macro, mkt):
    growth   = [p for p in picks if str(p.get("category","")).upper()=="GROWTH"]
    balanced = [p for p in picks if str(p.get("category","")).upper()!="GROWTH"]
    risk     = macro.get("risk_level","MODERATE").upper()
    mood     = macro.get("market_mood","NEUTRAL").upper()
    risk_col = {"LOW":"#059669","MODERATE":"#f59e0b","HIGH":"#ef4444"}.get(risk,"#94a3b8")
    mood_col = {"BULLISH":"#059669","NEUTRAL":"#f59e0b","BEARISH":"#ef4444"}.get(mood,"#94a3b8")

    pick_html = ""
    if picks:
        if growth:
            pick_html += f'<div style="display:flex;align-items:center;gap:8px;margin:20px 0 12px"><div style="width:4px;height:28px;background:#7c3aed;border-radius:2px"></div><div><div style="font-size:15px;font-weight:700;color:#0f172a">Growth Picks</div><div style="font-size:11px;color:#64748b">{len(growth)} high-conviction</div></div></div>'
            pick_html += "".join(pick_card(p,i+1) for i,p in enumerate(growth))
        if balanced:
            pick_html += f'<div style="display:flex;align-items:center;gap:8px;margin:20px 0 12px"><div style="width:4px;height:28px;background:#0369a1;border-radius:2px"></div><div><div style="font-size:15px;font-weight:700;color:#0f172a">Balanced Picks</div><div style="font-size:11px;color:#64748b">{len(balanced)} solid setups</div></div></div>'
            pick_html += "".join(pick_card(p,i+1) for i,p in enumerate(balanced))
    else:
        pick_html = '<div style="padding:24px;text-align:center;color:#94a3b8;font-size:13px;background:#f8fafc;border-radius:8px;margin:16px 0">No high-conviction picks today -- market conditions not ideal for new entries.</div>'

    watch_html = ""
    if watchlist:
        watch_html = (f'<div style="display:flex;align-items:center;gap:8px;margin:20px 0 12px">'
                      f'<div style="width:4px;height:28px;background:#f59e0b;border-radius:2px"></div>'
                      f'<div><div style="font-size:15px;font-weight:700;color:#0f172a">Your Watchlist</div>'
                      f'<div style="font-size:11px;color:#64748b">{len(watchlist)} stocks tracked</div></div></div>'
                      + "".join(watchlist_card(w) for w in watchlist))

    brief_html = ""
    if scan_brief:
        items = "".join([
            f'<span style="display:inline-flex;align-items:center;gap:5px;padding:4px 10px;margin:3px;'
            f'background:#f8fafc;border:1px solid #e2e8f0;border-radius:20px;font-size:11px">'
            f'<span style="font-weight:700;color:{"#059669" if b.get("bias")=="BULLISH" else "#ef4444" if b.get("bias")=="BEARISH" else "#f59e0b"}">{b.get("ticker","")}</span>'
            f'<span style="color:#64748b">{b.get("reason","")}</span></span>'
            for b in scan_brief
        ])
        brief_html = (f'<div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px 18px;margin-top:16px">'
                      f'<div style="font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px">Full Scan Brief</div>'
                      f'{items}</div>')

    tracking = " &middot; ".join(ALL_PERSONAL) if ALL_PERSONAL else "none"
    font = "-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,sans-serif"

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Victor Kane Report {TODAY}</title></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:{font}">

<!-- HEADER -->
<div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);padding:28px 32px">
  <div style="max-width:860px;margin:0 auto">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
      <div>
        <div style="font-size:10px;color:#475569;text-transform:uppercase;letter-spacing:.15em;margin-bottom:4px">Quant Signal Agent</div>
        <div style="font-size:26px;font-weight:800;color:#fff;letter-spacing:-.02em">Victor Kane Daily Report</div>
        <div style="font-size:11px;color:#64748b;margin-top:4px">{TODAY} &middot; {NOW}</div>
        <div style="font-size:11px;color:#475569;margin-top:3px">Tracking: {tracking}</div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <div style="text-align:center;padding:10px 16px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);border-radius:8px">
          <div style="font-size:9px;color:#64748b;text-transform:uppercase;margin-bottom:3px">Market Risk</div>
          <div style="font-size:16px;font-weight:800;color:{risk_col}">{risk}</div>
        </div>
        <div style="text-align:center;padding:10px 16px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);border-radius:8px">
          <div style="font-size:9px;color:#64748b;text-transform:uppercase;margin-bottom:3px">Top Picks</div>
          <div style="font-size:16px;font-weight:800;color:#fff">{len(picks)}</div>
        </div>
        <div style="text-align:center;padding:10px 16px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);border-radius:8px">
          <div style="font-size:9px;color:#64748b;text-transform:uppercase;margin-bottom:3px">G / B</div>
          <div style="font-size:16px;font-weight:800;color:#fff">{len(growth)}/{len(balanced)}</div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- MARKET SUMMARY -->
<div style="background:#fff;border-bottom:1px solid #e2e8f0;padding:16px 32px">
  <div style="max-width:860px;margin:0 auto;display:grid;grid-template-columns:1fr auto;gap:20px;align-items:start">
    <div>
      <div style="font-size:9px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px">Victor's Market Read</div>
      <p style="font-size:13px;color:#1e293b;line-height:1.7;margin:0 0 8px">{macro.get("macro_summary","N/A")}</p>
      <div style="font-size:12px;color:#64748b"><strong style="color:#374151">Sector rotation:</strong> {macro.get("sector_rotation","N/A")}</div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(2,auto);gap:8px;min-width:180px">
      <div style="text-align:center;padding:8px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px">
        <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;margin-bottom:2px">Mood</div>
        <div style="font-size:14px;font-weight:700;color:{mood_col}">{mood}</div>
      </div>
      <div style="text-align:center;padding:8px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px">
        <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;margin-bottom:2px">VIX</div>
        <div style="font-size:14px;font-weight:700;color:#0f172a">{mkt.get("vix","N/A")}</div>
      </div>
      <div style="text-align:center;padding:8px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px">
        <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;margin-bottom:2px">S&P 500</div>
        <div style="font-size:14px;font-weight:700;color:{"#10b981" if float(mkt.get("sp",0))>=0 else "#ef4444"}">{"+"+str(mkt.get("sp","0")) if float(mkt.get("sp",0))>=0 else str(mkt.get("sp","0"))}%</div>
      </div>
      <div style="text-align:center;padding:8px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px">
        <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;margin-bottom:2px">Nasdaq</div>
        <div style="font-size:14px;font-weight:700;color:{"#10b981" if float(mkt.get("nq",0))>=0 else "#ef4444"}">{"+"+str(mkt.get("nq","0")) if float(mkt.get("nq",0))>=0 else str(mkt.get("nq","0"))}%</div>
      </div>
    </div>
  </div>
</div>

<!-- MAIN CONTENT -->
<div style="max-width:860px;margin:0 auto;padding:20px 16px">
  {pick_html}
  {watch_html}
  {brief_html}
  <div style="text-align:center;padding:20px;font-size:10px;color:#94a3b8;line-height:1.8;margin-top:8px">
    For educational purposes only. Not financial advice. Always do your own research.<br>
    Data: yfinance (live) &middot; Analysis: Claude AI &middot; {NOW}
  </div>
</div>
</body></html>"""

# =============================================================================
# SEND EMAIL
# =============================================================================
def send_email(html, subject):
    print(f"  -> Sending to {EMAIL_TO}...")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html,"html"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com",465,context=ctx) as srv:
        srv.login(EMAIL_FROM,EMAIL_PASSWORD)
        srv.sendmail(EMAIL_FROM,EMAIL_TO,msg.as_string())
    print("  -> Sent.")

# =============================================================================
# MAIN
# =============================================================================
def main():
    print(f"\n{'='*55}\n  Quant Signal Agent -- {NOW}")
    if ALL_PERSONAL: print(f"  Watchlist: {', '.join(ALL_PERSONAL)}")
    print(f"{'='*55}\n")

    # Step 1 -- market data
    print("[Step 1] Fetching market data...")
    mkt = fetch_market()
    print(f"  -> S&P {mkt['sp']:+.2f}% | Nasdaq {mkt['nq']:+.2f}% | VIX {mkt['vix']:.1f}")

    # Discovery: deduplicated list excluding personal tickers
    disc_tickers  = [t for t in DISCOVERY_UNIVERSE if t not in ALL_PERSONAL][:12]
    watch_tickers = ALL_PERSONAL[:12]
    all_tickers   = list(dict.fromkeys(disc_tickers + watch_tickers))

    print(f"\n  Discovery: {disc_tickers}")
    print(f"  Watchlist: {watch_tickers}")

    stock_data = fetch_stock_data(all_tickers)

    # Compact JSON for Claude (only valid tickers, no errors)
    def to_json(tickers):
        d = {t: stock_data[t] for t in tickers if t in stock_data and "error" not in stock_data[t]}
        return json.dumps(d, separators=(',',':'))

    # Step 2a -- discovery picks
    print("\n[Step 2a] Discovery scan -- Victor Kane finding top picks...")
    d_report = call_claude(discovery_prompt(to_json(disc_tickers), mkt), "discovery")
    picks      = d_report.get("top_picks", [])
    scan_brief = d_report.get("full_scan_brief", [])
    macro      = {
        "macro_summary":  d_report.get("macro_summary",""),
        "risk_level":     d_report.get("risk_level","MODERATE"),
        "sector_rotation":d_report.get("sector_rotation",""),
        "market_mood":    d_report.get("market_mood","NEUTRAL"),
    }
    print(f"  -> Found {len(picks)} picks, {len(scan_brief)} brief items")
    if not picks:
        print("  -> WARNING: no picks returned. Check API response above.")

    # Step 2b -- watchlist
    watchlist = []
    if watch_tickers:
        print("\n[Step 2b] Watchlist analysis...")
        time.sleep(8)
        w_report  = call_claude(watchlist_prompt(to_json(watch_tickers), mkt), "watchlist")
        watchlist = w_report.get("watchlist", [])
        print(f"  -> {len(watchlist)} watchlist stocks analysed")

    growth   = [p for p in picks if str(p.get("category","")).upper()=="GROWTH"]
    balanced = [p for p in picks if str(p.get("category","")).upper()!="GROWTH"]

    # Step 3 -- email
    print("\n[Step 3] Building and sending report...")
    html    = build_email(picks, watchlist, scan_brief, macro, mkt)
    mood    = macro.get("market_mood","?")
    risk    = macro.get("risk_level","?")
    subject = f"Victor Kane {TODAY} | {len(picks)} picks ({len(growth)}G/{len(balanced)}B) | {mood} | Risk:{risk}"
    send_email(html, subject)

    print(f"\n{'='*55}\n  Done -- sent to {EMAIL_TO}\n{'='*55}\n")


if __name__ == "__main__":
    main()
