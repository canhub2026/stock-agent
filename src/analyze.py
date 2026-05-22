# -*- coding: utf-8 -*-
"""Quant Signal Agent v6 -- Victor Kane | Auto-deploy GitHub Pages"""

import os, json, re, urllib.request, urllib.error, smtplib, ssl, time, subprocess, sys, base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timezone

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
EMAIL_FROM        = os.environ["EMAIL_FROM"]
EMAIL_PASSWORD    = os.environ["EMAIL_PASSWORD"]
EMAIL_TO          = os.environ["EMAIL_TO"]
GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO       = os.environ.get("GITHUB_REPOSITORY", "")

_raw  = os.environ.get("PERSONAL_WATCHLIST", "")
_extra= os.environ.get("EXTRA_TICKERS", "")
PERSONAL_WATCHLIST = [t.strip().upper() for t in _raw.split(",")   if t.strip()]
EXTRA_TICKERS      = [t.strip().upper() for t in _extra.split(",") if t.strip()]
ALL_PERSONAL       = list(dict.fromkeys(PERSONAL_WATCHLIST + EXTRA_TICKERS))

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

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
        install_yfinance(); import yfinance as yf
    results = {}
    print(f"  -> Fetching {len(tickers)} tickers...")
    for ticker in tickers:
        try:
            t    = yf.Ticker(ticker)
            info = t.info or {}
            hist = t.history(period="1y", interval="1d")
            price = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
            prev  = float(info.get("previousClose") or price)
            chg   = round((price-prev)/prev*100,2) if prev else 0
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
            wk52l = float(info.get("fiftyTwoWeekLow",0) or 0)
            # Short description (first 2 sentences of longBusinessSummary)
            desc = info.get("longBusinessSummary","")
            if desc:
                sents = desc.replace("  "," ").split(". ")
                desc  = ". ".join(sents[:2]) + ("." if len(sents)>1 else "")
                if len(desc) > 200: desc = desc[:200] + "..."
            results[ticker] = {
                "ticker":   ticker,
                "name":     info.get("shortName", info.get("longName", ticker)),
                "fullname": info.get("longName", ticker),
                "sector":   info.get("sector","Unknown"),
                "industry": info.get("industry","Unknown"),
                "country":  info.get("country","US"),
                "desc":     desc,
                "website":  info.get("website",""),
                "employees":info.get("fullTimeEmployees",0) or 0,
                "founded":  info.get("founded",""),
                "price":    round(price,2),
                "chg_pct":  chg,
                "mktcap_b": round((info.get("marketCap",0) or 0)/1e9,1),
                "ev_b":     round((info.get("enterpriseValue",0) or 0)/1e9,1),
                "pe":       round(info.get("trailingPE",0) or 0,1),
                "fwd_pe":   round(info.get("forwardPE",0) or 0,1),
                "peg":      round(info.get("pegRatio",0) or 0,2),
                "ps":       round(info.get("priceToSalesTrailing12Months",0) or 0,1),
                "pb":       round(info.get("priceToBook",0) or 0,1),
                "ev_ebitda":round(info.get("enterpriseToEbitda",0) or 0,1),
                "eps":      round(info.get("trailingEps",0) or 0,2),
                "eps_g":    round((info.get("earningsGrowth",0) or 0)*100,1),
                "rev_g":    round((info.get("revenueGrowth",0) or 0)*100,1),
                "rev_b":    round((info.get("totalRevenue",0) or 0)/1e9,1),
                "gm":       round((info.get("grossMargins",0) or 0)*100,1),
                "om":       round((info.get("operatingMargins",0) or 0)*100,1),
                "nm":       round((info.get("profitMargins",0) or 0)*100,1),
                "roe":      round((info.get("returnOnEquity",0) or 0)*100,1),
                "roa":      round((info.get("returnOnAssets",0) or 0)*100,1),
                "de":       round(info.get("debtToEquity",0) or 0,2),
                "cr":       round(info.get("currentRatio",0) or 0,2),
                "cash_b":   round((info.get("totalCash",0) or 0)/1e9,1),
                "fcf_b":    round((info.get("freeCashflow",0) or 0)/1e9,1),
                "div_yield":round((info.get("dividendYield",0) or 0)*100,2),
                "beta":     round(info.get("beta",0) or 0,2),
                "short_pct":round((info.get("shortPercentOfFloat",0) or 0)*100,1),
                "wk52h":    round(wk52h,2),
                "wk52l":    round(wk52l,2),
                "vs52h":    round((price-wk52h)/wk52h*100,1) if wk52h else 0,
                "vs52l":    round((price-wk52l)/wk52l*100,1) if wk52l else 0,
                "rsi":      rsi,
                "vs50ma":   round((price-ma50)/ma50*100,1)   if ma50  else 0,
                "vs200ma":  round((price-ma200)/ma200*100,1) if ma200 else 0,
                "vol":      vol_t,
                "avgvol":   vol_a,
                "volr":     round(vol_t/vol_a,2) if vol_a else 1,
                "cons":     info.get("recommendationKey","N/A"),
                "atgt":     round(info.get("targetMeanPrice",0) or 0,2),
                "atgt_hi":  round(info.get("targetHighPrice",0) or 0,2),
                "atgt_lo":  round(info.get("targetLowPrice",0) or 0,2),
                "nans":     int(info.get("numberOfAnalystOpinions",0) or 0),
                "inst":     round((info.get("heldPercentInstitutions",0) or 0)*100,1),
                "insider":  round((info.get("heldPercentInsiders",0) or 0)*100,1),
                "earn":     str((info.get("earningsDate",["N/A"])[0])) if info.get("earningsDate") else "N/A",
            }
            print(f"    ok {ticker}: ${price:.2f} RSI:{rsi} PE:{results[ticker]['pe']} RevG:{results[ticker]['rev_g']}%")
        except Exception as e:
            print(f"    fail {ticker}: {e}")
            results[ticker] = {"ticker":ticker,"name":ticker,"sector":"Unknown","industry":"Unknown","desc":"","error":str(e)}
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
        print(f"  market error: {e}"); return {"sp":0,"nq":0,"vix":0}

