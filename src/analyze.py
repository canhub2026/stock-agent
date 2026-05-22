# -*- coding: utf-8 -*-
"""Quant Signal Agent v5 -- Victor Kane | GitHub Pages + Email Link"""

import os, json, re, urllib.request, urllib.error, smtplib, ssl, time, subprocess, sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
EMAIL_FROM        = os.environ["EMAIL_FROM"]
EMAIL_PASSWORD    = os.environ["EMAIL_PASSWORD"]
EMAIL_TO          = os.environ["EMAIL_TO"]
GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO       = os.environ.get("GITHUB_REPOSITORY", "")  # e.g. canhub2026/stock-agent

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
            results[ticker] = {
                "ticker":ticker,"name":info.get("longName",ticker),"sector":info.get("sector","Unknown"),
                "price":round(price,2),"chg_pct":chg,"mktcap_b":round((info.get("marketCap",0) or 0)/1e9,1),
                "pe":round(info.get("trailingPE",0) or 0,1),"fwd_pe":round(info.get("forwardPE",0) or 0,1),
                "peg":round(info.get("pegRatio",0) or 0,2),"eps":round(info.get("trailingEps",0) or 0,2),
                "eps_g":round((info.get("earningsGrowth",0) or 0)*100,1),
                "rev_g":round((info.get("revenueGrowth",0) or 0)*100,1),
                "gm":round((info.get("grossMargins",0) or 0)*100,1),
                "om":round((info.get("operatingMargins",0) or 0)*100,1),
                "nm":round((info.get("profitMargins",0) or 0)*100,1),
                "roe":round((info.get("returnOnEquity",0) or 0)*100,1),
                "de":round(info.get("debtToEquity",0) or 0,2),
                "cash_b":round((info.get("totalCash",0) or 0)/1e9,1),
                "wk52h":round(wk52h,2),"wk52l":round(float(info.get("fiftyTwoWeekLow",0) or 0),2),
                "vs52h":round((price-wk52h)/wk52h*100,1) if wk52h else 0,
                "rsi":rsi,"vs50ma":round((price-ma50)/ma50*100,1) if ma50 else 0,
                "vs200ma":round((price-ma200)/ma200*100,1) if ma200 else 0,
                "vol":vol_t,"avgvol":vol_a,"volr":round(vol_t/vol_a,2) if vol_a else 1,
                "cons":info.get("recommendationKey","N/A"),
                "atgt":round(info.get("targetMeanPrice",0) or 0,2),
                "nans":int(info.get("numberOfAnalystOpinions",0) or 0),
                "inst":round((info.get("heldPercentInstitutions",0) or 0)*100,1),
                "earn":str((info.get("earningsDate",["N/A"])[0])) if info.get("earningsDate") else "N/A",
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
        print(f"  market error: {e}"); return {"sp":0,"nq":0,"vix":0}

# =============================================================================
# CLAUDE CALLS
# =============================================================================
def call_claude(prompt, label):
    print(f"  -> Claude: {label}...")
    payload = json.dumps({
        "model":"claude-sonnet-4-5","max_tokens":2000,
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
                w = 30*(attempt+1); print(f"  -> retry {attempt+2}/4 in {w}s..."); time.sleep(w); continue
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
        f"Pick 2-3 best BUY setups. Score: technical(30)+fundamental(25)+catalyst(20)+macro(15)+rr(10). Min 65.\n"
        f"GROWTH=rev_g>20%. BALANCED=5-20%.\n"
        f"STRICT word limits: why_buy=25w, technical_read=15w, risks=15w, catalyst=10w, macro_factor=10w.\n\n"
        f"JSON only:\n"
        f'{{"top_picks":[{{"ticker":"","name":"","category":"GROWTH","sector":"",'
        f'"price":0,"chg_pct":0,"signal":"BUY","score":0,'
        f'"score_breakdown":{{"technical":0,"fundamental":0,"catalyst":0,"macro":0,"rr":0}},'
        f'"entry_low":0,"entry_high":0,"t1m":0,"t6m":0,"t1y":0,"stop":0,'
        f'"upr_1m":0,"upr_6m":0,"upr_1y":0,"prob_1m":0,"prob_6m":0,"prob_1y":0,"rr_ratio":0,'
        f'"pe":0,"fwd_pe":0,"peg":0,"eps_g":0,"rev_g":0,"gm":0,"om":0,"nm":0,"roe":0,'
        f'"de":0,"cash_b":0,"mktcap_b":0,"rsi":0,"vs50ma":0,"vs200ma":0,"volr":0,'
        f'"wk52h":0,"wk52l":0,"vs52h":0,"cons":"","atgt":0,"nans":0,"inst":0,"earn":"",'
        f'"why_buy":"","technical_read":"","risks":"","catalyst":"","macro_factor":""}}],'
        f'"macro_summary":"20w max","risk_level":"MODERATE","sector_rotation":"15w max",'
        f'"market_mood":"NEUTRAL",'
        f'"full_scan_brief":[{{"ticker":"","bias":"BULLISH","reason":"5w max"}}]}}'
    )

def watchlist_prompt(data_json, mkt):
    return (
        f"Victor Kane. {TODAY}. S&P{mkt['sp']:+.2f}% Nasdaq{mkt['nq']:+.2f}% VIX{mkt['vix']:.1f}\n"
        f"WATCHLIST:\n{data_json}\n\n"
        f"Score each 0-100. Signal: STRONG BUY/BUY/WATCH/HOLD/AVOID. Entry range, 1y target, stop.\n"
        f"note=20w max, specific numbers only.\n\n"
        f"JSON only:\n"
        f'{{"watchlist":[{{"ticker":"","name":"","category":"GROWTH",'
        f'"price":0,"chg_pct":0,"signal":"WATCH","score":0,'
        f'"entry_low":0,"entry_high":0,"t1y":0,"stop":0,"upr_1y":0,'
        f'"pe":0,"rsi":0,"wk52h":0,"wk52l":0,"atgt":0,"cons":"",'
        f'"note":"20w max"}}]}}'
    )

# =============================================================================
# GITHUB PAGES -- publish HTML report
# =============================================================================
def publish_to_github(html_content):
    """Push index.html to gh-pages branch via GitHub API."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("  -> No GitHub token/repo, skipping Pages publish")
        return None

    import base64
    api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/docs/index.html"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "stock-agent"
    }

    # Get current file SHA if exists (needed for update)
    sha = None
    try:
        req = urllib.request.Request(api, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            existing = json.loads(r.read().decode())
            sha = existing.get("sha")
    except:
        pass

    encoded = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")
    body = {"message": f"Report {TODAY}", "content": encoded, "branch": "main"}
    if sha:
        body["sha"] = sha

    req = urllib.request.Request(api, data=json.dumps(body).encode(), headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"  -> Published to GitHub Pages")
            owner, repo = GITHUB_REPO.split("/")
            return f"https://{owner}.github.io/{repo}/"
    except Exception as e:
        print(f"  -> GitHub Pages publish failed: {e}")
        return None

# =============================================================================
# HTML REPORT BUILDER
# =============================================================================
def build_html(picks, watchlist, scan_brief, macro, mkt):
    picks_json    = json.dumps(picks,    ensure_ascii=False)
    watchlist_json= json.dumps(watchlist,ensure_ascii=False)
    scan_json     = json.dumps(scan_brief,ensure_ascii=False)
    macro_json    = json.dumps(macro,    ensure_ascii=False)
    mkt_json      = json.dumps(mkt,      ensure_ascii=False)
    watchlist_str = ", ".join(ALL_PERSONAL) if ALL_PERSONAL else "none"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Victor Kane -- {TODAY}</title>
<style>
  :root{{--bg:#0f172a;--card:#1e293b;--card2:#263148;--border:#334155;--text:#e2e8f0;--muted:#94a3b8;--green:#10b981;--red:#ef4444;--amber:#f59e0b;--blue:#3b82f6;--purple:#8b5cf6;--indigo:#6366f1}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh}}
  .header{{background:linear-gradient(135deg,#0f172a,#1e3a5f);padding:24px 20px;border-bottom:1px solid var(--border)}}
  .header-inner{{max-width:1100px;margin:0 auto;display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px}}
  .logo{{font-size:10px;color:#475569;letter-spacing:.15em;text-transform:uppercase;margin-bottom:4px}}
  .title{{font-size:24px;font-weight:800;color:#fff;letter-spacing:-.02em}}
  .subtitle{{font-size:11px;color:#64748b;margin-top:4px}}
  .badges{{display:flex;gap:8px;flex-wrap:wrap}}
  .badge{{padding:8px 14px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);border-radius:8px;text-align:center}}
  .badge-label{{font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:.1em;margin-bottom:2px}}
  .badge-val{{font-size:15px;font-weight:800;color:#fff}}
  .market-bar{{background:var(--card);border-bottom:1px solid var(--border);padding:14px 20px}}
  .market-inner{{max-width:1100px;margin:0 auto;display:flex;gap:16px;align-items:center;flex-wrap:wrap}}
  .mstat{{text-align:center;padding:8px 16px;background:var(--card2);border-radius:8px;min-width:80px}}
  .mstat-l{{font-size:9px;color:var(--muted);text-transform:uppercase;margin-bottom:3px}}
  .mstat-v{{font-size:14px;font-weight:700}}
  .macro-text{{font-size:12px;color:var(--muted);flex:1;min-width:200px;line-height:1.6}}
  .nav{{background:var(--card);border-bottom:1px solid var(--border);padding:0 20px;display:flex;gap:0;overflow-x:auto}}
  .nav-btn{{padding:12px 18px;font-size:12px;font-weight:600;color:var(--muted);background:none;border:none;cursor:pointer;border-bottom:3px solid transparent;white-space:nowrap;transition:.2s}}
  .nav-btn.active{{color:var(--blue);border-bottom-color:var(--blue)}}
  .nav-btn:hover{{color:var(--text)}}
  .main{{max-width:1100px;margin:0 auto;padding:20px}}
  .section{{display:none}}.section.active{{display:block}}
  .picks-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;margin-top:16px}}
  .pick-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden;transition:.2s}}
  .pick-card:hover{{border-color:var(--blue);transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.3)}}
  .card-header{{padding:14px 16px;background:var(--card2);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:flex-start}}
  .card-ticker{{font-size:22px;font-weight:800;letter-spacing:-.02em}}
  .card-name{{font-size:11px;color:var(--muted);margin-top:2px}}
  .card-price{{text-align:right}}
  .price-val{{font-size:20px;font-weight:700}}
  .price-chg{{font-size:11px;font-weight:600;margin-top:2px}}
  .signal-badge{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700;margin-top:4px}}
  .cat-badge{{font-size:9px;padding:2px 7px;border-radius:8px;font-weight:700;margin-left:6px}}
  .score-section{{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;gap:12px;align-items:center}}
  .score-num{{font-size:36px;font-weight:800;min-width:54px;text-align:center;line-height:1}}
  .score-sub{{font-size:9px;color:var(--muted);text-align:center;margin-top:2px}}
  .score-bars{{flex:1}}
  .bar-row{{margin-bottom:4px}}
  .bar-labels{{display:flex;justify-content:space-between;font-size:9px;color:var(--muted);margin-bottom:2px}}
  .bar-track{{height:4px;background:var(--border);border-radius:2px}}
  .bar-fill{{height:4px;border-radius:2px;transition:.5s}}
  .targets-grid{{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid var(--border)}}
  .tgt-cell{{padding:10px 8px;text-align:center;border-right:1px solid var(--border)}}
  .tgt-label{{font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}}
  .tgt-val{{font-size:12px;font-weight:700}}
  .tgt-sub{{font-size:9px;color:var(--muted);margin-top:1px}}
  .stats-grid{{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid var(--border)}}
  .stat-cell{{padding:8px;text-align:center;border-right:1px solid var(--border)}}
  .stat-label{{font-size:8px;color:var(--muted);text-transform:uppercase;margin-bottom:2px}}
  .stat-val{{font-size:12px;font-weight:600}}
  .thesis{{padding:14px 16px;border-bottom:1px solid var(--border)}}
  .thesis-title{{font-size:9px;font-weight:700;color:var(--purple);text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px}}
  .thesis-text{{font-size:12px;color:var(--text);line-height:1.7;margin-bottom:10px}}
  .pill-row{{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}}
  .pill{{padding:6px 10px;border-radius:8px;font-size:11px;line-height:1.5;flex:1;min-width:120px}}
  .pill-title{{font-size:8px;font-weight:700;text-transform:uppercase;margin-bottom:3px}}
  .risks-bar{{padding:8px 16px;font-size:11px}}
  .watch-table{{width:100%;border-collapse:collapse;margin-top:12px}}
  .watch-table th{{padding:10px 12px;font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;border-bottom:2px solid var(--border);text-align:left;white-space:nowrap}}
  .watch-table td{{padding:12px;font-size:12px;border-bottom:1px solid var(--border);vertical-align:top}}
  .watch-table tr:hover td{{background:var(--card2)}}
  .tag{{display:inline-block;padding:1px 6px;border-radius:4px;font-size:9px;font-weight:700}}
  .brief-grid{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}}
  .brief-chip{{padding:6px 12px;background:var(--card2);border:1px solid var(--border);border-radius:20px;font-size:12px;display:flex;align-items:center;gap:6px}}
  .brief-reason{{font-size:10px;color:var(--muted)}}
  .empty{{text-align:center;padding:40px;color:var(--muted);font-size:13px;background:var(--card2);border-radius:12px}}
  .section-title{{font-size:16px;font-weight:700;margin-bottom:4px;display:flex;align-items:center;gap:8px}}
  .section-sub{{font-size:11px;color:var(--muted);margin-bottom:16px}}
  .green{{color:var(--green)}}.red{{color:var(--red)}}.amber{{color:var(--amber)}}.blue{{color:var(--blue)}}.muted{{color:var(--muted)}}
  @media(max-width:600px){{.picks-grid{{grid-template-columns:1fr}}.targets-grid{{grid-template-columns:repeat(2,1fr)}}.stats-grid{{grid-template-columns:repeat(2,1fr)}}}}
</style>
</head>
<body>

<div class="header">
  <div class="header-inner">
    <div>
      <div class="logo">Quant Signal Agent</div>
      <div class="title">Victor Kane Daily Report</div>
      <div class="subtitle">{TODAY} &middot; {NOW} &middot; Tracking: {watchlist_str}</div>
    </div>
    <div class="badges" id="header-badges"></div>
  </div>
</div>

<div class="market-bar">
  <div class="market-inner" id="market-bar"></div>
</div>

<nav class="nav">
  <button class="nav-btn active" onclick="showSection('picks')">Top Picks</button>
  <button class="nav-btn" onclick="showSection('watchlist')">Watchlist</button>
  <button class="nav-btn" onclick="showSection('scan')">Full Scan</button>
</nav>

<div class="main">
  <div id="picks" class="section active"></div>
  <div id="watchlist" class="section"></div>
  <div id="scan" class="section"></div>
</div>

<script>
const PICKS     = {picks_json};
const WATCHLIST = {watchlist_json};
const SCAN      = {scan_json};
const MACRO     = {macro_json};
const MKT       = {mkt_json};
const TODAY     = "{TODAY}";

const GREEN="#10b981",RED="#ef4444",AMBER="#f59e0b",BLUE="#3b82f6",PURPLE="#8b5cf6",MUTED="#94a3b8";

function scoreColor(s){{return s>=80?GREEN:s>=65?"#22c55e":s>=50?AMBER:RED}}
function sigColor(s){{s=(s||"").toUpperCase();if(s.includes("STRONG BUY"))return GREEN;if(s.includes("BUY"))return GREEN;if(s.includes("WATCH"))return AMBER;if(s.includes("HOLD"))return BLUE;return RED}}
function chgColor(v){{return parseFloat(v||0)>=0?GREEN:RED}}
function fp(v,d=1){{try{{let n=parseFloat(v||0);return (n>=0?"+":"")+n.toFixed(d)+"%"}}catch{{return"N/A"}}}}
function fd(v,d=2){{try{{return parseFloat(v||0).toFixed(d)}}catch{{return"N/A"}}}}
function catStyle(c){{c=(c||"").toUpperCase();if(c=="GROWTH")return"background:#4c1d95;color:#ddd6fe";if(c=="BALANCED")return"background:#0c4a6e;color:#bae6fd";return"background:#374151;color:#e5e7eb"}}
function sigStyle(s){{let c=sigColor(s);return`background:${{c}}22;color:${{c}};border:1px solid ${{c}}44`}}

function showSection(id){{
  document.querySelectorAll(".section").forEach(s=>s.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach(b=>b.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  event.target.classList.add("active");
}}

function renderBadges(){{
  const risk=MACRO.risk_level||"MODERATE";
  const riskCol={{LOW:GREEN,MODERATE:AMBER,HIGH:RED}}[risk]||MUTED;
  const growth=PICKS.filter(p=>(p.category||"").toUpperCase()=="GROWTH").length;
  const balanced=PICKS.length-growth;
  document.getElementById("header-badges").innerHTML=`
    <div class="badge"><div class="badge-label">Risk</div><div class="badge-val" style="color:${{riskCol}}">${{risk}}</div></div>
    <div class="badge"><div class="badge-label">Top Picks</div><div class="badge-val">${{PICKS.length}}</div></div>
    <div class="badge"><div class="badge-label">G / B</div><div class="badge-val">${{growth}}/${{balanced}}</div></div>
  `;
}}

function renderMarket(){{
  const spCol=chgColor(MKT.sp), nqCol=chgColor(MKT.nq);
  const moodCol={{BULLISH:GREEN,NEUTRAL:AMBER,BEARISH:RED}}[MACRO.market_mood]||MUTED;
  document.getElementById("market-bar").innerHTML=`
    <div class="mstat"><div class="mstat-l">Mood</div><div class="mstat-v" style="color:${{moodCol}}">${{MACRO.market_mood||"N/A"}}</div></div>
    <div class="mstat"><div class="mstat-l">VIX</div><div class="mstat-v">${{MKT.vix||"N/A"}}</div></div>
    <div class="mstat"><div class="mstat-l">S&P 500</div><div class="mstat-v" style="color:${{spCol}}">${{fp(MKT.sp)}}</div></div>
    <div class="mstat"><div class="mstat-l">Nasdaq</div><div class="mstat-v" style="color:${{nqCol}}">${{fp(MKT.nq)}}</div></div>
    <div class="macro-text">${{MACRO.macro_summary||""}} <span style="color:${{MUTED}}">${{MACRO.sector_rotation||""}}</span></div>
  `;
}}

function scoreBar(bd, col){{
  return [["Technical",bd.technical||0,30],["Fundamental",bd.fundamental||0,25],
          ["Catalyst",bd.catalyst||0,20],["Macro",bd.macro||0,15],["R/R",bd.rr||0,10]]
    .map(([n,v,mx])=>`
      <div class="bar-row">
        <div class="bar-labels"><span>${{n}}</span><span style="color:${{col}}">${{v}}/${{mx}}</span></div>
        <div class="bar-track"><div class="bar-fill" style="width:${{Math.round(v/mx*100)}}%;background:${{col}}"></div></div>
      </div>`).join("");
}}

function renderPick(p, idx){{
  const sc=p.score||0, col=scoreColor(sc);
  const bd=p.score_breakdown||{{}};
  const chgC=chgColor(p.chg_pct);
  const upr1yC=(p.upr_1y||0)>0?GREEN:RED;
  return `
  <div class="pick-card">
    <div class="card-header">
      <div>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
          <span style="color:${{MUTED}};font-size:11px">#${{idx}}</span>
          <span class="card-ticker">${{p.ticker}}</span>
          <span class="cat-badge" style="${{catStyle(p.category)}}">${{p.category}}</span>
        </div>
        <div class="card-name">${{p.name}} &middot; ${{p.sector}}</div>
        <span class="signal-badge" style="${{sigStyle(p.signal)}}">${{p.signal}}</span>
      </div>
      <div class="card-price">
        <div class="price-val">$${{fd(p.price)}}</div>
        <div class="price-chg" style="color:${{chgC}}">${{fp(p.chg_pct)}} today</div>
        ${{p.earn?`<div style="font-size:10px;color:${{MUTED}};margin-top:2px">Earn: ${{p.earn}}</div>`:""}}</div>
    </div>
    <div class="score-section">
      <div>
        <div class="score-num" style="color:${{col}}">${{sc}}</div>
        <div class="score-sub">/100</div>
      </div>
      <div class="score-bars">${{scoreBar(bd,col)}}</div>
    </div>
    <div class="targets-grid">
      <div class="tgt-cell"><div class="tgt-label">Entry</div><div class="tgt-val" style="color:${{BLUE}}">$${{fd(p.entry_low)}}--$${{fd(p.entry_high)}}</div></div>
      <div class="tgt-cell"><div class="tgt-label">1-Month</div><div class="tgt-val" style="color:${{GREEN}}">$${{fd(p.t1m)}}</div><div class="tgt-sub">${{fp(p.upr_1m)}} &middot; ${{p.prob_1m||"?"}}%</div></div>
      <div class="tgt-cell"><div class="tgt-label">6-Month</div><div class="tgt-val" style="color:${{GREEN}}">$${{fd(p.t6m)}}</div><div class="tgt-sub">${{fp(p.upr_6m)}} &middot; ${{p.prob_6m||"?"}}%</div></div>
      <div class="tgt-cell" style="border-right:none"><div class="tgt-label">1-Year</div><div class="tgt-val" style="color:${{upr1yC}}">$${{fd(p.t1y)}}</div><div class="tgt-sub">${{fp(p.upr_1y)}} &middot; RR ${{fd(p.rr_ratio,1)}}x</div></div>
      <div class="tgt-cell"><div class="tgt-label">Stop Loss</div><div class="tgt-val" style="color:${{RED}}">$${{fd(p.stop)}}</div></div>
      <div class="tgt-cell"><div class="tgt-label">Analyst Target</div><div class="tgt-val" style="color:${{PURPLE}}">$${{fd(p.atgt)}}</div><div class="tgt-sub">${{p.nans||"?"}} analysts</div></div>
    </div>
    <div class="stats-grid">
      <div class="stat-cell"><div class="stat-label">P/E</div><div class="stat-val">${{fd(p.pe)}}x</div></div>
      <div class="stat-cell"><div class="stat-label">Fwd P/E</div><div class="stat-val">${{fd(p.fwd_pe)}}x</div></div>
      <div class="stat-cell"><div class="stat-label">Rev Growth</div><div class="stat-val" style="color:${{parseFloat(p.rev_g||0)>15?GREEN:"inherit"}}">${{fp(p.rev_g)}}</div></div>
      <div class="stat-cell"><div class="stat-label">EPS Growth</div><div class="stat-val" style="color:${{parseFloat(p.eps_g||0)>0?GREEN:RED}}">${{fp(p.eps_g)}}</div></div>
      <div class="stat-cell"><div class="stat-label">Gross Margin</div><div class="stat-val">${{fp(p.gm)}}</div></div>
      <div class="stat-cell"><div class="stat-label">Net Margin</div><div class="stat-val">${{fp(p.nm)}}</div></div>
      <div class="stat-cell"><div class="stat-label">RSI (14)</div><div class="stat-val" style="color:${{parseFloat(p.rsi||50)>70?AMBER:parseFloat(p.rsi||50)<35?GREEN:"inherit"}}">${{p.rsi}}</div></div>
      <div class="stat-cell"><div class="stat-label">Vs 50MA</div><div class="stat-val" style="color:${{chgColor(p.vs50ma)}}">${{fp(p.vs50ma)}}</div></div>
      <div class="stat-cell"><div class="stat-label">Vs 200MA</div><div class="stat-val" style="color:${{chgColor(p.vs200ma)}}">${{fp(p.vs200ma)}}</div></div>
      <div class="stat-cell"><div class="stat-label">Mkt Cap</div><div class="stat-val">$${{fd(p.mktcap_b,0)}}B</div></div>
      <div class="stat-cell"><div class="stat-label">52W High</div><div class="stat-val">$${{fd(p.wk52h)}}</div></div>
      <div class="stat-cell"><div class="stat-label">Vs 52W Hi</div><div class="stat-val" style="color:${{chgColor(p.vs52h)}}">${{fp(p.vs52h)}}</div></div>
    </div>
    <div class="thesis">
      <div class="thesis-title">Victor Kane's Investment Thesis</div>
      <div class="thesis-text">${{p.why_buy||"N/A"}}</div>
      <div class="pill-row">
        <div class="pill" style="background:#052e16;border:1px solid #166534;color:#86efac">
          <div class="pill-title" style="color:#4ade80">Technical Setup</div>
          ${{p.technical_read||"N/A"}}
        </div>
        <div class="pill" style="background:#0c1a3e;border:1px solid #1e40af;color:#93c5fd">
          <div class="pill-title" style="color:#60a5fa">Key Catalyst</div>
          ${{p.catalyst||"N/A"}}
        </div>
        <div class="pill" style="background:#2d1b00;border:1px solid #92400e;color:#fcd34d">
          <div class="pill-title" style="color:#fbbf24">Macro Tailwind</div>
          ${{p.macro_factor||"N/A"}}
        </div>
      </div>
    </div>
    <div class="risks-bar" style="background:#1a0a0a;border-top:1px solid #7f1d1d">
      <span style="font-size:9px;font-weight:700;color:#ef4444;text-transform:uppercase">Risks: </span>
      <span style="color:#fca5a5;font-size:11px">${{p.risks||"N/A"}}</span>
    </div>
  </div>`;
}}

function renderPicks(){{
  const el = document.getElementById("picks");
  if(!PICKS.length){{
    el.innerHTML=`<div class="empty" style="margin-top:16px">No high-conviction picks today -- market conditions not ideal.</div>`;return;
  }}
  const growth=PICKS.filter(p=>(p.category||"").toUpperCase()=="GROWTH");
  const balanced=PICKS.filter(p=>(p.category||"").toUpperCase()!="GROWTH");
  let html="";
  if(growth.length){{
    html+=`<div class="section-title" style="margin-top:8px"><span style="display:inline-block;width:4px;height:24px;background:${{PURPLE}};border-radius:2px"></span>Growth Picks</div>
    <div class="section-sub">${{growth.length}} high-conviction growth setups</div>
    <div class="picks-grid">${{growth.map((p,i)=>renderPick(p,i+1)).join("")}}</div>`;
  }}
  if(balanced.length){{
    html+=`<div class="section-title" style="margin-top:24px"><span style="display:inline-block;width:4px;height:24px;background:${{BLUE}};border-radius:2px"></span>Balanced Picks</div>
    <div class="section-sub">${{balanced.length}} solid setups with lower volatility</div>
    <div class="picks-grid">${{balanced.map((p,i)=>renderPick(p,i+1)).join("")}}</div>`;
  }}
  el.innerHTML=html;
}}

function renderWatchlist(){{
  const el=document.getElementById("watchlist");
  if(!WATCHLIST.length){{el.innerHTML=`<div class="empty" style="margin-top:16px">No watchlist data.</div>`;return;}}
  const rows=WATCHLIST.map(w=>{{
    const sc=w.score||0,col=scoreColor(sc),chgC=chgColor(w.chg_pct);
    const upr=parseFloat(w.upr_1y||0);
    return `<tr>
      <td>
        <div style="font-size:16px;font-weight:800">${{w.ticker}}</div>
        <div style="font-size:10px;color:${{MUTED}}">${{(w.name||"").substring(0,25)}}</div>
        <span class="cat-badge" style="${{catStyle(w.category)}}">${{w.category}}</span>
      </td>
      <td>
        <div style="font-size:15px;font-weight:700">$${{fd(w.price)}}</div>
        <div style="font-size:11px;color:${{chgC}}">${{fp(w.chg_pct)}}</div>
      </td>
      <td><span class="signal-badge" style="${{sigStyle(w.signal)}}">${{w.signal}}</span></td>
      <td>
        <div style="font-size:18px;font-weight:800;color:${{col}}">${{sc}}</div>
        <div style="font-size:9px;color:${{MUTED}}">/ 100</div>
      </td>
      <td style="color:${{BLUE}}">$${{fd(w.entry_low)}} -- $${{fd(w.entry_high)}}</td>
      <td>
        <div style="color:${{upr>0?GREEN:RED}};font-weight:700">$${{fd(w.t1y)}}</div>
        <div style="font-size:10px;color:${{upr>0?GREEN:RED}}">${{fp(w.upr_1y)}}</div>
      </td>
      <td style="color:${{RED}}">$${{fd(w.stop)}}</td>
      <td>${{fd(w.pe)}}x</td>
      <td style="color:${{parseFloat(w.rsi||50)>70?AMBER:parseFloat(w.rsi||50)<35?GREEN:"inherit"}}">${{w.rsi}}</td>
      <td style="color:${{PURPLE}}">$${{fd(w.atgt)}}</td>
      <td style="color:${{MUTED}};font-size:11px;font-style:italic">${{w.note||""}}</td>
    </tr>`;
  }}).join("");
  el.innerHTML=`
    <div class="section-title" style="margin-top:8px"><span style="display:inline-block;width:4px;height:24px;background:${{AMBER}};border-radius:2px"></span>Your Watchlist</div>
    <div class="section-sub">${{WATCHLIST.length}} stocks tracked daily</div>
    <div style="overflow-x:auto">
    <table class="watch-table">
      <thead><tr>
        <th>Stock</th><th>Price</th><th>Signal</th><th>Score</th>
        <th>Entry Range</th><th>1Y Target</th><th>Stop</th>
        <th>P/E</th><th>RSI</th><th>Analyst Tgt</th><th>Victor's Note</th>
      </tr></thead>
      <tbody>${{rows}}</tbody>
    </table></div>`;
}}

function renderScan(){{
  const el=document.getElementById("scan");
  if(!SCAN.length){{el.innerHTML=`<div class="empty" style="margin-top:16px">No scan data.</div>`;return;}}
  const items=SCAN.map(b=>{{
    const col={{BULLISH:GREEN,BEARISH:RED,NEUTRAL:AMBER}}[b.bias]||MUTED;
    return `<div class="brief-chip">
      <span style="font-weight:800;color:${{col}}">${{b.ticker}}</span>
      <span class="brief-reason">${{b.reason||""}}</span>
    </div>`;
  }}).join("");
  el.innerHTML=`
    <div class="section-title" style="margin-top:8px"><span style="display:inline-block;width:4px;height:24px;background:${{MUTED}};border-radius:2px"></span>Full Scan Brief</div>
    <div class="section-sub">All stocks scanned today</div>
    <div class="brief-grid">${{items}}</div>`;
}}

renderBadges();
renderMarket();
renderPicks();
renderWatchlist();
renderScan();
</script>
</body></html>"""

# =============================================================================
# SEND EMAIL WITH LINK
# =============================================================================
def send_email(subject, url, picks, mkt, macro):
    growth   = [p for p in picks if str(p.get("category","")).upper()=="GROWTH"]
    balanced = [p for p in picks if str(p.get("category","")).upper()!="GROWTH"]
    risk     = macro.get("risk_level","MODERATE")
    risk_col = {"LOW":"#059669","MODERATE":"#d97706","HIGH":"#dc2626"}.get(risk.upper(),"#6b7280")

    top_picks_html = ""
    for p in picks[:5]:
        sc  = p.get("score",0)
        col = "#059669" if sc>=80 else "#10b981" if sc>=65 else "#d97706"
        top_picks_html += f"""
        <tr>
          <td style="padding:10px 12px;font-weight:700;font-size:14px">{p.get('ticker','')}</td>
          <td style="padding:10px 12px;color:#64748b;font-size:12px">{p.get('name','')[:25]}</td>
          <td style="padding:10px 12px;font-size:12px">${p.get('price',0):.2f}</td>
          <td style="padding:10px 12px"><span style="font-weight:700;color:{col}">{sc}/100</span></td>
          <td style="padding:10px 12px;color:#10b981;font-size:12px">${p.get('t1y',0):.2f} ({'+' if p.get('upr_1y',0)>=0 else ''}{p.get('upr_1y',0):.1f}%)</td>
          <td style="padding:10px 12px;font-size:11px;color:#64748b;font-style:italic">{str(p.get('why_buy',''))[:60]}...</td>
        </tr>"""

    link_section = ""
    if url:
        link_section = f"""
        <div style="text-align:center;margin:24px 0">
          <a href="{url}" style="display:inline-block;background:linear-gradient(135deg,#3b82f6,#6366f1);
            color:#fff;text-decoration:none;padding:14px 32px;border-radius:8px;font-size:14px;font-weight:700;
            letter-spacing:.02em">Open Full Interactive Report</a>
          <div style="font-size:11px;color:#94a3b8;margin-top:8px">{url}</div>
        </div>"""

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif">
  <div style="max-width:700px;margin:0 auto">
    <div style="background:linear-gradient(135deg,#0f172a,#1e3a5f);padding:24px 28px;border-radius:0 0 0 0">
      <div style="font-size:10px;color:#475569;text-transform:uppercase;letter-spacing:.15em;margin-bottom:3px">Quant Signal Agent</div>
      <div style="font-size:22px;font-weight:800;color:#fff">Victor Kane Daily Report</div>
      <div style="font-size:11px;color:#64748b;margin-top:3px">{TODAY} &middot; {NOW}</div>
      <div style="display:flex;gap:10px;margin-top:12px;flex-wrap:wrap">
        <span style="padding:5px 12px;background:rgba(255,255,255,.08);border-radius:6px;font-size:11px;font-weight:600;color:{risk_col}">Risk: {risk}</span>
        <span style="padding:5px 12px;background:rgba(255,255,255,.08);border-radius:6px;font-size:11px;color:#fff">{len(picks)} picks</span>
        <span style="padding:5px 12px;background:rgba(255,255,255,.08);border-radius:6px;font-size:11px;color:#94a3b8">S&P {'+' if mkt.get('sp',0)>=0 else ''}{mkt.get('sp',0):.2f}% &middot; VIX {mkt.get('vix','?')}</span>
      </div>
    </div>
    <div style="background:#fff;padding:20px 28px">
      <p style="font-size:13px;color:#374151;line-height:1.7;margin:0 0 16px">{macro.get('macro_summary','')}</p>
      {link_section}
      {"<div style='margin:20px 0'><div style='font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px'>Today Top Picks</div><table style='width:100%;border-collapse:collapse'><thead><tr style='background:#f8fafc;border-bottom:2px solid #e2e8f0'><th style='padding:8px 12px;text-align:left;font-size:10px;color:#64748b;text-transform:uppercase'>Ticker</th><th style='padding:8px 12px;text-align:left;font-size:10px;color:#64748b;text-transform:uppercase'>Company</th><th style='padding:8px 12px;text-align:left;font-size:10px;color:#64748b;text-transform:uppercase'>Price</th><th style='padding:8px 12px;text-align:left;font-size:10px;color:#64748b;text-transform:uppercase'>Score</th><th style='padding:8px 12px;text-align:left;font-size:10px;color:#64748b;text-transform:uppercase'>1Y Target</th><th style='padding:8px 12px;text-align:left;font-size:10px;color:#64748b;text-transform:uppercase'>Thesis</th></tr></thead><tbody>" + top_picks_html + "</tbody></table></div>" if picks else "<div style='padding:16px;text-align:center;color:#94a3b8;font-size:13px;background:#f8fafc;border-radius:8px'>No high-conviction picks today.</div>"}
    </div>
    <div style="padding:14px 28px;background:#f8fafc;border-top:1px solid #e2e8f0;text-align:center">
      <div style="font-size:10px;color:#94a3b8;line-height:1.7">For educational purposes only. Not financial advice.<br>Data: yfinance &middot; Analysis: Claude AI &middot; {NOW}</div>
    </div>
  </div>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html, "html"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as srv:
        srv.login(EMAIL_FROM, EMAIL_PASSWORD)
        srv.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    print(f"  -> Email sent to {EMAIL_TO}")

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
    watch_tickers  = ALL_PERSONAL[:8]
    watch_tickers2 = ALL_PERSONAL[8:14]
    all_tickers    = list(dict.fromkeys(disc_tickers + watch_tickers + watch_tickers2))

    print(f"\n  Discovery: {disc_tickers}")
    print(f"  Watchlist: {watch_tickers + watch_tickers2}")
    stock_data = fetch_stock_data(all_tickers)

    def to_json(tickers):
        d = {t: stock_data[t] for t in tickers if t in stock_data and "error" not in stock_data[t]}
        return json.dumps(d, separators=(',',':'))

    print("\n[Step 2a] Discovery -- Victor Kane finding top picks...")
    d_report   = call_claude(discovery_prompt(to_json(disc_tickers), mkt), "discovery")
    picks      = d_report.get("top_picks", [])
    scan_brief = d_report.get("full_scan_brief", [])
    macro      = {
        "macro_summary":  d_report.get("macro_summary",""),
        "risk_level":     d_report.get("risk_level","MODERATE"),
        "sector_rotation":d_report.get("sector_rotation",""),
        "market_mood":    d_report.get("market_mood","NEUTRAL"),
    }
    print(f"  -> {len(picks)} picks, {len(scan_brief)} scan items")

    watchlist = []
    if watch_tickers:
        print("\n[Step 2b] Watchlist batch 1...")
        time.sleep(8)
        w1 = call_claude(watchlist_prompt(to_json(watch_tickers), mkt), "watchlist-1")
        watchlist += w1.get("watchlist", [])
        print(f"  -> {len(watchlist)} stocks")

    if watch_tickers2:
        print("\n[Step 2c] Watchlist batch 2...")
        time.sleep(8)
        w2 = call_claude(watchlist_prompt(to_json(watch_tickers2), mkt), "watchlist-2")
        watchlist += w2.get("watchlist", [])
        print(f"  -> {len(watchlist)} total")

    print("\n[Step 3] Building interactive HTML report...")
    html = build_html(picks, watchlist, scan_brief, macro, mkt)

    url = publish_to_github(html)
    if url:
        print(f"  -> Live at: {url}")

    growth   = [p for p in picks if str(p.get("category","")).upper()=="GROWTH"]
    balanced = [p for p in picks if str(p.get("category","")).upper()!="GROWTH"]
    mood     = macro.get("market_mood","?")
    risk     = macro.get("risk_level","?")
    subject  = f"Victor Kane {TODAY} | {len(picks)} picks ({len(growth)}G/{len(balanced)}B) | {mood} | Risk:{risk}"

    print("\n[Step 4] Sending email...")
    send_email(subject, url, picks, mkt, macro)

    print(f"\n{'='*55}\n  Done -- sent to {EMAIL_TO}\n{'='*55}\n")

if __name__ == "__main__":
    main()
