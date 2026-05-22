# -*- coding: utf-8 -*-
"""Quant Signal Agent v7 -- Victor Kane | Always shows top 10 | Robinhood-style data"""

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
GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN","")
GITHUB_REPO       = os.environ.get("GITHUB_REPOSITORY","")

_raw  = os.environ.get("PERSONAL_WATCHLIST","")
_extra= os.environ.get("EXTRA_TICKERS","")
PERSONAL_WATCHLIST = [t.strip().upper() for t in _raw.split(",")   if t.strip()]
EXTRA_TICKERS      = [t.strip().upper() for t in _extra.split(",") if t.strip()]
ALL_PERSONAL       = list(dict.fromkeys(PERSONAL_WATCHLIST + EXTRA_TICKERS))

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# Broad universe covering key themes: AI, cybersecurity, semis, cloud, healthcare, financials
UNIVERSE = [
    # AI & Chips
    "NVDA","AMD","AVGO","TSM","ARM","SMCI","INTC","QCOM","MRVL",
    # Cybersecurity
    "CRWD","PANW","ZS","FTNT","OKTA","S","CYBR",
    # Cloud & Software
    "MSFT","GOOGL","AMZN","META","ORCL","SNOW","DDOG","MDB","NOW",
    # Growth Tech
    "PLTR","UBER","SHOP","COIN","SQ","RBLX",
    # Healthcare & Biotech
    "LLY","UNH","ABBV","ISRG","MRNA",
    # Financials
    "JPM","GS","V","MA",
    # Industrial & Defense
    "CAT","GE","RTX","LMT",
]

# =============================================================================
# DATA FETCHING
# =============================================================================
def install_yf():
    subprocess.check_call([sys.executable,"-m","pip","install","yfinance","--quiet","--break-system-packages"])

def fetch_data(tickers):
    try: import yfinance as yf
    except ImportError: install_yf(); import yfinance as yf
    results = {}
    print(f"  -> Fetching {len(tickers)} tickers...")
    for ticker in tickers:
        try:
            t    = yf.Ticker(ticker)
            info = t.info or {}
            hist = t.history(period="1y",interval="1d")
            price= float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
            prev = float(info.get("previousClose") or price)
            chg  = round((price-prev)/prev*100,2) if prev else 0
            rsi  = 50
            if len(hist)>=15:
                d=hist["Close"].diff()
                g=d.clip(lower=0).rolling(14).mean()
                l=(-d.clip(upper=0)).rolling(14).mean()
                rs=g/l.replace(0,0.0001)
                r=100-(100/(1+rs))
                rsi=round(float(r.iloc[-1]),1) if not r.empty else 50
            ma50 =round(float(hist["Close"].rolling(50).mean().iloc[-1]),2)  if len(hist)>=50  else 0
            ma200=round(float(hist["Close"].rolling(200).mean().iloc[-1]),2) if len(hist)>=200 else 0
            vol_t=int(hist["Volume"].iloc[-1])        if not hist.empty else 0
            vol_a=int(hist["Volume"].tail(30).mean()) if len(hist)>=30  else 0
            wk52h=float(info.get("fiftyTwoWeekHigh",price) or price)
            wk52l=float(info.get("fiftyTwoWeekLow",0) or 0)
            desc =info.get("longBusinessSummary","")
            if desc:
                sents=desc.replace("  "," ").split(". ")
                desc =". ".join(sents[:2])+"."
                if len(desc)>220: desc=desc[:220]+"..."
            results[ticker]={
                "ticker":ticker,"name":info.get("shortName",ticker),
                "fullname":info.get("longName",ticker),
                "sector":info.get("sector","Unknown"),"industry":info.get("industry","Unknown"),
                "desc":desc,"website":info.get("website",""),
                "employees":info.get("fullTimeEmployees",0) or 0,
                "price":round(price,2),"chg_pct":chg,
                "mktcap_b":round((info.get("marketCap",0) or 0)/1e9,1),
                "pe":round(info.get("trailingPE",0) or 0,1),
                "fwd_pe":round(info.get("forwardPE",0) or 0,1),
                "peg":round(info.get("pegRatio",0) or 0,2),
                "ps":round(info.get("priceToSalesTrailing12Months",0) or 0,1),
                "pb":round(info.get("priceToBook",0) or 0,1),
                "eps":round(info.get("trailingEps",0) or 0,2),
                "eps_g":round((info.get("earningsGrowth",0) or 0)*100,1),
                "rev_g":round((info.get("revenueGrowth",0) or 0)*100,1),
                "rev_b":round((info.get("totalRevenue",0) or 0)/1e9,1),
                "gm":round((info.get("grossMargins",0) or 0)*100,1),
                "om":round((info.get("operatingMargins",0) or 0)*100,1),
                "nm":round((info.get("profitMargins",0) or 0)*100,1),
                "roe":round((info.get("returnOnEquity",0) or 0)*100,1),
                "de":round(info.get("debtToEquity",0) or 0,2),
                "cash_b":round((info.get("totalCash",0) or 0)/1e9,1),
                "fcf_b":round((info.get("freeCashflow",0) or 0)/1e9,1),
                "beta":round(info.get("beta",0) or 0,2),
                "div_yield":round((info.get("dividendYield",0) or 0)*100,2),
                "short_pct":round((info.get("shortPercentOfFloat",0) or 0)*100,1),
                "wk52h":round(wk52h,2),"wk52l":round(wk52l,2),
                "vs52h":round((price-wk52h)/wk52h*100,1) if wk52h else 0,
                "vs52l":round((price-wk52l)/wk52l*100,1) if wk52l else 0,
                "rsi":rsi,"vs50ma":round((price-ma50)/ma50*100,1) if ma50 else 0,
                "vs200ma":round((price-ma200)/ma200*100,1) if ma200 else 0,
                "vol":vol_t,"avgvol":vol_a,"volr":round(vol_t/vol_a,2) if vol_a else 1,
                "cons":info.get("recommendationKey","N/A"),
                "atgt":round(info.get("targetMeanPrice",0) or 0,2),
                "atgt_hi":round(info.get("targetHighPrice",0) or 0,2),
                "atgt_lo":round(info.get("targetLowPrice",0) or 0,2),
                "nans":int(info.get("numberOfAnalystOpinions",0) or 0),
                "inst":round((info.get("heldPercentInstitutions",0) or 0)*100,1),
                "insider_pct":round((info.get("heldPercentInsiders",0) or 0)*100,1),
                "earn":str((info.get("earningsDate",["N/A"])[0])) if info.get("earningsDate") else "N/A",
            }
            print(f"    ok {ticker}: ${price:.2f} RSI:{rsi} PE:{results[ticker]['pe']} RevG:{results[ticker]['rev_g']}%")
        except Exception as e:
            print(f"    fail {ticker}: {e}")
            results[ticker]={"ticker":ticker,"name":ticker,"sector":"Unknown","industry":"Unknown","desc":"","price":0,"chg_pct":0,"error":str(e)}
    return results