# =============================================================================
# CLAUDE CALLS
# =============================================================================
def call_claude(prompt, label, max_tokens=1800):
    print(f"  -> Claude: {label}...")
    payload = json.dumps({
        "model":"claude-sonnet-4-5","max_tokens":max_tokens,
        "messages":[{"role":"user","content":prompt}]
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
            print(f"  x {e.code}: {body[:120]}")
            if e.code in (429,500,502,503,529) and attempt < 3:
                w = 30*(attempt+1); print(f"  -> retry in {w}s..."); time.sleep(w); continue
            return {}
        except Exception as e:
            print(f"  x {e}")
            if attempt < 3: time.sleep(30); continue
            return {}
    text = "".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text").strip()
    text = re.sub(r"^```(?:json)?\s*","",text,flags=re.MULTILINE)
    text = re.sub(r"\s*```$","",text,flags=re.MULTILINE)
    s = text.find("{"); e2 = text.rfind("}")+1
    if s==-1: print(f"  x no JSON: {text[:150]}"); return {}
    js = re.sub(r",\s*([}\]])",r"\1",text[s:e2])
    try: return json.loads(js)
    except json.JSONDecodeError as ex:
        print(f"  x JSON err pos {ex.pos}: ...{js[max(0,ex.pos-40):ex.pos+40]}...")
        return {}

def discovery_prompt(data_json, mkt):
    return (
        f"Victor Kane, quant analyst. {TODAY}. S&P{mkt['sp']:+.2f}% Nasdaq{mkt['nq']:+.2f}% VIX{mkt['vix']:.1f}\n"
        f"DATA:\n{data_json}\n\n"
        f"Pick the 2 best BUY setups. Score: technical(30)+fundamental(25)+catalyst(20)+macro(15)+rr(10). Min 65.\n"
        f"GROWTH=rev_g>20%. BALANCED=5-20%. ALL text fields HARD LIMIT 10 words.\n\n"
        f"JSON only:\n"
        f'{{"top_picks":[{{"ticker":"","name":"","category":"GROWTH","sector":"","industry":"",'
        f'"price":0,"chg_pct":0,"signal":"BUY","score":0,'
        f'"score_breakdown":{{"technical":0,"fundamental":0,"catalyst":0,"macro":0,"rr":0}},'
        f'"entry_low":0,"entry_high":0,"t1m":0,"t6m":0,"t1y":0,"stop":0,'
        f'"upr_1m":0,"upr_6m":0,"upr_1y":0,"prob_1m":0,"prob_6m":0,"prob_1y":0,"rr_ratio":0,'
        f'"pe":0,"fwd_pe":0,"rev_g":0,"gm":0,"nm":0,"mktcap_b":0,'
        f'"rsi":0,"vs50ma":0,"vs200ma":0,"wk52h":0,"wk52l":0,"vs52h":0,'
        f'"cons":"","atgt":0,"nans":0,"earn":"",'
        f'"why_buy":"","technical_read":"","risks":"","catalyst":"","macro_factor":""}}],'
        f'"macro_summary":"","risk_level":"MODERATE","sector_rotation":"","market_mood":"NEUTRAL",'
        f'"full_scan_brief":[{{"ticker":"","bias":"BULLISH","reason":""}}]}}'
    )

def watchlist_prompt(data_json, mkt):
    return (
        f"Victor Kane. {TODAY}. S&P{mkt['sp']:+.2f}% Nasdaq{mkt['nq']:+.2f}% VIX{mkt['vix']:.1f}\n"
        f"WATCHLIST:\n{data_json}\n\n"
        f"Score each 0-100. Signal: STRONG BUY/BUY/WATCH/HOLD/AVOID. Entry range, 1y target, stop.\n"
        f"note = EXACTLY 12 words, include 2 specific numbers from the data.\n\n"
        f"JSON only:\n"
        f'{{"watchlist":[{{"ticker":"","name":"","category":"GROWTH","sector":"","industry":"",'
        f'"price":0,"chg_pct":0,"signal":"WATCH","score":0,'
        f'"entry_low":0,"entry_high":0,"t1y":0,"stop":0,"upr_1y":0,'
        f'"pe":0,"fwd_pe":0,"rsi":0,"rev_g":0,"gm":0,"nm":0,'
        f'"wk52h":0,"wk52l":0,"vs52h":0,"atgt":0,"cons":"","nans":0,'
        f'"vs50ma":0,"vs200ma":0,"volr":0,"beta":0,"short_pct":0,'
        f'"note":""}}]}}'
    )

# =============================================================================
# PUBLISH TO GITHUB (docs/index.html)
# =============================================================================
def publish_to_github(html_content):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("  -> No GitHub token, skipping publish")
        return
    api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/docs/index.html"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "stock-agent"
    }
    sha = None
    try:
        req = urllib.request.Request(api, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            sha = json.loads(r.read().decode()).get("sha")
    except: pass
    encoded = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")
    body = {"message": f"Report {TODAY}", "content": encoded, "branch": "main"}
    if sha: body["sha"] = sha
    req = urllib.request.Request(api, data=json.dumps(body).encode(), headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=30):
            owner, repo = GITHUB_REPO.split("/")
            print(f"  -> Published docs/index.html -> https://{owner}.github.io/{repo}/")
    except Exception as e:
        print(f"  -> Publish failed: {e}")

# =============================================================================
# HTML REPORT
# =============================================================================
def build_html(picks, watchlist, scan_brief, macro, mkt, all_stock_data):
    picks_json     = json.dumps(picks,         ensure_ascii=False)
    watchlist_json = json.dumps(watchlist,     ensure_ascii=False)
    scan_json      = json.dumps(scan_brief,    ensure_ascii=False)
    macro_json     = json.dumps(macro,         ensure_ascii=False)
    mkt_json       = json.dumps(mkt,           ensure_ascii=False)
    stocks_json    = json.dumps(all_stock_data,ensure_ascii=False)
    tracking       = ", ".join(ALL_PERSONAL) if ALL_PERSONAL else "none"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Victor Kane -- {TODAY}</title>
<style>
:root{{--bg:#0f172a;--card:#1e293b;--card2:#263148;--border:#334155;--text:#e2e8f0;--muted:#94a3b8;
      --green:#10b981;--red:#ef4444;--amber:#f59e0b;--blue:#3b82f6;--purple:#8b5cf6;--indigo:#6366f1}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh}}
.header{{background:linear-gradient(135deg,#0f172a,#1e3a5f);padding:20px;border-bottom:1px solid var(--border)}}
.header-inner{{max-width:1200px;margin:0 auto;display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px}}
.logo{{font-size:10px;color:#475569;letter-spacing:.15em;text-transform:uppercase;margin-bottom:3px}}
.title{{font-size:22px;font-weight:800;color:#fff}}
.subtitle{{font-size:11px;color:#64748b;margin-top:3px}}
.badges{{display:flex;gap:8px;flex-wrap:wrap}}
.badge{{padding:8px 14px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);border-radius:8px;text-align:center}}
.badge-label{{font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:.1em;margin-bottom:2px}}
.badge-val{{font-size:14px;font-weight:800;color:#fff}}
.market-bar{{background:var(--card);border-bottom:1px solid var(--border);padding:12px 20px}}
.market-inner{{max-width:1200px;margin:0 auto;display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
.mstat{{text-align:center;padding:6px 14px;background:var(--card2);border-radius:8px;min-width:72px}}
.mstat-l{{font-size:9px;color:var(--muted);text-transform:uppercase;margin-bottom:2px}}
.mstat-v{{font-size:13px;font-weight:700}}
.macro-text{{font-size:12px;color:var(--muted);flex:1;min-width:180px;line-height:1.6}}
.nav{{background:var(--card);border-bottom:1px solid var(--border);padding:0 20px;display:flex;gap:0;overflow-x:auto}}
.nav-btn{{padding:11px 16px;font-size:12px;font-weight:600;color:var(--muted);background:none;border:none;cursor:pointer;border-bottom:3px solid transparent;white-space:nowrap;transition:.2s}}
.nav-btn.active{{color:var(--blue);border-bottom-color:var(--blue)}}
.main{{max-width:1200px;margin:0 auto;padding:16px}}
.section{{display:none}}.section.active{{display:block}}

/* PICK CARDS */
.picks-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px;margin-top:12px}}
.pick-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden;transition:.2s;cursor:pointer}}
.pick-card:hover{{border-color:var(--blue);transform:translateY(-1px)}}
.card-header{{padding:14px 16px;background:var(--card2);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:flex-start}}
.card-detail{{display:none;padding:14px 16px;border-top:1px solid var(--border);background:var(--bg);font-size:12px;line-height:1.7;color:var(--muted)}}
.card-detail.open{{display:block}}

/* WATCHLIST TABLE */
.tbl-wrap{{overflow-x:auto;margin-top:12px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{padding:10px 10px;font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;
    border-bottom:2px solid var(--border);text-align:left;white-space:nowrap;cursor:pointer;user-select:none;
    background:var(--card2);position:sticky;top:0}}
th:hover{{color:var(--blue)}}
th.sort-asc::after{{content:" ^"}}
th.sort-desc::after{{content:" v"}}
td{{padding:9px 10px;border-bottom:1px solid var(--border);vertical-align:middle;white-space:nowrap}}
tr:hover td{{background:var(--card2)}}
.sector-header{{padding:10px 16px;background:var(--card2);border-radius:8px;margin:16px 0 8px;
               font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;
               display:flex;align-items:center;gap:8px}}
.company-cell{{white-space:normal;min-width:160px}}
.company-name{{font-size:13px;font-weight:700;color:var(--text)}}
.company-sub{{font-size:10px;color:var(--muted);margin-top:1px}}
.company-desc{{font-size:10px;color:#64748b;margin-top:3px;line-height:1.4;max-width:220px;white-space:normal}}
.tag{{display:inline-block;padding:1px 6px;border-radius:4px;font-size:9px;font-weight:700;margin-top:2px}}
.signal-badge{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700}}
.score-cell{{text-align:center}}
.score-num{{font-size:16px;font-weight:800}}
.score-sub{{font-size:9px;color:var(--muted)}}

/* MISC */
.brief-grid{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}}
.brief-chip{{padding:5px 12px;background:var(--card2);border:1px solid var(--border);border-radius:20px;font-size:11px;display:flex;align-items:center;gap:6px}}
.empty{{text-align:center;padding:40px;color:var(--muted);font-size:13px;background:var(--card2);border-radius:12px}}
.section-hdr{{font-size:15px;font-weight:700;margin-bottom:4px;display:flex;align-items:center;gap:8px;margin-top:8px}}
.section-sub{{font-size:11px;color:var(--muted);margin-bottom:12px}}
.filter-row{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center}}
.filter-btn{{padding:5px 12px;font-size:11px;background:var(--card2);border:1px solid var(--border);border-radius:20px;cursor:pointer;color:var(--muted);transition:.2s}}
.filter-btn.active{{background:var(--blue);color:#fff;border-color:var(--blue)}}
.search-box{{padding:6px 12px;font-size:12px;background:var(--card2);border:1px solid var(--border);border-radius:8px;color:var(--text);flex:1;min-width:150px;max-width:220px}}
.green{{color:var(--green)}}.red{{color:var(--red)}}.amber{{color:var(--amber)}}.blue{{color:var(--blue)}}.muted{{color:var(--muted)}}
@media(max-width:600px){{.picks-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>

<div class="header">
  <div class="header-inner">
    <div>
      <div class="logo">Quant Signal Agent</div>
      <div class="title">Victor Kane Daily Report</div>
      <div class="subtitle">{TODAY} &middot; {NOW}</div>
      <div class="subtitle">Tracking: {tracking}</div>
    </div>
    <div class="badges" id="hdr-badges"></div>
  </div>
</div>
<div class="market-bar"><div class="market-inner" id="mkt-bar"></div></div>
<nav class="nav">
  <button class="nav-btn active" onclick="showTab('picks',this)">Top Picks</button>
  <button class="nav-btn" onclick="showTab('watchlist',this)">Watchlist</button>
  <button class="nav-btn" onclick="showTab('scan',this)">Full Scan</button>
</nav>
<div class="main">
  <div id="picks" class="section active"></div>
  <div id="watchlist" class="section"></div>
  <div id="scan" class="section"></div>
</div>

<script>
const PICKS={picks_json},WATCHLIST={watchlist_json},SCAN={scan_json};
const MACRO={macro_json},MKT={mkt_json},STOCKS={stocks_json};
const TODAY="{TODAY}";
const G="#10b981",R="#ef4444",A="#f59e0b",B="#3b82f6",P="#8b5cf6",M="#94a3b8";

let sortCol=null,sortDir=1,filterSig="ALL",filterCat="ALL",searchQ="";

function sc(s){{s=(s||"").toUpperCase();if(s.includes("STRONG BUY"))return G;if(s.includes("BUY"))return G;if(s.includes("WATCH"))return A;if(s.includes("HOLD"))return B;return R;}}
function scoreCol(s){{return s>=80?G:s>=65?"#22c55e":s>=50?A:R}}
function chgCol(v){{return parseFloat(v||0)>=0?G:R}}
function fp(v,d=1){{try{{let n=parseFloat(v||0);return(n>=0?"+":"")+n.toFixed(d)+"%"}}catch{{return"N/A"}}}}
function fd(v,d=2){{try{{return parseFloat(v||0).toFixed(d)}}catch{{return"N/A"}}}}
function fB(v){{try{{let n=parseFloat(v||0);return n>0?"$"+n.toFixed(1)+"B":"N/A"}}catch{{return"N/A"}}}}
function catStyle(c){{c=(c||"").toUpperCase();if(c=="GROWTH")return"background:#4c1d95;color:#ddd6fe";if(c=="BALANCED")return"background:#0c4a6e;color:#bae6fd";if(c=="VALUE")return"background:#14532d;color:#bbf7d0";return"background:#374151;color:#e5e7eb"}}
function sigStyle(s){{let c=sc(s);return`background:${{c}}22;color:${{c}};border:1px solid ${{c}}44`}}

function showTab(id,btn){{
  document.querySelectorAll(".section").forEach(s=>s.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach(b=>b.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  btn.classList.add("active");
}}

function renderBadges(){{
  const risk=MACRO.risk_level||"MODERATE";
  const rCol={{LOW:G,MODERATE:A,HIGH:R}}[risk]||M;
  const gr=PICKS.filter(p=>(p.category||"").toUpperCase()=="GROWTH").length;
  document.getElementById("hdr-badges").innerHTML=`
    <div class="badge"><div class="badge-label">Risk</div><div class="badge-val" style="color:${{rCol}}">${{risk}}</div></div>
    <div class="badge"><div class="badge-label">Picks</div><div class="badge-val">${{PICKS.length}}</div></div>
    <div class="badge"><div class="badge-label">G/B</div><div class="badge-val">${{gr}}/${{PICKS.length-gr}}</div></div>
    <div class="badge"><div class="badge-label">VIX</div><div class="badge-val">${{MKT.vix}}</div></div>
  `;
}}

function renderMarket(){{
  const spC=chgCol(MKT.sp),nqC=chgCol(MKT.nq);
  const mC={{BULLISH:G,NEUTRAL:A,BEARISH:R}}[MACRO.market_mood]||M;
  document.getElementById("mkt-bar").innerHTML=`
    <div class="mstat"><div class="mstat-l">Mood</div><div class="mstat-v" style="color:${{mC}}">${{MACRO.market_mood||"N/A"}}</div></div>
    <div class="mstat"><div class="mstat-l">S&P 500</div><div class="mstat-v" style="color:${{spC}}">${{fp(MKT.sp)}}</div></div>
    <div class="mstat"><div class="mstat-l">Nasdaq</div><div class="mstat-v" style="color:${{nqC}}">${{fp(MKT.nq)}}</div></div>
    <div class="macro-text">${{MACRO.macro_summary||""}} <span style="color:#64748b">&nbsp;|&nbsp; ${{MACRO.sector_rotation||""}}</span></div>
  `;
}}

function scoreBar(bd,col){{
  return [["Tech",bd.technical||0,30],["Fund",bd.fundamental||0,25],["Cat",bd.catalyst||0,20],["Macro",bd.macro||0,15],["RR",bd.rr||0,10]]
    .map(([n,v,mx])=>`<div style="margin-bottom:3px"><div style="display:flex;justify-content:space-between;font-size:9px;color:${{M}};margin-bottom:1px"><span>${{n}}</span><span>${{v}}/${{mx}}</span></div><div style="height:3px;background:#334155;border-radius:2px"><div style="height:3px;width:${{Math.round(v/mx*100)}}%;background:${{col}};border-radius:2px"></div></div></div>`).join("");
}}

function renderPickCard(p,idx){{
  const sc2=p.score||0,col=scoreCol(sc2),bd=p.score_breakdown||{{}};
  const chgC=chgCol(p.chg_pct);
  const sd=STOCKS[p.ticker]||{{}};
  return `
  <div class="pick-card" onclick="toggleDetail(this)">
    <div class="card-header">
      <div>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
          <span style="color:${{M}};font-size:10px">#${{idx}}</span>
          <span style="font-size:20px;font-weight:800">${{p.ticker}}</span>
          <span class="tag" style="${{catStyle(p.category)}}">${{p.category}}</span>
        </div>
        <div style="font-size:11px;color:${{M}};margin-top:2px">${{p.name}} &middot; ${{p.sector}}</div>
        <div style="font-size:10px;color:#64748b;margin-top:2px;max-width:200px;white-space:normal">${{sd.desc||""}}</div>
        <span class="signal-badge" style="${{sigStyle(p.signal)}};margin-top:5px;display:inline-block">${{p.signal}}</span>
      </div>
      <div style="text-align:right">
        <div style="font-size:20px;font-weight:700">$${{fd(p.price)}}</div>
        <div style="font-size:11px;font-weight:600;color:${{chgC}}">${{fp(p.chg_pct)}} today</div>
        <div style="font-size:10px;color:${{col}};font-weight:800;margin-top:4px">Score: ${{sc2}}/100</div>
        ${{p.earn?`<div style="font-size:9px;color:${{M}};margin-top:2px">Earn: ${{p.earn}}</div>`:""}}
      </div>
    </div>
    <div style="padding:10px 16px;border-bottom:1px solid var(--border)">
      <div style="display:flex;gap:10px;align-items:flex-start">
        <div style="min-width:50px;text-align:center">
          <div style="font-size:28px;font-weight:800;color:${{col}};line-height:1">${{sc2}}</div>
          <div style="font-size:8px;color:${{M}}">/ 100</div>
        </div>
        <div style="flex:1">${{scoreBar(bd,col)}}</div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid var(--border)">
      ${{[["Entry",[`$${{fd(p.entry_low)}}`,`$${{fd(p.entry_high)}}`].join("--"),B,""],
         ["1M Target",`$${{fd(p.t1m)}}`,G,fp(p.upr_1m)+" "+p.prob_1m+"%"],
         ["6M Target",`$${{fd(p.t6m)}}`,G,fp(p.upr_6m)+" "+p.prob_6m+"%"],
         ["1Y Target",`$${{fd(p.t1y)}}`,parseFloat(p.upr_1y||0)>0?G:R,fp(p.upr_1y)+" "+p.prob_1y+"%"],
         ["Stop Loss",`$${{fd(p.stop)}}`,R,"RR: "+fd(p.rr_ratio,1)+"x"],
         ["Analyst Tgt",`$${{fd(p.atgt)}}`,P,p.nans+" analysts"]]
        .map(([l,v,c,s])=>`<div style="padding:8px;text-align:center;border-right:1px solid var(--border)"><div style="font-size:8px;color:${{M}};text-transform:uppercase;margin-bottom:2px">${{l}}</div><div style="font-size:11px;font-weight:700;color:${{c}}">${{v}}</div>${{s?`<div style="font-size:9px;color:${{M}}">${{s}}</div>`:""}}`)
        .join("")}}
    </div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--border);background:#1a2540">
      ${{[["P/E",fd(p.pe)+"x",""],["Fwd P/E",fd(p.fwd_pe)+"x",""],["Rev G",fp(p.rev_g),parseFloat(p.rev_g||0)>15?G:""],
         ["Gross M",fp(p.gm),""],["Net M",fp(p.nm),""],["RSI",p.rsi,parseFloat(p.rsi||50)>70?A:parseFloat(p.rsi||50)<35?G:""],
         ["Vs 50MA",fp(p.vs50ma),chgCol(p.vs50ma)],["Vs 52Whi",fp(p.vs52h),chgCol(p.vs52h)]]
        .map(([l,v,c])=>`<div style="padding:6px 8px;text-align:center;border-right:1px solid var(--border)"><div style="font-size:8px;color:${{M}};text-transform:uppercase">${{l}}</div><div style="font-size:11px;font-weight:600;color:${{c||"inherit"}}">${{v}}</div>`)
        .join("")}}
    </div>
    <div class="card-detail">
      <div style="margin-bottom:8px;padding:8px;background:var(--card2);border-radius:6px">
        <div style="font-size:9px;font-weight:700;color:${{P}};text-transform:uppercase;margin-bottom:4px">Victor's Thesis</div>
        <div style="color:var(--text)">${{p.why_buy||"N/A"}}</div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
        <div style="padding:8px;background:#052e16;border-radius:6px;border:1px solid #166534">
          <div style="font-size:8px;font-weight:700;color:#4ade80;text-transform:uppercase;margin-bottom:3px">Technical</div>
          <div style="color:#86efac">${{p.technical_read||"N/A"}}</div>
        </div>
        <div style="padding:8px;background:#0c1a3e;border-radius:6px;border:1px solid #1e40af">
          <div style="font-size:8px;font-weight:700;color:#60a5fa;text-transform:uppercase;margin-bottom:3px">Catalyst</div>
          <div style="color:#93c5fd">${{p.catalyst||"N/A"}}</div>
        </div>
        <div style="padding:8px;background:#2d1b00;border-radius:6px;border:1px solid #92400e">
          <div style="font-size:8px;font-weight:700;color:#fbbf24;text-transform:uppercase;margin-bottom:3px">Macro</div>
          <div style="color:#fcd34d">${{p.macro_factor||"N/A"}}</div>
        </div>
      </div>
      <div style="margin-top:8px;padding:8px;background:#1a0a0a;border-radius:6px;border:1px solid #7f1d1d">
        <span style="font-size:8px;font-weight:700;color:${{R}};text-transform:uppercase">Risks: </span>
        <span style="color:#fca5a5">${{p.risks||"N/A"}}</span>
      </div>
      ${{sd.desc?`<div style="margin-top:8px;padding:8px;background:var(--card2);border-radius:6px;font-size:10px;color:${{M}};line-height:1.6"><span style="font-size:8px;font-weight:700;color:${{B}};text-transform:uppercase">About: </span>${{sd.desc}}</div>`:""}}
    </div>
  </div>`;
}}

function toggleDetail(card){{
  card.querySelector(".card-detail").classList.toggle("open");
}}

function renderPicks(){{
  const el=document.getElementById("picks");
  if(!PICKS.length){{el.innerHTML=`<div class="empty" style="margin-top:12px">No high-conviction picks today.</div>`;return;}}
  const gr=PICKS.filter(p=>(p.category||"").toUpperCase()=="GROWTH");
  const ba=PICKS.filter(p=>(p.category||"").toUpperCase()!="GROWTH");
  let html="";
  if(gr.length){{
    html+=`<div class="section-hdr" style="margin-top:8px"><span style="display:inline-block;width:4px;height:22px;background:${{P}};border-radius:2px"></span>Growth Picks</div>
    <div class="section-sub">${{gr.length}} high-conviction -- click card for full thesis</div>
    <div class="picks-grid">${{gr.map((p,i)=>renderPickCard(p,i+1)).join("")}}</div>`;
  }}
  if(ba.length){{
    html+=`<div class="section-hdr" style="margin-top:20px"><span style="display:inline-block;width:4px;height:22px;background:${{B}};border-radius:2px"></span>Balanced Picks</div>
    <div class="section-sub">${{ba.length}} solid setups</div>
    <div class="picks-grid">${{ba.map((p,i)=>renderPickCard(p,i+1)).join("")}}</div>`;
  }}
  el.innerHTML=html;
}}

// WATCHLIST -- sortable, filterable, sector-grouped
function getWatchlistData(){{
  return WATCHLIST.filter(w=>{{
    if(filterSig!="ALL" && w.signal!==filterSig) return false;
    if(filterCat!="ALL" && (w.category||"").toUpperCase()!==filterCat) return false;
    if(searchQ && !(w.ticker||"").includes(searchQ.toUpperCase()) && !(w.name||"").toUpperCase().includes(searchQ.toUpperCase()) && !(w.sector||"").toUpperCase().includes(searchQ.toUpperCase())) return false;
    return true;
  }});
}}

function sortData(data){{
  if(!sortCol) return data;
  return [...data].sort((a,b)=>{{
    let va=a[sortCol],vb=b[sortCol];
    if(typeof va==="string") return sortDir*va.localeCompare(vb||"");
    return sortDir*(parseFloat(va||0)-parseFloat(vb||0));
  }});
}}

function watchlistRow(w){{
  const sc2=w.score||0,col=scoreCol(sc2),chgC=chgCol(w.chg_pct);
  const upr=parseFloat(w.upr_1y||0);
  const sd=STOCKS[w.ticker]||{{}};
  return `<tr>
    <td class="company-cell">
      <div class="company-name">${{w.ticker}}</div>
      <div class="company-sub">${{(w.name||"").substring(0,28)}}</div>
      <div class="company-sub" style="color:#475569">${{w.industry||w.sector||""}}</div>
      <div class="company-desc">${{sd.desc||""}}</div>
      <span class="tag" style="${{catStyle(w.category)}}">${{w.category||""}}</span>
    </td>
    <td><div style="font-weight:700">$${{fd(w.price)}}</div><div style="font-size:10px;color:${{chgC}}">${{fp(w.chg_pct)}}</div></td>
    <td><span class="signal-badge" style="${{sigStyle(w.signal)}}">${{w.signal}}</span></td>
    <td class="score-cell"><div class="score-num" style="color:${{col}}">${{sc2}}</div><div class="score-sub">/ 100</div></td>
    <td style="color:${{B}};font-size:11px">$${{fd(w.entry_low)}} -- $${{fd(w.entry_high)}}</td>
    <td><div style="color:${{upr>0?G:R}};font-weight:700">$${{fd(w.t1y)}}</div><div style="font-size:10px;color:${{upr>0?G:R}}">${{fp(w.upr_1y)}}</div></td>
    <td style="color:${{R}}">$${{fd(w.stop)}}</td>
    <td>${{fd(w.pe)}}x</td>
    <td>${{fd(w.fwd_pe)}}x</td>
    <td style="color:${{parseFloat(w.rev_g||0)>15?G:"inherit"}}">${{fp(w.rev_g)}}</td>
    <td style="color:${{parseFloat(w.gm||0)>50?"#22c55e":"inherit"}}">${{fp(w.gm)}}</td>
    <td style="color:${{parseFloat(w.nm||0)>0?G:R}}">${{fp(w.nm)}}</td>
    <td style="color:${{parseFloat(w.rsi||50)>70?A:parseFloat(w.rsi||50)<35?G:"inherit"}}">${{w.rsi}}</td>
    <td style="color:${{chgCol(w.vs50ma)}}">${{fp(w.vs50ma)}}</td>
    <td style="color:${{chgCol(w.vs200ma)}}">${{fp(w.vs200ma)}}</td>
    <td style="color:${{parseFloat(w.volr||1)>1.3?G:"inherit"}}">${{fd(w.volr)}}x</td>
    <td>$${{fd(w.atgt)}}</td>
    <td>${{w.nans||"?"}}</td>
    <td style="color:${{M}};font-size:11px;font-style:italic;white-space:normal;min-width:180px">${{w.note||""}}</td>
  </tr>`;
}}

function renderWatchlist(){{
  const el=document.getElementById("watchlist");
  const cols=[
    ["company-cell","Stock","ticker"],["price","Price","price"],["signal","Signal","signal"],
    ["score","Score","score"],["entry","Entry Range","entry_low"],["t1y","1Y Target","t1y"],
    ["stop","Stop","stop"],["pe","P/E","pe"],["fwd_pe","Fwd P/E","fwd_pe"],
    ["rev_g","Rev Gr","rev_g"],["gm","Gross M","gm"],["nm","Net M","nm"],
    ["rsi","RSI","rsi"],["vs50ma","Vs 50MA","vs50ma"],["vs200ma","Vs 200MA","vs200ma"],
    ["volr","Vol Ratio","volr"],["atgt","Analyst Tgt","atgt"],["nans","# Analysts","nans"],
    ["note","Victor's Note","note"]
  ];
  const thead=cols.map(([id,label,key])=>
    `<th id="th-${{id}}" onclick="doSort('${{key}}')">${{label}}</th>`
  ).join("");

  const data=sortData(getWatchlistData());

  // Group by sector
  const sectors={{}};
  data.forEach(w=>{{
    const s=w.sector||"Other";
    if(!sectors[s]) sectors[s]=[];
    sectors[s].push(w);
  }});

  let bodyHtml="";
  const sectorIcons={{
    "Technology":"<svg width=12 height=12 viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width=2><rect x=2 y=3 width=20 height=14 rx=2/><line x1=8 y1=21 x2=16 y2=21/><line x1=12 y1=17 x2=12 y2=21/></svg>",
    "Healthcare":"<svg width=12 height=12 viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width=2><path d='M22 12h-4l-3 9L9 3l-3 9H2'/></svg>",
    "Financial Services":"<svg width=12 height=12 viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width=2><line x1=12 y1=1 x2=12 y2=23/><path d='M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6'/></svg>",
    "Consumer Cyclical":"<svg width=12 height=12 viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width=2><circle cx=9 cy=21 r=1/><circle cx=20 cy=21 r=1/><path d='M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6'/></svg>",
  }};

  Object.entries(sectors).sort(([a],[b])=>a.localeCompare(b)).forEach(([sector,rows])=>{{
    const icon=sectorIcons[sector]||"";
    bodyHtml+=`<tr><td colspan="19"><div class="sector-header">${{icon}} ${{sector}} <span style="color:#475569;font-weight:400">(${{rows.length}} stocks)</span></div></td></tr>`;
    bodyHtml+=rows.map(watchlistRow).join("");
  }});

  const signals=["ALL",...new Set(WATCHLIST.map(w=>w.signal).filter(Boolean))];
  const cats=["ALL","GROWTH","BALANCED","VALUE"];
  const filterBtns=signals.map(s=>`<button class="filter-btn ${{filterSig===s?"active":""}}" onclick="setFilter('sig','${{s}}')">${{s}}</button>`).join("");
  const catBtns=cats.map(c=>`<button class="filter-btn ${{filterCat===c?"active":""}}" onclick="setFilter('cat','${{c}}')">${{c}}</button>`).join("");

  el.innerHTML=`
    <div class="section-hdr" style="margin-top:8px"><span style="display:inline-block;width:4px;height:22px;background:${{A}};border-radius:2px"></span>Your Watchlist</div>
    <div class="section-sub">${{WATCHLIST.length}} stocks tracked &middot; click column headers to sort &middot; grouped by sector</div>
    <div class="filter-row">
      <input class="search-box" placeholder="Search ticker / name / sector..." oninput="setSearch(this.value)" value="${{searchQ}}">
      ${{filterBtns}}
      <span style="color:#475569;font-size:10px">|</span>
      ${{catBtns}}
    </div>
    <div class="tbl-wrap">
      <table><thead><tr>${{thead}}</tr></thead><tbody>${{bodyHtml || '<tr><td colspan=19 style="text-align:center;padding:24px;color:#64748b">No stocks match filter</td></tr>'}}</tbody></table>
    </div>`;
  // Re-apply sort indicators
  if(sortCol){{
    const el2=document.querySelector(`th[onclick="doSort('${{sortCol}}')"]`);
    if(el2) el2.classList.add(sortDir>0?"sort-asc":"sort-desc");
  }}
}}

function doSort(col){{
  if(sortCol===col){{sortDir*=-1;}}else{{sortCol=col;sortDir=1;}}
  renderWatchlist();
}}
function setFilter(type,val){{
  if(type==="sig") filterSig=val; else filterCat=val;
  renderWatchlist();
}}
function setSearch(v){{searchQ=v;renderWatchlist();}}

function renderScan(){{
  const el=document.getElementById("scan");
  if(!SCAN.length){{el.innerHTML=`<div class="empty" style="margin-top:12px">No scan data.</div>`;return;}}
  const items=SCAN.map(b=>{{
    const col={{BULLISH:G,BEARISH:R,NEUTRAL:A}}[b.bias]||M;
    return `<div class="brief-chip"><span style="font-weight:800;color:${{col}}">${{b.ticker}}</span><span style="color:${{M}};font-size:10px">${{b.reason||""}}</span></div>`;
  }}).join("");
  el.innerHTML=`<div class="section-hdr" style="margin-top:8px"><span style="display:inline-block;width:4px;height:22px;background:${{M}};border-radius:2px"></span>Full Scan Brief</div>
  <div class="section-sub">${{SCAN.length}} stocks scanned today</div>
  <div class="brief-grid">${{items}}</div>`;
}}

renderBadges(); renderMarket(); renderPicks(); renderWatchlist(); renderScan();
</script>
</body></html>"""

# =============================================================================
# EMAIL
# =============================================================================
def send_email(subject, html_report, picks, mkt, macro):
    growth   = [p for p in picks if str(p.get("category","")).upper()=="GROWTH"]
    balanced = [p for p in picks if str(p.get("category","")).upper()!="GROWTH"]
    risk     = macro.get("risk_level","MODERATE")
    risk_col = {"LOW":"#059669","MODERATE":"#d97706","HIGH":"#dc2626"}.get(risk.upper(),"#6b7280")
    owner    = GITHUB_REPO.split("/")[0] if GITHUB_REPO else ""
    repo     = GITHUB_REPO.split("/")[1] if "/" in GITHUB_REPO else "stock-agent"
    page_url = f"https://{owner}.github.io/{repo}/" if owner else ""

    rows = "".join([f"""<tr>
      <td style="padding:9px 12px;font-weight:700;font-size:13px">{p.get('ticker','')}</td>
      <td style="padding:9px 12px;color:#64748b;font-size:11px">{p.get('name','')[:22]}</td>
      <td style="padding:9px 12px">${p.get('price',0):.2f}</td>
      <td style="padding:9px 12px;font-weight:700;color:{'#059669' if (p.get('score',0))>=80 else '#10b981' if p.get('score',0)>=65 else '#d97706'}">{p.get('score',0)}/100</td>
      <td style="padding:9px 12px;color:#10b981">${p.get('t1y',0):.2f} ({'+' if p.get('upr_1y',0)>=0 else ''}{p.get('upr_1y',0):.1f}%)</td>
      <td style="padding:9px 12px;font-size:10px;color:#64748b;font-style:italic">{str(p.get('why_buy',''))[:55]}...</td>
    </tr>""" for p in picks[:6]])

    link_btn = f"""<div style="text-align:center;margin:20px 0">
      <a href="{page_url}" style="display:inline-block;background:linear-gradient(135deg,#3b82f6,#6366f1);
        color:#fff;text-decoration:none;padding:13px 28px;border-radius:8px;font-size:13px;font-weight:700">
        Open Full Interactive Report
      </a>
      <div style="font-size:10px;color:#94a3b8;margin-top:6px">{page_url}</div>
    </div>""" if page_url else ""

    body = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,sans-serif">
<div style="max-width:680px;margin:0 auto">
  <div style="background:linear-gradient(135deg,#0f172a,#1e3a5f);padding:22px 26px">
    <div style="font-size:9px;color:#475569;text-transform:uppercase;letter-spacing:.15em">Quant Signal Agent</div>
    <div style="font-size:20px;font-weight:800;color:#fff;margin:3px 0">Victor Kane Daily Report</div>
    <div style="font-size:10px;color:#64748b">{TODAY} &middot; {NOW}</div>
    <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
      <span style="padding:4px 10px;background:rgba(255,255,255,.08);border-radius:5px;font-size:10px;font-weight:600;color:{risk_col}">Risk: {risk}</span>
      <span style="padding:4px 10px;background:rgba(255,255,255,.08);border-radius:5px;font-size:10px;color:#fff">{len(picks)} picks ({len(growth)}G/{len(balanced)}B)</span>
      <span style="padding:4px 10px;background:rgba(255,255,255,.08);border-radius:5px;font-size:10px;color:#94a3b8">S&P {'+' if mkt.get('sp',0)>=0 else ''}{mkt.get('sp',0):.2f}% &middot; VIX {mkt.get('vix','?')}</span>
    </div>
  </div>
  <div style="background:#fff;padding:18px 26px">
    <p style="font-size:12px;color:#374151;line-height:1.7;margin:0 0 14px">{macro.get('macro_summary','')}</p>
    {link_btn}
    {'<table style="width:100%;border-collapse:collapse;margin-top:14px"><thead><tr style="background:#f8fafc;border-bottom:2px solid #e2e8f0"><th style="padding:7px 12px;text-align:left;font-size:9px;color:#64748b;text-transform:uppercase">Ticker</th><th style="padding:7px 12px;text-align:left;font-size:9px;color:#64748b;text-transform:uppercase">Company</th><th style="padding:7px 12px;text-align:left;font-size:9px;color:#64748b;text-transform:uppercase">Price</th><th style="padding:7px 12px;text-align:left;font-size:9px;color:#64748b;text-transform:uppercase">Score</th><th style="padding:7px 12px;text-align:left;font-size:9px;color:#64748b;text-transform:uppercase">1Y Target</th><th style="padding:7px 12px;text-align:left;font-size:9px;color:#64748b;text-transform:uppercase">Thesis</th></tr></thead><tbody>' + rows + '</tbody></table>' if picks else '<div style="padding:14px;text-align:center;color:#94a3b8;font-size:12px;background:#f8fafc;border-radius:7px">No high-conviction picks today.</div>'}
    <div style="margin-top:14px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:7px;padding:12px">
      <div style="font-size:10px;font-weight:700;color:#1e40af;margin-bottom:3px">Full report attached as HTML file</div>
      <div style="font-size:10px;color:#3b82f6">Open victor-kane-{TODAY}.html in any browser for interactive dashboard with sortable watchlist, sector grouping, company descriptions</div>
    </div>
  </div>
  <div style="padding:12px 26px;background:#f8fafc;text-align:center;font-size:9px;color:#94a3b8">
    For educational purposes only. Not financial advice. &middot; {NOW}
  </div>
</div></body></html>"""

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(body, "html"))

    att = MIMEBase("text", "html")
    att.set_payload(html_report.encode("utf-8"))
    encoders.encode_base64(att)
    att.add_header("Content-Disposition","attachment",filename=f"victor-kane-{TODAY}.html")
    msg.attach(att)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com",465,context=ctx) as srv:
        srv.login(EMAIL_FROM,EMAIL_PASSWORD)
        srv.sendmail(EMAIL_FROM,EMAIL_TO,msg.as_string())
    print(f"  -> Email + attachment sent to {EMAIL_TO}")

# =============================================================================
# MAIN
# =============================================================================
def main():
    print(f"\n{'='*55}\n  Quant Signal Agent -- {NOW}")
    if ALL_PERSONAL: print(f"  Watchlist: {', '.join(ALL_PERSONAL)}")
    print(f"{'='*55}\n")

    print("[Step 1] Fetching market data...")
    mkt = fetch_market()
    print(f"  -> S&P {mkt['sp']:+.2f}% | Nasdaq {mkt['nq']:+.2f}% | VIX {mkt['vix']:.1f}")

    disc_tickers   = [t for t in DISCOVERY_UNIVERSE if t not in ALL_PERSONAL][:6]
    watch_batches  = [ALL_PERSONAL[i:i+5] for i in range(0, len(ALL_PERSONAL), 5)]
    all_tickers    = list(dict.fromkeys(disc_tickers + ALL_PERSONAL))

    print(f"\n  Discovery: {disc_tickers}")
    print(f"  Watchlist: {ALL_PERSONAL} ({len(watch_batches)} batches of 5)")
    stock_data = fetch_stock_data(all_tickers)

    def to_json(tickers):
        d = {t: {k:v for k,v in stock_data[t].items() if k not in ("desc","website","founded","country","fullname","employees")}
             for t in tickers if t in stock_data and "error" not in stock_data[t]}
        return json.dumps(d, separators=(',',':'))

    print("\n[Step 2a] Discovery scan...")
    d_report   = call_claude(discovery_prompt(to_json(disc_tickers), mkt), "discovery", max_tokens=1400)
    picks      = d_report.get("top_picks", [])
    scan_brief = d_report.get("full_scan_brief", [])
    macro      = {
        "macro_summary":  d_report.get("macro_summary",""),
        "risk_level":     d_report.get("risk_level","MODERATE"),
        "sector_rotation":d_report.get("sector_rotation",""),
        "market_mood":    d_report.get("market_mood","NEUTRAL"),
    }
    print(f"  -> {len(picks)} picks")

    watchlist = []
    for i, batch in enumerate(watch_batches, 1):
        if not batch: continue
        print(f"\n[Step 2{chr(97+i)}] Watchlist batch {i} ({', '.join(batch)})...")
        time.sleep(8)
        wr = call_claude(watchlist_prompt(to_json(batch), mkt), f"watchlist-{i}", max_tokens=1500)
        new_items = wr.get("watchlist", [])
        watchlist += new_items
        print(f"  -> {len(new_items)} stocks (total {len(watchlist)})")

    # Add full stock data (including descriptions) for the HTML
    all_sd_for_html = {t: stock_data[t] for t in all_tickers if t in stock_data}

    print("\n[Step 3] Building interactive report...")
    html = build_html(picks, watchlist, scan_brief, macro, mkt, all_sd_for_html)

    print("[Step 4] Publishing to GitHub docs/index.html...")
    publish_to_github(html)

    growth   = [p for p in picks if str(p.get("category","")).upper()=="GROWTH"]
    balanced = [p for p in picks if str(p.get("category","")).upper()!="GROWTH"]
    mood     = macro.get("market_mood","?")
    risk     = macro.get("risk_level","?")
    subject  = f"Victor Kane {TODAY} | {len(picks)} picks ({len(growth)}G/{len(balanced)}B) | {mood} | Risk:{risk}"

    print("[Step 5] Sending email...")
    send_email(subject, html, picks, mkt, macro)

    print(f"\n{'='*55}\n  Done -- {EMAIL_TO}\n{'='*55}\n")

if __name__ == "__main__":
    main()