def fetch_market():
    try:
        import yfinance as yf
        spy=yf.Ticker("SPY").history(period="2d")
        qqq=yf.Ticker("QQQ").history(period="2d")
        vix=yf.Ticker("^VIX").history(period="1d")
        sp =round((spy["Close"].iloc[-1]-spy["Close"].iloc[-2])/spy["Close"].iloc[-2]*100,2) if len(spy)>=2 else 0
        nq =round((qqq["Close"].iloc[-1]-qqq["Close"].iloc[-2])/qqq["Close"].iloc[-2]*100,2) if len(qqq)>=2 else 0
        vx =round(float(vix["Close"].iloc[-1]),2) if not vix.empty else 0
        return {"sp":sp,"nq":nq,"vix":vx}
    except Exception as e:
        print(f"  market error: {e}"); return {"sp":0,"nq":0,"vix":0}

# =============================================================================
# CLAUDE
# =============================================================================
def call_claude(prompt, label, max_tokens=1600):
    print(f"  -> Claude: {label}...")
    payload=json.dumps({"model":"claude-sonnet-4-5","max_tokens":max_tokens,"messages":[{"role":"user","content":prompt}]}).encode("utf-8")
    req=urllib.request.Request("https://api.anthropic.com/v1/messages",data=payload,
        headers={"Content-Type":"application/json","x-api-key":ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01"},method="POST")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req,timeout=120) as resp:
                data=json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            body=e.read().decode("utf-8")
            print(f"  x {e.code}: {body[:120]}")
            if e.code in (429,500,502,503,529) and attempt<3:
                w=30*(attempt+1); print(f"  -> retry in {w}s..."); time.sleep(w); continue
            return {}
        except Exception as e:
            print(f"  x {e}")
            if attempt<3: time.sleep(30); continue
            return {}
    text="".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text").strip()
    text=re.sub(r"^```(?:json)?\s*","",text,flags=re.MULTILINE)
    text=re.sub(r"\s*```$","",text,flags=re.MULTILINE)
    s=text.find("{"); e2=text.rfind("}")+1
    if s==-1: print(f"  x no JSON: {text[:150]}"); return {}
    js=re.sub(r",\s*([}\]])",r"\1",text[s:e2])
    try: return json.loads(js)
    except json.JSONDecodeError as ex:
        print(f"  x JSON err pos {ex.pos}: ...{js[max(0,ex.pos-40):ex.pos+40]}...")
        return {}

SCORE_SCHEMA = (
    '{"ticker":"","name":"","category":"GROWTH","sector":"","industry":"",'
    '"price":0,"chg_pct":0,"signal":"BUY","score":0,'
    '"score_breakdown":{"technical":0,"fundamental":0,"catalyst":0,"macro":0,"rr":0},'
    '"entry_low":0,"entry_high":0,"t1m":0,"t6m":0,"t1y":0,"stop":0,'
    '"upr_1m":0,"upr_6m":0,"upr_1y":0,"prob_1m":0,"prob_6m":0,"prob_1y":0,"rr_ratio":0,'
    '"pe":0,"fwd_pe":0,"rev_g":0,"gm":0,"nm":0,"mktcap_b":0,'
    '"rsi":0,"vs50ma":0,"vs200ma":0,"wk52h":0,"wk52l":0,"vs52h":0,'
    '"cons":"","atgt":0,"nans":0,"earn":"",'
    '"theme":"AI|Cybersecurity|Cloud|Healthcare|Fintech|Industrial|Other",'
    '"why_buy":"","technical_read":"","risks":"","catalyst":"","macro_factor":""}'
)

def score_prompt(data_json, mkt, task):
    return (
        f"Victor Kane, quant analyst. {TODAY}. S&P{mkt['sp']:+.2f}% Nasdaq{mkt['nq']:+.2f}% VIX{mkt['vix']:.1f}\n"
        f"{task}\n"
        f"DATA:\n{data_json}\n\n"
        f"Score each stock 0-100: technical(30)+fundamental(25)+catalyst(20)+macro(15)+rr(10).\n"
        f"GROWTH=rev_g>20%. BALANCED=5-20%. VALUE=stable+dividend.\n"
        f"Consider megatrends: AI infrastructure, cybersecurity spend, cloud migration, GLP-1 drugs.\n"
        f"ALL text fields MAX 10 words. Numbers only in numeric fields.\n\n"
        f"JSON only, no extra text:\n"
        f'{{"stocks":[{SCORE_SCHEMA}],"macro_summary":"","risk_level":"MODERATE","sector_rotation":"","market_mood":"NEUTRAL"}}'
    )

# =============================================================================
# PUBLISH
# =============================================================================
def publish_html(html_content):
    if not GITHUB_TOKEN or not GITHUB_REPO: return
    api=f"https://api.github.com/repos/{GITHUB_REPO}/contents/docs/index.html"
    hdrs={"Authorization":f"token {GITHUB_TOKEN}","Content-Type":"application/json","Accept":"application/vnd.github.v3+json","User-Agent":"stock-agent"}
    sha=None
    try:
        req=urllib.request.Request(api,headers=hdrs)
        with urllib.request.urlopen(req,timeout=30) as r: sha=json.loads(r.read().decode()).get("sha")
    except: pass
    encoded=base64.b64encode(html_content.encode("utf-8")).decode("utf-8")
    body={"message":f"Report {TODAY}","content":encoded,"branch":"main"}
    if sha: body["sha"]=sha
    req=urllib.request.Request(api,data=json.dumps(body).encode(),headers=hdrs,method="PUT")
    try:
        with urllib.request.urlopen(req,timeout=30): print(f"  -> Published docs/index.html")
    except Exception as e: print(f"  -> Publish failed: {e}")

# =============================================================================
# HTML
# =============================================================================
def build_html(top10, watchlist, macro, mkt, stock_data):
    top10_json    =json.dumps(top10,      ensure_ascii=False)
    watchlist_json=json.dumps(watchlist,  ensure_ascii=False)
    macro_json    =json.dumps(macro,      ensure_ascii=False)
    mkt_json      =json.dumps(mkt,        ensure_ascii=False)
    stocks_json   =json.dumps(stock_data, ensure_ascii=False)
    tracking      =", ".join(ALL_PERSONAL) if ALL_PERSONAL else "none"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Victor Kane -- {TODAY}</title>
<style>
:root{{--bg:#0f172a;--card:#1e293b;--card2:#263148;--border:#334155;--text:#e2e8f0;--muted:#64748b;
      --green:#10b981;--red:#ef4444;--amber:#f59e0b;--blue:#3b82f6;--purple:#8b5cf6}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
/* Header */
.hdr{{background:linear-gradient(135deg,#0f172a,#1e3a5f);padding:18px 20px;border-bottom:1px solid var(--border)}}
.hdr-inner{{max-width:1200px;margin:0 auto;display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px}}
.logo{{font-size:9px;color:#475569;text-transform:uppercase;letter-spacing:.15em;margin-bottom:2px}}
.title{{font-size:20px;font-weight:800;color:#fff}}
.sub{{font-size:10px;color:#475569;margin-top:2px}}
.badges{{display:flex;gap:6px;flex-wrap:wrap}}
.badge{{padding:6px 12px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.1);border-radius:7px;text-align:center}}
.badge-l{{font-size:8px;color:#475569;text-transform:uppercase;margin-bottom:1px}}
.badge-v{{font-size:13px;font-weight:800;color:#fff}}
/* Market bar */
.mbar{{background:var(--card);border-bottom:1px solid var(--border);padding:10px 20px}}
.mbar-inner{{max-width:1200px;margin:0 auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
.ms{{text-align:center;padding:5px 12px;background:var(--card2);border-radius:6px}}
.ms-l{{font-size:8px;color:var(--muted);text-transform:uppercase;margin-bottom:1px}}
.ms-v{{font-size:12px;font-weight:700}}
.mtext{{font-size:11px;color:var(--muted);flex:1;min-width:160px;line-height:1.5}}
/* Nav */
.nav{{background:var(--card);border-bottom:1px solid var(--border);display:flex;overflow-x:auto}}
.nb{{padding:10px 16px;font-size:12px;font-weight:600;color:var(--muted);background:none;border:none;cursor:pointer;border-bottom:3px solid transparent;white-space:nowrap}}
.nb.active{{color:var(--blue);border-bottom-color:var(--blue)}}
/* Main */
.main{{max-width:1200px;margin:0 auto;padding:14px}}
.sec{{display:none}}.sec.active{{display:block}}
/* Cards */
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px;margin-top:10px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:10px;overflow:hidden;cursor:pointer;transition:.15s}}
.card:hover{{border-color:var(--blue);transform:translateY(-1px)}}
.card-hdr{{padding:12px 14px;background:var(--card2);border-bottom:1px solid var(--border);display:flex;justify-content:space-between}}
.card-body{{display:none;padding:12px 14px;border-top:1px solid var(--border)}}
.card-body.open{{display:block}}
/* Table */
.twrap{{overflow-x:auto;margin-top:10px}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{padding:8px 10px;font-size:9px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;
    border-bottom:2px solid var(--border);text-align:left;white-space:nowrap;cursor:pointer;background:var(--card2)}}
th:hover{{color:var(--blue)}}th.sa::after{{content:" ^"}}th.sd::after{{content:" v"}}
td{{padding:8px 10px;border-bottom:1px solid var(--border);vertical-align:middle;white-space:nowrap}}
tr:hover td{{background:var(--card2)}}
.srow td{{background:var(--card2);font-size:9px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}}
.co{{white-space:normal;min-width:160px}}
.cn{{font-size:12px;font-weight:700}}
.cs{{font-size:9px;color:var(--muted);margin-top:1px}}
.cd{{font-size:9px;color:#475569;margin-top:2px;max-width:200px;white-space:normal;line-height:1.4}}
/* Badges */
.sig{{display:inline-block;padding:2px 8px;border-radius:16px;font-size:9px;font-weight:700}}
.tag{{display:inline-block;padding:1px 5px;border-radius:3px;font-size:8px;font-weight:700;margin-top:2px}}
/* Filters */
.frow{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;align-items:center}}
.fb{{padding:4px 10px;font-size:10px;background:var(--card2);border:1px solid var(--border);border-radius:16px;cursor:pointer;color:var(--muted)}}
.fb.active{{background:var(--blue);color:#fff;border-color:var(--blue)}}
.sb{{padding:5px 10px;font-size:11px;background:var(--card2);border:1px solid var(--border);border-radius:6px;color:var(--text);flex:1;min-width:140px;max-width:200px}}
/* Section title */
.sh{{font-size:14px;font-weight:700;margin:8px 0 2px;display:flex;align-items:center;gap:6px}}
.ss{{font-size:10px;color:var(--muted);margin-bottom:10px}}
/* Theme chips */
.theme-chips{{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}}
.tc{{padding:3px 10px;border-radius:12px;font-size:10px;font-weight:600}}
.g{{color:var(--green)}}.r{{color:var(--red)}}.a{{color:var(--amber)}}.b{{color:var(--blue)}}.p{{color:var(--purple)}}.m{{color:var(--muted)}}
@media(max-width:600px){{.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="hdr"><div class="hdr-inner">
  <div><div class="logo">Quant Signal Agent</div><div class="title">Victor Kane Daily Report</div>
  <div class="sub">{TODAY} &middot; {NOW} &middot; Tracking: {tracking}</div></div>
  <div class="badges" id="hdrbadges"></div>
</div></div>
<div class="mbar"><div class="mbar-inner" id="mbar"></div></div>
<nav class="nav">
  <button class="nb active" onclick="showTab('picks',this)">Top 10 Picks</button>
  <button class="nb" onclick="showTab('watch',this)">Watchlist</button>
  <button class="nb" onclick="showTab('info',this)">Market Themes</button>
</nav>
<div class="main">
  <div id="picks" class="sec active"></div>
  <div id="watch" class="sec"></div>
  <div id="info" class="sec"></div>
</div>

<script>
const TOP10={top10_json},WATCH={watchlist_json},MACRO={macro_json},MKT={mkt_json},SD={stocks_json};
const TODAY="{TODAY}";
let sortK=null,sortD=1,fSig="ALL",fCat="ALL",fTheme="ALL",srch="";

const G="#10b981",R="#ef4444",A="#f59e0b",B="#3b82f6",P="#8b5cf6",M="#64748b";
const THEME_COLS={{AI:"#a78bfa",Cybersecurity:"#34d399",Cloud:"#60a5fa",Healthcare:"#f472b6",Fintech:"#fbbf24",Industrial:"#94a3b8",Other:"#64748b"}};
const SECTOR_ICONS={{Technology:"[T]",Healthcare:"[H]","Financial Services":"[$]","Consumer Cyclical":"[C]",Industrials:"[I]",Energy:"[E]",Other:"[?]"}};

function sc(s){{s=(s||"").toUpperCase();if(s.includes("STRONG BUY"))return G;if(s.includes("BUY"))return G;if(s.includes("WATCH"))return A;if(s.includes("HOLD"))return B;return R;}}
function scr(n){{return n>=80?G:n>=65?"#22c55e":n>=50?A:R}}
function cc(v){{return parseFloat(v||0)>=0?G:R}}
function fp(v,d=1){{try{{let n=parseFloat(v||0);return(n>=0?"+":"")+n.toFixed(d)+"%"}}catch{{return"N/A"}}}}
function fd(v,d=2){{try{{return parseFloat(v||0).toFixed(d)}}catch{{return"N/A"}}}}
function cs(c){{c=(c||"").toUpperCase();if(c=="GROWTH")return"background:#4c1d95;color:#ddd6fe";if(c=="BALANCED")return"background:#0c4a6e;color:#bae6fd";if(c=="VALUE")return"background:#14532d;color:#bbf7d0";return"background:#374151;color:#e5e7eb"}}
function ss(s){{let c=sc(s);return`background:${{c}}22;color:${{c}};border:1px solid ${{c}}44`}}
function showTab(id,btn){{document.querySelectorAll(".sec").forEach(s=>s.classList.remove("active"));document.querySelectorAll(".nb").forEach(b=>b.classList.remove("active"));document.getElementById(id).classList.add("active");btn.classList.add("active");}}

function renderBadges(){{
  const risk=MACRO.risk_level||"MODERATE";
  const rc={{LOW:G,MODERATE:A,HIGH:R}}[risk]||M;
  const gr=TOP10.filter(p=>(p.category||"").toUpperCase()=="GROWTH").length;
  document.getElementById("hdrbadges").innerHTML=[
    ["Risk",`<span style="color:${{rc}}">${{risk}}</span>`],["Picks",TOP10.length],
    ["G/B",`${{gr}}/${{TOP10.length-gr}}`],["VIX",MKT.vix]
  ].map(([l,v])=>`<div class="badge"><div class="badge-l">${{l}}</div><div class="badge-v">${{v}}</div></div>`).join("");
}}

function renderMarket(){{
  const mC={{BULLISH:G,NEUTRAL:A,BEARISH:R}}[MACRO.market_mood]||M;
  document.getElementById("mbar").innerHTML=`
    <div class="ms"><div class="ms-l">Mood</div><div class="ms-v" style="color:${{mC}}">${{MACRO.market_mood||"N/A"}}</div></div>
    <div class="ms"><div class="ms-l">S&P 500</div><div class="ms-v" style="color:${{cc(MKT.sp)}}">${{fp(MKT.sp)}}</div></div>
    <div class="ms"><div class="ms-l">Nasdaq</div><div class="ms-v" style="color:${{cc(MKT.nq)}}">${{fp(MKT.nq)}}</div></div>
    <div class="mtext">${{MACRO.macro_summary||""}} <span style="color:#334155">&mdash; ${{MACRO.sector_rotation||""}}</span></div>`;
}}

function scoreBars(bd,col){{
  return [["Tech",bd.technical||0,30],["Fund",bd.fundamental||0,25],["Cat",bd.catalyst||0,20],["Macro",bd.macro||0,15],["RR",bd.rr||0,10]]
    .map(([n,v,mx])=>`<div style="margin-bottom:3px"><div style="display:flex;justify-content:space-between;font-size:8px;color:${{M}};margin-bottom:1px"><span>${{n}}</span><span style="color:${{col}}">${{v}}/${{mx}}</span></div><div style="height:3px;background:#334155;border-radius:2px"><div style="height:3px;width:${{Math.round(v/mx*100)}}%;background:${{col}};border-radius:2px"></div></div></div>`).join("");
}}

function renderCard(p,idx){{
  const s=p.score||0,col=scr(s),chgC=cc(p.chg_pct),bd=p.score_breakdown||{{}};
  const sd=SD[p.ticker]||{{}};
  const thCol=THEME_COLS[p.theme]||M;
  const upr1yC=parseFloat(p.upr_1y||0)>0?G:R;
  return `<div class="card" onclick="this.querySelector('.card-body').classList.toggle('open')">
  <div class="card-hdr">
    <div>
      <div style="display:flex;align-items:center;gap:5px;flex-wrap:wrap">
        <span style="color:${{M}};font-size:9px">#${{idx}}</span>
        <span style="font-size:19px;font-weight:800">${{p.ticker}}</span>
        <span class="tag" style="${{cs(p.category)}}">${{p.category}}</span>
        ${{p.theme?`<span class="tag" style="background:${{thCol}}22;color:${{thCol}};border:1px solid ${{thCol}}44">${{p.theme}}</span>`:""}}
      </div>
      <div style="font-size:10px;color:${{M}};margin-top:1px">${{p.name}} &middot; ${{p.sector}}</div>
      <div style="font-size:9px;color:#334155;margin-top:2px;max-width:190px;white-space:normal;line-height:1.4">${{sd.desc||""}}</div>
      <span class="sig" style="${{ss(p.signal)}};margin-top:4px;display:inline-block">${{p.signal}}</span>
    </div>
    <div style="text-align:right">
      <div style="font-size:18px;font-weight:700">$${{fd(p.price)}}</div>
      <div style="font-size:10px;color:${{chgC}};font-weight:600">${{fp(p.chg_pct)}} today</div>
      <div style="font-size:18px;font-weight:800;color:${{col}};margin-top:3px">${{s}}</div>
      <div style="font-size:8px;color:${{M}}">confidence</div>
    </div>
  </div>
  <div style="padding:8px 14px;border-bottom:1px solid var(--border)">
    <div style="display:flex;gap:8px;align-items:flex-start">
      <div style="flex:1">${{scoreBars(bd,col)}}</div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid var(--border)">
    ${{[["Entry",`$${{fd(p.entry_low)}}--$${{fd(p.entry_high)}}`,B,""],
       ["1M",`$${{fd(p.t1m)}}`,G,fp(p.upr_1m)+" "+p.prob_1m+"%"],
       ["6M",`$${{fd(p.t6m)}}`,G,fp(p.upr_6m)+" "+p.prob_6m+"%"],
       ["1Y",`$${{fd(p.t1y)}}`,upr1yC,fp(p.upr_1y)+" "+p.prob_1y+"%"],
       ["Stop",`$${{fd(p.stop)}}`,R,"RR "+fd(p.rr_ratio,1)+"x"],
       ["Analyst",`$${{fd(p.atgt)}}`,P,p.nans+" ana"]]
      .map(([l,v,c,s])=>`<div style="padding:6px 8px;text-align:center;border-right:1px solid var(--border)"><div style="font-size:7px;color:${{M}};text-transform:uppercase">${{l}}</div><div style="font-size:10px;font-weight:700;color:${{c}}">${{v}}</div>${{s?`<div style="font-size:8px;color:${{M}}">${{s}}</div>`:""}}`)
      .join("")}}
  </div>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);background:#1a2540">
    ${{[["P/E",fd(p.pe)+"x",""],["RevG",fp(p.rev_g),parseFloat(p.rev_g||0)>15?G:""],
       ["GrossM",fp(p.gm),""],["RSI",p.rsi,parseFloat(p.rsi||50)>70?A:parseFloat(p.rsi||50)<35?G:""],
       ["Vs50MA",fp(p.vs50ma),cc(p.vs50ma)],["NetM",fp(p.nm),parseFloat(p.nm||0)>0?G:R],
       ["52W hi",fp(p.vs52h),cc(p.vs52h)],["Beta",fd(p.beta||0,1),""]]
      .map(([l,v,c])=>`<div style="padding:5px 8px;text-align:center;border-right:1px solid var(--border)"><div style="font-size:7px;color:${{M}};text-transform:uppercase">${{l}}</div><div style="font-size:10px;font-weight:600;color:${{c||"inherit"}}">${{v}}</div>`).join("")}}
  </div>
  <div class="card-body">
    <div style="padding:8px;background:var(--card2);border-radius:6px;margin-bottom:8px">
      <div style="font-size:8px;font-weight:700;color:${{P}};text-transform:uppercase;margin-bottom:3px">Victor's Thesis</div>
      <div style="font-size:11px;line-height:1.6">${{p.why_buy||"N/A"}}</div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px">
      <div style="padding:8px;background:#052e16;border-radius:6px;border:1px solid #166534">
        <div style="font-size:7px;font-weight:700;color:#4ade80;text-transform:uppercase;margin-bottom:2px">Technical Setup</div>
        <div style="font-size:10px;color:#86efac;line-height:1.5">${{p.technical_read||"N/A"}}</div>
      </div>
      <div style="padding:8px;background:#0c1a3e;border-radius:6px;border:1px solid #1e40af">
        <div style="font-size:7px;font-weight:700;color:#60a5fa;text-transform:uppercase;margin-bottom:2px">Key Catalyst</div>
        <div style="font-size:10px;color:#93c5fd;line-height:1.5">${{p.catalyst||"N/A"}}</div>
      </div>
      <div style="padding:8px;background:#2d1b00;border-radius:6px;border:1px solid #92400e">
        <div style="font-size:7px;font-weight:700;color:#fbbf24;text-transform:uppercase;margin-bottom:2px">Macro Tailwind</div>
        <div style="font-size:10px;color:#fcd34d;line-height:1.5">${{p.macro_factor||"N/A"}}</div>
      </div>
      <div style="padding:8px;background:#1a0a0a;border-radius:6px;border:1px solid #7f1d1d">
        <div style="font-size:7px;font-weight:700;color:#ef4444;text-transform:uppercase;margin-bottom:2px">Risks</div>
        <div style="font-size:10px;color:#fca5a5;line-height:1.5">${{p.risks||"N/A"}}</div>
      </div>
    </div>
    ${{sd.desc?`<div style="font-size:9px;color:${{M}};padding:6px 8px;background:var(--card2);border-radius:5px;line-height:1.5"><span style="font-size:8px;font-weight:700;color:${{B}};text-transform:uppercase">About: </span>${{sd.desc}}</div>`:""}}
    ${{sd.employees?`<div style="font-size:9px;color:${{M}};margin-top:4px">Employees: ${{sd.employees.toLocaleString()}} &middot; Inst: ${{sd.inst||"?"}}% &middot; Short: ${{sd.short_pct||"?"}}%</div>`:""}}
  </div>
</div>`;
}}

function renderPicks(){{
  const el=document.getElementById("picks");
  const themes=[...new Set(TOP10.map(p=>p.theme||"Other"))].sort();
  const themeFilter=`<div style="margin-bottom:8px;display:flex;gap:5px;flex-wrap:wrap"><span style="font-size:9px;color:${{M}};align-self:center">Theme:</span>
    ${{["ALL",...themes].map(t=>`<button class="fb ${{fTheme===t?"active":""}}" onclick="setTheme('${{t}}')" style="${{t!="ALL"?`border-color:${{THEME_COLS[t]||M}};`:""}}">${{t}}</button>`).join("")}}</div>`;

  if(!TOP10.length){{el.innerHTML=`<div style="text-align:center;padding:40px;color:${{M}}">No picks today.</div>`;return;}}

  const gr=TOP10.filter(p=>(p.category||"").toUpperCase()=="GROWTH"&&(fTheme=="ALL"||p.theme==fTheme));
  const ba=TOP10.filter(p=>(p.category||"").toUpperCase()!="GROWTH"&&(fTheme=="ALL"||p.theme==fTheme));
  let html=themeFilter;
  if(gr.length) html+=`<div class="sh"><span style="width:3px;height:20px;background:${{P}};border-radius:2px;display:inline-block"></span>Growth Picks</div><div class="ss">${{gr.length}} picks &middot; click any card for full thesis</div><div class="grid">${{gr.map((p,i)=>renderCard(p,i+1)).join("")}}</div>`;
  if(ba.length) html+=`<div class="sh" style="margin-top:16px"><span style="width:3px;height:20px;background:${{B}};border-radius:2px;display:inline-block"></span>Balanced / Value Picks</div><div class="ss">${{ba.length}} picks</div><div class="grid">${{ba.map((p,i)=>renderCard(p,i+1)).join("")}}</div>`;
  el.innerHTML=html;
}}
function setTheme(t){{fTheme=t;renderPicks();}}

// Watchlist table
function getFiltered(){{
  return WATCH.filter(w=>{{
    if(fSig!="ALL"&&w.signal!==fSig) return false;
    if(fCat!="ALL"&&(w.category||"").toUpperCase()!==fCat) return false;
    if(srch&&![(w.ticker||""),(w.name||""),(w.sector||""),(w.industry||"")].some(v=>v.toUpperCase().includes(srch.toUpperCase()))) return false;
    return true;
  }});
}}
function doSort(k){{sortK===k?sortD*=-1:(sortK=k,sortD=1);renderWatch();}}
function watchRow(w){{
  const s=w.score||0,col=scr(s),chgC=cc(w.chg_pct),upr=parseFloat(w.upr_1y||0);
  const sd=SD[w.ticker]||{{}};
  return `<tr>
    <td class="co"><div class="cn">${{w.ticker}}</div><div class="cs">${{(w.name||"").substring(0,24)}}</div>
      <div class="cs" style="color:#475569">${{w.industry||w.sector||""}}</div>
      <div class="cd">${{sd.desc||""}}</div>
      <span class="tag" style="${{cs(w.category)}}">${{w.category}}</span></td>
    <td><div style="font-weight:700">$${{fd(w.price)}}</div><div style="font-size:9px;color:${{chgC}}">${{fp(w.chg_pct)}}</div></td>
    <td><span class="sig" style="${{ss(w.signal)}}">${{w.signal}}</span></td>
    <td style="text-align:center"><div style="font-size:15px;font-weight:800;color:${{col}}">${{s}}</div><div style="font-size:8px;color:${{M}}">/100</div></td>
    <td style="color:${{B}};font-size:10px">$${{fd(w.entry_low)}}--$${{fd(w.entry_high)}}</td>
    <td><div style="color:${{upr>0?G:R}};font-weight:700">$${{fd(w.t1y)}}</div><div style="font-size:9px;color:${{upr>0?G:R}}">${{fp(w.upr_1y)}}</div></td>
    <td style="color:${{R}}">$${{fd(w.stop)}}</td>
    <td>${{fd(w.pe)}}x</td>
    <td>${{fd(w.fwd_pe)}}x</td>
    <td style="color:${{parseFloat(w.rev_g||0)>15?G:"inherit"}}">${{fp(w.rev_g)}}</td>
    <td style="color:${{parseFloat(w.gm||0)>50?"#22c55e":"inherit"}}">${{fp(w.gm)}}</td>
    <td style="color:${{parseFloat(w.nm||0)>0?G:R}}">${{fp(w.nm)}}</td>
    <td style="color:${{parseFloat(w.rsi||50)>70?A:parseFloat(w.rsi||50)<35?G:"inherit"}}">${{w.rsi}}</td>
    <td style="color:${{cc(w.vs50ma)}}">${{fp(w.vs50ma)}}</td>
    <td style="color:${{cc(w.vs200ma)}}">${{fp(w.vs200ma)}}</td>
    <td>$${{fd(w.atgt)}}</td>
    <td>${{w.nans||"?"}}</td>
    <td style="color:${{M}};font-style:italic;white-space:normal;min-width:160px;font-size:10px">${{w.note||""}}</td>
  </tr>`;
}}
function renderWatch(){{
  const el=document.getElementById("watch");
  const data=sortK?[...getFiltered()].sort((a,b)=>{{let va=a[sortK],vb=b[sortK];return typeof va==="string"?sortD*va.localeCompare(vb||""):sortD*(parseFloat(va||0)-parseFloat(vb||0))}}):getFiltered();
  const sectors={{}};
  data.forEach(w=>{{const s=w.sector||"Other";if(!sectors[s])sectors[s]=[];sectors[s].push(w);}});
  let body="";
  Object.entries(sectors).sort(([a],[b])=>a.localeCompare(b)).forEach(([sec,rows])=>{{
    body+=`<tr class="srow"><td colspan=18>${{SECTOR_ICONS[sec]||"[?]"}} ${{sec}} (${{rows.length}})</td></tr>`;
    body+=rows.map(watchRow).join("");
  }});
  const cols=[["co","Stock","ticker"],["p","Price","price"],["sig","Signal","signal"],["sc","Score","score"],
    ["er","Entry","entry_low"],["t1","1Y Target","t1y"],["st","Stop","stop"],["pe","P/E","pe"],
    ["fp2","Fwd P/E","fwd_pe"],["rg","Rev Gr","rev_g"],["gm","Gross M","gm"],["nm","Net M","nm"],
    ["rs","RSI","rsi"],["v5","Vs 50MA","vs50ma"],["v2","Vs 200MA","vs200ma"],
    ["at","Analyst Tgt","atgt"],["na","# Ana","nans"],["nt","Victor's Note","note"]];
  const thead=cols.map(([id,lbl,key])=>`<th id="th${{id}}" onclick="doSort('${{key}}')">${{lbl}}</th>`).join("");
  const sigs=["ALL",...new Set(WATCH.map(w=>w.signal).filter(Boolean))];
  const cats=["ALL","GROWTH","BALANCED","VALUE"];
  el.innerHTML=`
    <div class="sh" style="margin-top:6px"><span style="width:3px;height:20px;background:${{A}};border-radius:2px;display:inline-block"></span>Your Watchlist</div>
    <div class="ss">${{WATCH.length}} stocks &middot; click headers to sort &middot; grouped by sector</div>
    <div class="frow">
      <input class="sb" placeholder="Search..." oninput="srch=this.value;renderWatch()" value="${{srch}}">
      ${{sigs.map(s=>`<button class="fb ${{fSig===s?"active":""}}" onclick="fSig='${{s}}';renderWatch()">${{s}}</button>`).join("")}}
      <span style="color:#334155">|</span>
      ${{cats.map(c=>`<button class="fb ${{fCat===c?"active":""}}" onclick="fCat='${{c}}';renderWatch()">${{c}}</button>`).join("")}}
    </div>
    <div class="twrap"><table><thead><tr>${{thead}}</tr></thead><tbody>${{body||'<tr><td colspan=18 style="text-align:center;padding:20px;color:#64748b">No stocks match</td></tr>'}}</tbody></table></div>`;
  if(sortK){{const th=document.querySelector(`th[onclick="doSort('${{sortK}}')"]`);if(th)th.classList.add(sortD>0?"sa":"sd");}}
}}

// Market themes tab
function renderThemes(){{
  const themes={{
    "AI & Semiconductors":{{color:THEME_COLS.AI,desc:"AI infrastructure spending is in a multi-year supercycle. Hyperscalers (MSFT, GOOGL, AMZN, META) are spending $300B+ on AI capex in 2025. NVIDIA dominates GPU market with 80%+ share. ARM, AVGO, SMCI, MRVL riding the wave.",tickers:["NVDA","AMD","AVGO","ARM","SMCI","MRVL","INTC","QCOM"]}},
    "Cybersecurity":{{color:THEME_COLS.Cybersecurity,desc:"Every AI deployment creates new attack surfaces. Global cybersecurity spend projected to reach $300B by 2027. Zero-trust architecture, cloud security, and AI-driven threat detection are fastest-growing segments. Post-breach spending accelerating.",tickers:["CRWD","PANW","ZS","FTNT","OKTA","S","CYBR"]}},
    "Cloud & SaaS":{{color:THEME_COLS.Cloud,desc:"Cloud migration still in early innings globally. AI is accelerating SaaS adoption as companies retool workflows. Hyperscalers growing 20-25% YoY. Database and observability tools seeing renewed demand.",tickers:["MSFT","GOOGL","AMZN","ORCL","SNOW","DDOG","MDB","NOW"]}},
    "Healthcare & GLP-1":{{color:THEME_COLS.Healthcare,desc:"GLP-1 drugs (Ozempic, Wegovy) are once-in-a-generation products. Eli Lilly and Novo Nordisk addressing obesity, diabetes, potentially heart disease and Alzheimer's. Medtech innovation + aging demographics = long runway.",tickers:["LLY","UNH","ABBV","ISRG","MRNA"]}},
  }};
  const el=document.getElementById("info");
  el.innerHTML=`<div class="sh" style="margin-top:6px">Market Themes & Investment Theses</div>
    <div class="ss">Macro tailwinds driving long-term sector returns &middot; Data as of ${{TODAY}}</div>
    ${{Object.entries(themes).map(([name,t])=>`
    <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:12px;border-left:4px solid ${{t.color}}">
      <div style="font-size:13px;font-weight:700;color:${{t.color}};margin-bottom:6px">${{name}}</div>
      <div style="font-size:12px;color:var(--text);line-height:1.7;margin-bottom:10px">${{t.desc}}</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        ${{t.tickers.map(tk=>{{const sd=SD[tk]||{{}};const p=sd.price||0;const chg=sd.chg_pct||0;const rg=sd.rev_g||0;
          return `<div style="padding:6px 10px;background:var(--card2);border-radius:6px;border:1px solid ${{t.color}}33;cursor:pointer" onclick="document.querySelector('.nb[onclick*=watch]').click();srch='${{tk}}';renderWatch()">
            <div style="font-size:11px;font-weight:700">${{tk}}</div>
            ${{p?`<div style="font-size:9px;color:${{cc(chg)}}">${{p?("$"+p.toFixed(2)):"N/A"}} ${{fp(chg)}}</div>`:""}}`+
            (rg?`<div style="font-size:9px;color:${{parseFloat(rg)>15?"#22c55e":M}}">RevG ${{fp(rg,0)}}</div>`:"")+"</div>";
        }}).join("")}}
      </div>
    </div>`).join("")}}`;
}}

renderBadges();renderMarket();renderPicks();renderWatch();renderThemes();
</script>
</body></html>"""

# =============================================================================
# EMAIL
# =============================================================================
def send_email(subject, html_report, top10, mkt, macro):
    growth   = [p for p in top10 if str(p.get("category","")).upper()=="GROWTH"]
    balanced = [p for p in top10 if str(p.get("category","")).upper()!="GROWTH"]
    risk     = macro.get("risk_level","MODERATE")
    risk_col = {"LOW":"#059669","MODERATE":"#d97706","HIGH":"#dc2626"}.get(risk.upper(),"#6b7280")
    owner    = GITHUB_REPO.split("/")[0] if GITHUB_REPO else ""
    repo     = GITHUB_REPO.split("/")[1] if "/" in GITHUB_REPO else "stock-agent"
    page_url = f"https://{owner}.github.io/{repo}/" if owner else ""

    rows="".join([f"""<tr>
      <td style="padding:8px 10px;font-weight:700">{p.get('ticker','')}</td>
      <td style="padding:8px 10px;color:#64748b;font-size:11px">{p.get('name','')[:20]}</td>
      <td style="padding:8px 10px;font-size:10px;background:{'#7c3aed22' if (p.get('theme',''))=='AI' else '#05965522' if p.get('theme')=='Cybersecurity' else 'transparent'};color:{'#a78bfa' if p.get('theme')=='AI' else '#34d399' if p.get('theme')=='Cybersecurity' else '#94a3b8'}">{p.get('theme','')}</td>
      <td style="padding:8px 10px">${p.get('price',0):.2f}</td>
      <td style="padding:8px 10px;font-weight:700;color:{'#059669' if p.get('score',0)>=80 else '#10b981' if p.get('score',0)>=65 else '#d97706'}">{p.get('score',0)}/100</td>
      <td style="padding:8px 10px;color:#10b981">${p.get('t1y',0):.2f} ({'+' if p.get('upr_1y',0)>=0 else ''}{p.get('upr_1y',0):.1f}%)</td>
      <td style="padding:8px 10px;font-size:10px;color:#94a3b8;font-style:italic">{str(p.get('why_buy',''))[:50]}...</td>
    </tr>""" for p in top10])

    body=f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,sans-serif">
<div style="max-width:700px;margin:0 auto">
  <div style="background:linear-gradient(135deg,#0f172a,#1e3a5f);padding:20px 24px">
    <div style="font-size:9px;color:#475569;text-transform:uppercase;letter-spacing:.15em">Quant Signal Agent</div>
    <div style="font-size:20px;font-weight:800;color:#fff;margin:2px 0">Victor Kane Daily Report</div>
    <div style="font-size:10px;color:#475569">{TODAY} &middot; {NOW}</div>
    <div style="display:flex;gap:7px;margin-top:9px;flex-wrap:wrap">
      <span style="padding:3px 9px;background:rgba(255,255,255,.08);border-radius:5px;font-size:10px;font-weight:600;color:{risk_col}">Risk: {risk}</span>
      <span style="padding:3px 9px;background:rgba(255,255,255,.08);border-radius:5px;font-size:10px;color:#fff">Top {len(top10)} picks ({len(growth)}G/{len(balanced)}B)</span>
      <span style="padding:3px 9px;background:rgba(255,255,255,.08);border-radius:5px;font-size:10px;color:#94a3b8">S&P {'+' if mkt.get('sp',0)>=0 else ''}{mkt.get('sp',0):.2f}% &middot; VIX {mkt.get('vix','?')}</span>
    </div>
  </div>
  <div style="background:#fff;padding:18px 24px">
    <p style="font-size:12px;color:#374151;line-height:1.7;margin:0 0 14px">{macro.get('macro_summary','')}</p>
    {'<div style="text-align:center;margin:16px 0"><a href="' + page_url + '" style="display:inline-block;background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff;text-decoration:none;padding:11px 24px;border-radius:7px;font-size:13px;font-weight:700">Open Full Interactive Report</a><div style="font-size:9px;color:#94a3b8;margin-top:5px">' + page_url + '</div></div>' if page_url else ''}
    <table style="width:100%;border-collapse:collapse;margin-top:12px">
      <thead><tr style="background:#f8fafc;border-bottom:2px solid #e2e8f0">
        <th style="padding:6px 10px;text-align:left;font-size:9px;color:#64748b;text-transform:uppercase">Ticker</th>
        <th style="padding:6px 10px;text-align:left;font-size:9px;color:#64748b;text-transform:uppercase">Company</th>
        <th style="padding:6px 10px;text-align:left;font-size:9px;color:#64748b;text-transform:uppercase">Theme</th>
        <th style="padding:6px 10px;text-align:left;font-size:9px;color:#64748b;text-transform:uppercase">Price</th>
        <th style="padding:6px 10px;text-align:left;font-size:9px;color:#64748b;text-transform:uppercase">Score</th>
        <th style="padding:6px 10px;text-align:left;font-size:9px;color:#64748b;text-transform:uppercase">1Y Target</th>
        <th style="padding:6px 10px;text-align:left;font-size:9px;color:#64748b;text-transform:uppercase">Thesis</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <div style="margin-top:12px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:10px">
      <div style="font-size:10px;font-weight:700;color:#1e40af;margin-bottom:2px">Full report attached (victor-kane-{TODAY}.html)</div>
      <div style="font-size:9px;color:#3b82f6">Open in any browser for interactive dashboard: sortable table, sector grouping, company descriptions, market themes</div>
    </div>
  </div>
  <div style="padding:10px 24px;background:#f8fafc;text-align:center;font-size:9px;color:#94a3b8">
    Educational purposes only. Not financial advice. &middot; {NOW}
  </div>
</div></body></html>"""

    msg=MIMEMultipart("mixed")
    msg["Subject"]=subject; msg["From"]=EMAIL_FROM; msg["To"]=EMAIL_TO
    msg.attach(MIMEText(body,"html"))
    att=MIMEBase("text","html")
    att.set_payload(html_report.encode("utf-8"))
    encoders.encode_base64(att)
    att.add_header("Content-Disposition","attachment",filename=f"victor-kane-{TODAY}.html")
    msg.attach(att)
    ctx=ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com",465,context=ctx) as srv:
        srv.login(EMAIL_FROM,EMAIL_PASSWORD); srv.sendmail(EMAIL_FROM,EMAIL_TO,msg.as_string())
    print(f"  -> Email sent to {EMAIL_TO}")

# =============================================================================
# MAIN
# =============================================================================
def main():
    print(f"\n{'='*55}\n  Quant Signal Agent -- {NOW}")
    if ALL_PERSONAL: print(f"  Watchlist: {', '.join(ALL_PERSONAL)}")
    print(f"{'='*55}\n")

    print("[Step 1] Fetching market data...")
    mkt=fetch_market()
    print(f"  -> S&P {mkt['sp']:+.2f}% | Nasdaq {mkt['nq']:+.2f}% | VIX {mkt['vix']:.1f}")

    # All tickers to fetch
    disc=[t for t in UNIVERSE if t not in ALL_PERSONAL]
    all_tickers=list(dict.fromkeys(disc + ALL_PERSONAL))
    stock_data=fetch_data(all_tickers)

    def compact(tickers):
        """Compact JSON for Claude - strip desc/website to save tokens"""
        d={}
        for t in tickers:
            if t not in stock_data or "error" in stock_data[t]: continue
            s=stock_data[t]
            d[t]={k:s[k] for k in ["ticker","name","sector","industry","price","chg_pct","mktcap_b",
                "pe","fwd_pe","peg","eps_g","rev_g","gm","om","nm","roe","de","cash_b","fcf_b",
                "beta","wk52h","wk52l","vs52h","rsi","vs50ma","vs200ma","volr",
                "cons","atgt","nans","earn"] if k in s}
        return json.dumps(d,separators=(',',':'))

    # Score ALL discovery stocks in batches of 8 to find true top 10
    all_scored=[]
    disc_batches=[disc[i:i+8] for i in range(0,min(len(disc),24),8)]

    macro={"macro_summary":"","risk_level":"MODERATE","sector_rotation":"","market_mood":"NEUTRAL"}

    for i,batch in enumerate(disc_batches,1):
        print(f"\n[Step 2.{i}] Scoring batch {i}/{len(disc_batches)}: {batch}...")
        if i>1: time.sleep(8)
        task=("Score these stocks. ALWAYS return at least the top 3 regardless of score. "
              "Pick top 3 BUY candidates from this batch. "
              "Assign theme: AI, Cybersecurity, Cloud, Healthcare, Fintech, Industrial, or Other.")
        r=call_claude(score_prompt(compact(batch),mkt,task),"score-"+str(i),max_tokens=1500)
        if r:
            all_scored.extend(r.get("stocks",[]))
            if not macro["macro_summary"] and r.get("macro_summary"):
                macro={k:r.get(k,v) for k,v in macro.items()}

    # Sort by score, take top 10
    all_scored.sort(key=lambda x:x.get("score",0),reverse=True)
    top10=all_scored[:10]
    print(f"\n  -> Top 10 picks selected (scores: {[p.get('score',0) for p in top10]})")

    # Score personal watchlist in batches of 5
    watchlist=[]
    watch_batches=[ALL_PERSONAL[i:i+5] for i in range(0,len(ALL_PERSONAL),5)]
    for i,batch in enumerate(watch_batches,1):
        if not batch: continue
        print(f"\n[Step 3.{i}] Watchlist batch {i}/{len(watch_batches)}: {batch}...")
        time.sleep(8)
        task=("Score these watchlist stocks. Return ALL of them with score, signal, entry, target, stop. "
              "note = exactly 12 words with 2 specific numbers. "
              "Assign theme: AI, Cybersecurity, Cloud, Healthcare, Fintech, Industrial, or Other.")
        r=call_claude(score_prompt(compact(batch),mkt,task),"watch-"+str(i),max_tokens=1500)
        if r:
            items=r.get("stocks",[])
            # map to watchlist format
            for s in items:
                s["note"]=s.get("why_buy","") or s.get("catalyst","") or ""
            watchlist.extend(items)
            print(f"  -> {len(items)} stocks (total {len(watchlist)})")

    print(f"\n[Step 4] Building report (top10={len(top10)}, watchlist={len(watchlist)})...")
    html=build_html(top10,watchlist,macro,mkt,stock_data)

    print("[Step 5] Publishing to GitHub docs/index.html...")
    publish_html(html)

    growth=[p for p in top10 if str(p.get("category","")).upper()=="GROWTH"]
    balanced=[p for p in top10 if str(p.get("category","")).upper()!="GROWTH"]
    mood=macro.get("market_mood","?"); risk=macro.get("risk_level","?")
    subject=f"Victor Kane {TODAY} | Top {len(top10)} picks ({len(growth)}G/{len(balanced)}B) | {mood} | Risk:{risk}"

    print("[Step 6] Sending email...")
    send_email(subject,html,top10,mkt,macro)

    print(f"\n{'='*55}\n  Done\n{'='*55}\n")

if __name__=="__main__":
    main()
