"""
Quant Signal Agent v3 — Victor Kane Daily Stock Report
Architecture: fetch real data via yfinance (free, no API key) → send to Claude for analysis
This avoids web-search token explosions and rate limit issues entirely.
"""

import os, json, urllib.request, urllib.error, smtplib, ssl, time, subprocess, sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

# ── CREDENTIALS ───────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
EMAIL_FROM        = os.environ["EMAIL_FROM"]
EMAIL_PASSWORD    = os.environ["EMAIL_PASSWORD"]
EMAIL_TO          = os.environ["EMAIL_TO"]

# ── WATCHLIST ─────────────────────────────────────────────────────────────────
_raw  = os.environ.get("PERSONAL_WATCHLIST", "")
_extra= os.environ.get("EXTRA_TICKERS", "")
PERSONAL_WATCHLIST = [t.strip().upper() for t in _raw.split(",")   if t.strip()]
EXTRA_TICKERS      = [t.strip().upper() for t in _extra.split(",") if t.strip()]
ALL_PERSONAL       = list(dict.fromkeys(PERSONAL_WATCHLIST + EXTRA_TICKERS))

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# ── DEFAULT DISCOVERY LIST (when no personal watchlist set) ───────────────────
DEFAULT_TICKERS = ["NVDA","AAPL","MSFT","AMD","TSLA","META","GOOGL","AMZN","PLTR","ARM"]

# =============================================================================
# STEP 1 — FETCH REAL MARKET DATA VIA YFINANCE (no API key needed)
# =============================================================================
def install_yfinance():
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance", "--quiet", "--break-system-packages"])

def fetch_stock_data(tickers):
    """Fetch real market data for a list of tickers using yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        install_yfinance()
        import yfinance as yf

    results = {}
    print(f"  → Fetching data for {len(tickers)} tickers: {', '.join(tickers)}")

    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            hist = t.history(period="1y", interval="1d")

            price       = info.get("currentPrice") or info.get("regularMarketPrice") or 0
            prev_close  = info.get("previousClose") or price
            chg_pct     = round(((price - prev_close) / prev_close * 100), 2) if prev_close else 0

            # RSI calculation
            rsi = 50
            if len(hist) >= 15:
                delta = hist["Close"].diff()
                gain  = delta.clip(lower=0).rolling(14).mean()
                loss  = (-delta.clip(upper=0)).rolling(14).mean()
                rs    = gain / loss.replace(0, 0.0001)
                rsi_s = 100 - (100 / (1 + rs))
                rsi   = round(float(rsi_s.iloc[-1]), 1) if not rsi_s.empty else 50

            # Moving averages
            ma50  = round(float(hist["Close"].rolling(50).mean().iloc[-1]),  2) if len(hist) >= 50  else 0
            ma200 = round(float(hist["Close"].rolling(200).mean().iloc[-1]), 2) if len(hist) >= 200 else 0
            vs_50  = round((price - ma50)  / ma50  * 100, 1) if ma50  else 0
            vs_200 = round((price - ma200) / ma200 * 100, 1) if ma200 else 0

            # Volume
            vol_today  = int(hist["Volume"].iloc[-1])   if not hist.empty else 0
            vol_avg30  = int(hist["Volume"].tail(30).mean()) if len(hist) >= 30 else 0
            vol_ratio  = round(vol_today / vol_avg30, 2) if vol_avg30 else 1.0

            results[ticker] = {
                "ticker":               ticker,
                "company_name":         info.get("longName", ticker),
                "sector":               info.get("sector", "Unknown"),
                "current_price":        round(price, 2),
                "price_change_today_pct": chg_pct,
                "market_cap_b":         round(info.get("marketCap", 0) / 1e9, 2),
                "pe_ratio":             round(info.get("trailingPE", 0) or 0, 2),
                "forward_pe":           round(info.get("forwardPE",  0) or 0, 2),
                "peg_ratio":            round(info.get("pegRatio",   0) or 0, 2),
                "ps_ratio":             round(info.get("priceToSalesTrailing12Months", 0) or 0, 2),
                "ev_ebitda":            round(info.get("enterpriseToEbitda", 0) or 0, 2),
                "eps_ttm":              round(info.get("trailingEps", 0) or 0, 2),
                "eps_growth_yoy_pct":   round((info.get("earningsGrowth", 0) or 0) * 100, 1),
                "revenue_growth_yoy_pct": round((info.get("revenueGrowth", 0) or 0) * 100, 1),
                "gross_margin_pct":     round((info.get("grossMargins",    0) or 0) * 100, 1),
                "operating_margin_pct": round((info.get("operatingMargins",0) or 0) * 100, 1),
                "net_margin_pct":       round((info.get("profitMargins",   0) or 0) * 100, 1),
                "roe_pct":              round((info.get("returnOnEquity",  0) or 0) * 100, 1),
                "debt_to_equity":       round(info.get("debtToEquity", 0) or 0, 2),
                "cash_position_b":      round((info.get("totalCash", 0) or 0) / 1e9, 2),
                "week52_high":          round(info.get("fiftyTwoWeekHigh", 0) or 0, 2),
                "week52_low":           round(info.get("fiftyTwoWeekLow",  0) or 0, 2),
                "price_vs_52h_pct":     round((price - (info.get("fiftyTwoWeekHigh",price) or price)) / (info.get("fiftyTwoWeekHigh",price) or price) * 100, 1) if price else 0,
                "analyst_consensus":    info.get("recommendationKey", "N/A"),
                "analyst_avg_target":   round(info.get("targetMeanPrice", 0) or 0, 2),
                "num_analysts":         info.get("numberOfAnalystOpinions", 0) or 0,
                "rsi_14":               rsi,
                "price_vs_50ma":        vs_50,
                "price_vs_200ma":       vs_200,
                "volume_today":         vol_today,
                "avg_volume_30d":       vol_avg30,
                "volume_ratio":         vol_ratio,
                "next_earnings_est":    str(info.get("earningsDate", ["N/A"])[0]) if info.get("earningsDate") else "N/A",
                "institutional_ownership_pct": round((info.get("heldPercentInstitutions", 0) or 0) * 100, 1),
            }
            print(f"    ✓ {ticker}: ${price} | RSI {rsi} | PE {results[ticker]['pe_ratio']}")
        except Exception as e:
            print(f"    ✗ {ticker}: {e}")
            results[ticker] = {"ticker": ticker, "company_name": ticker, "error": str(e)}

    return results


def fetch_market_overview():
    """Fetch S&P500, Nasdaq, VIX."""
    try:
        import yfinance as yf
        spy  = yf.Ticker("SPY").history(period="2d")
        qqq  = yf.Ticker("QQQ").history(period="2d")
        vix  = yf.Ticker("^VIX").history(period="1d")

        sp_chg = round((spy["Close"].iloc[-1] - spy["Close"].iloc[-2]) / spy["Close"].iloc[-2] * 100, 2) if len(spy) >= 2 else 0
        nq_chg = round((qqq["Close"].iloc[-1] - qqq["Close"].iloc[-2]) / qqq["Close"].iloc[-2] * 100, 2) if len(qqq) >= 2 else 0
        vix_v  = round(float(vix["Close"].iloc[-1]), 2) if not vix.empty else 0

        return {"sp500_pct": sp_chg, "nasdaq_pct": nq_chg, "vix": vix_v}
    except Exception as e:
        print(f"  ✗ Market overview error: {e}")
        return {"sp500_pct": 0, "nasdaq_pct": 0, "vix": 0}


# =============================================================================
# STEP 2 — SEND DATA TO CLAUDE FOR ANALYSIS (no web search, tiny prompt)
# =============================================================================
def build_analysis_prompt(stock_data_json, market_overview, personal_tickers):
    watchlist_note = f"Personal watchlist tickers (include ALL in watchlist_analysis): {', '.join(personal_tickers)}" if personal_tickers else ""
    return f"""You are Victor Kane, elite quant analyst, 25yr Wall St veteran. Blunt, precise, min R:R 2.5:1.
Date: {TODAY}. Market: S&P {market_overview['sp500_pct']:+.2f}% | Nasdaq {market_overview['nasdaq_pct']:+.2f}% | VIX {market_overview['vix']:.1f}
{watchlist_note}

REAL MARKET DATA (fetched live today):
{stock_data_json}

Using ONLY the data above:
1. Classify each stock: GROWTH (rev growth >20%/yr) or BALANCED (5-20%/yr)
2. Score each 0-100: technical(30) + fundamental(25) + catalyst(20) + macro(15) + rr(10)
3. Select top picks: STRONG BUY (>=80) or BUY (>=65) only
4. For each pick: set entry range, 1m/6m/1y targets, stop loss, R:R ratio
5. Write Victor's analysis: blunt, specific price levels, no fluff
6. All personal watchlist tickers must appear in watchlist_analysis regardless of signal

Reply with ONLY valid JSON, no markdown, no text before or after:
{{"report_date":"{TODAY}","macro_summary":"Victor 2-sentence market read","risk_level":"LOW|MODERATE|HIGH","sector_rotation":"one line on sector flows","market_mood":"BULLISH|NEUTRAL|BEARISH","vix":{market_overview['vix']},"sp500_pct":{market_overview['sp500_pct']},"nasdaq_pct":{market_overview['nasdaq_pct']},"top_picks":[],"watchlist_analysis":[],"full_scan_brief":[],"disclaimer":"For educational purposes only. Not financial advice."}}

For each item in top_picks use this schema:
{{"ticker":"","company_name":"","category":"GROWTH|BALANCED","sector":"","current_price":0,"price_change_today_pct":0,"signal":"STRONG BUY|BUY","confidence_score":0,"confidence_breakdown":{{"technical":0,"fundamental":0,"catalyst":0,"macro_alignment":0,"risk_reward":0}},"entry_range_low":0,"entry_range_high":0,"target_1m":0,"target_6m":0,"target_1y":0,"stop_loss":0,"upside_1m_pct":0,"upside_6m_pct":0,"upside_1y_pct":0,"target_1m_probability_pct":0,"target_6m_probability_pct":0,"target_1y_probability_pct":0,"risk_reward_ratio":0,"pe_ratio":0,"forward_pe":0,"peg_ratio":0,"ps_ratio":0,"ev_ebitda":0,"eps_ttm":0,"eps_growth_yoy_pct":0,"market_cap_b":0,"revenue_growth_yoy_pct":0,"revenue_growth_qoq_pct":0,"gross_margin_pct":0,"operating_margin_pct":0,"net_margin_pct":0,"fcf_yield_pct":0,"roe_pct":0,"debt_to_equity":0,"cash_position_b":0,"earnings_streak":"","last_earnings_surprise_pct":0,"guidance":"","volume_today":0,"avg_volume_30d":0,"volume_ratio":0,"week52_high":0,"week52_low":0,"price_vs_52h_pct":0,"rsi_14":0,"macd_signal":"BULLISH|NEUTRAL|BEARISH","macd_histogram":"POSITIVE|NEGATIVE","price_vs_50ma":0,"price_vs_200ma":0,"ma_signal":"","chart_pattern":"","support_level":0,"resistance_level":0,"analyst_consensus":"","analyst_avg_target":0,"num_analysts":0,"insider_activity":"Buying|Selling|Neutral","institutional_ownership_pct":0,"institutional_change":"Increasing|Decreasing|Stable","next_earnings_est":"","catalyst_summary":"","geopolitical_factor":"","technical_analysis":"","fundamental_analysis":"","victor_verdict":"","why_now":"","risks":"","is_personal_watchlist":false}}

For watchlist_analysis:
{{"ticker":"","company_name":"","category":"GROWTH|BALANCED","current_price":0,"price_change_today_pct":0,"signal":"STRONG BUY|BUY|WATCH|AVOID","confidence_score":0,"entry_range_low":0,"entry_range_high":0,"target_1y":0,"stop_loss":0,"upside_1y_pct":0,"pe_ratio":0,"week52_high":0,"week52_low":0,"rsi_14":0,"analyst_consensus":"","analyst_avg_target":0,"victor_note":"Victor 1-sentence verdict","is_personal_watchlist":true}}

For full_scan_brief: {{"ticker":"","bias":"BULLISH|NEUTRAL|BEARISH","note":"one line","category":"GROWTH|BALANCED"}}"""


def call_claude_analysis(prompt):
    """Call Claude WITHOUT web search — just pure analysis of pre-fetched data."""
    print("  → Sending data to Claude for Victor Kane analysis...")
    payload = json.dumps({
        "model": "claude-sonnet-4-5",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )

    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            print(f"  ✗ API error {e.code}: {body[:200]}")
            if e.code in (429, 500, 502, 503, 529) and attempt < 3:
                wait = 30 * (attempt + 1)
                print(f"  → Retrying in {wait}s (attempt {attempt+2}/4)...")
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            if attempt < 3:
                print(f"  ✗ Network error: {e}. Retrying in 30s...")
                time.sleep(30)
                continue
            raise

    full_text = "".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text").strip()

    # Strip markdown fences
    import re
    full_text = re.sub(r"^```(?:json)?\s*", "", full_text, flags=re.MULTILINE)
    full_text = re.sub(r"\s*```$",          "", full_text, flags=re.MULTILINE)

    start = full_text.find("{")
    end   = full_text.rfind("}") + 1
    if start == -1:
        raise ValueError(f"No JSON in response. Preview: {full_text[:300]}")

    json_str = full_text[start:end]

    # Clean common issues
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)          # trailing commas
    json_str = json_str.replace("\u201c",'"').replace("\u201d",'"')  # smart quotes

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  ✗ JSON error at pos {e.pos}: ...{json_str[max(0,e.pos-60):e.pos+60]}...")
        # Return skeleton so email still sends
        return {
            "report_date": TODAY, "macro_summary": "Analysis error — partial data only.",
            "risk_level": "MODERATE", "sector_rotation": "N/A",
            "market_mood": "NEUTRAL", "vix": 0, "sp500_pct": 0, "nasdaq_pct": 0,
            "top_picks": [], "watchlist_analysis": [], "full_scan_brief": [],
            "disclaimer": "For educational purposes only. Not financial advice."
        }


# =============================================================================
# HTML EMAIL BUILDER
# =============================================================================
def f(v, d=2):
    try: return f"{float(v):.{d}f}" if v not in (None,"","N/A") else "N/A"
    except: return str(v) if v else "N/A"

def fp(v):
    try:
        n = float(v)
        return f"{'+'if n>=0 else ''}{n:.1f}%"
    except: return "N/A"

def fvol(v):
    try:
        n = float(v)
        if n>=1e9: return f"{n/1e9:.2f}B"
        if n>=1e6: return f"{n/1e6:.1f}M"
        if n>=1e3: return f"{n/1e3:.0f}K"
        return str(int(n))
    except: return "N/A"

def sc(s):
    s=(s or "").upper()
    if "STRONG BUY" in s: return "#059669"
    if "BUY" in s:        return "#10b981"
    if "WATCH" in s:      return "#d97706"
    return "#dc2626"

def cc(v):
    try: return "#059669" if float(v)>=0 else "#dc2626"
    except: return "#6b7280"

def conf_color(s):
    s=int(s or 0)
    if s>=80: return "#059669"
    if s>=65: return "#10b981"
    if s>=50: return "#d97706"
    return "#dc2626"

def cat_style(c):
    return "background:#ede9fe;color:#5b21b6;border:1px solid #c4b5fd" if str(c).upper()=="GROWTH" \
      else "background:#e0f2fe;color:#075985;border:1px solid #7dd3fc"

def kv(k,v,hi=False):
    bg="background:#f0fdf4;" if hi else ""
    return (f'<div style="display:flex;justify-content:space-between;padding:5px 0;'
            f'border-bottom:1px solid #f1f5f9;font-size:12px;{bg}">'
            f'<span style="color:#64748b">{k}</span>'
            f'<span style="color:#0f172a;font-weight:500">{v}</span></div>')

def conf_bar(score, bd):
    s=int(score or 0); col=conf_color(s)
    rows=""
    for name,got,mx in [("Technical",bd.get("technical",0),30),("Fundamental",bd.get("fundamental",0),25),
                         ("Catalyst",bd.get("catalyst",0),20),("Macro",bd.get("macro_alignment",0),15),
                         ("R/R",bd.get("risk_reward",0),10)]:
        pct=int((got/mx)*100) if mx else 0
        rows+=(f'<div style="margin-bottom:4px"><div style="display:flex;justify-content:space-between;'
               f'font-size:10px;color:#64748b;margin-bottom:2px"><span>{name}</span><span>{got}/{mx}</span></div>'
               f'<div style="background:#e2e8f0;border-radius:3px;height:4px">'
               f'<div style="background:{col};width:{pct}%;height:4px;border-radius:3px"></div></div></div>')
    return (f'<div style="padding:14px 18px;border-bottom:1px solid #e5e7eb;display:flex;gap:14px;align-items:flex-start">'
            f'<div style="text-align:center;min-width:56px">'
            f'<div style="font-size:28px;font-weight:700;color:{col};line-height:1">{s}</div>'
            f'<div style="font-size:9px;color:#94a3b8">/100</div></div>'
            f'<div style="flex:1">{rows}</div></div>')

def pick_card(s, idx, watchlist=False):
    ticker  = s.get("ticker","?")
    score   = s.get("confidence_score",0)
    signal  = s.get("signal","")
    cat     = s.get("category","BALANCED")
    chg     = s.get("price_change_today_pct",0)
    bd      = s.get("confidence_breakdown",{})
    personal= s.get("is_personal_watchlist",False)

    p_badge = ('<span style="font-size:10px;padding:2px 8px;border-radius:20px;'
               'background:#fef3c7;color:#92400e;border:1px solid #fcd34d;margin-left:6px">★ Watchlist</span>'
               ) if personal else ""

    # Targets row
    if not watchlist:
        tgt = "".join([
            f'<div style="padding:10px 8px;border-right:1px solid #e5e7eb;text-align:center">'
            f'<div style="font-size:9px;color:#94a3b8;text-transform:uppercase;margin-bottom:2px">{lb}</div>'
            f'<div style="font-size:12px;font-weight:600;color:{col}">{vl}</div>'
            f'{"<div style=font-size:9px;color:#94a3b8>"+sub+"</div>" if sub else ""}'
            f'</div>'
            for lb,vl,col,sub in [
              ("Entry",      f"${f(s.get('entry_range_low'))}–${f(s.get('entry_range_high'))}", "#0369a1",""),
              ("1-month",    f"${f(s.get('target_1m'))}",  "#059669", f"{fp(s.get('upside_1m_pct'))} · {s.get('target_1m_probability_pct','?')}%"),
              ("6-month",    f"${f(s.get('target_6m'))}",  "#059669", f"{fp(s.get('upside_6m_pct'))} · {s.get('target_6m_probability_pct','?')}%"),
              ("1-year",     f"${f(s.get('target_1y'))}",  "#059669", f"{fp(s.get('upside_1y_pct'))} · {s.get('target_1y_probability_pct','?')}%"),
              ("Stop loss",  f"${f(s.get('stop_loss'))}",  "#dc2626", f"R:R {f(s.get('risk_reward_ratio'),1)}:1"),
            ]
        ])
        tgt_html = f'<div style="display:grid;grid-template-columns:repeat(5,1fr);border-bottom:1px solid #e5e7eb">{tgt}</div>'
    else:
        tgt = "".join([
            f'<div style="padding:10px 8px;border-right:1px solid #e5e7eb;text-align:center">'
            f'<div style="font-size:9px;color:#94a3b8;text-transform:uppercase;margin-bottom:2px">{lb}</div>'
            f'<div style="font-size:12px;font-weight:600;color:{col}">{vl}</div></div>'
            for lb,vl,col in [
              ("Entry",   f"${f(s.get('entry_range_low'))}–${f(s.get('entry_range_high'))}", "#0369a1"),
              ("1-year",  f"${f(s.get('target_1y'))}",  "#059669"),
              ("Upside",  fp(s.get('upside_1y_pct')),   "#059669"),
              ("Stop",    f"${f(s.get('stop_loss'))}",  "#dc2626"),
            ]
        ])
        tgt_html = f'<div style="display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid #e5e7eb">{tgt}</div>'

    # Stats
    if not watchlist:
        c1 = "".join([kv("P/E",f"{f(s.get('pe_ratio'))}x"), kv("Fwd P/E",f"{f(s.get('forward_pe'))}x"),
                      kv("PEG",f(s.get('peg_ratio'))), kv("P/S",f"{f(s.get('ps_ratio'))}x"),
                      kv("EV/EBITDA",f"{f(s.get('ev_ebitda'))}x"), kv("EPS",f"${f(s.get('eps_ttm'))}"),
                      kv("EPS growth",fp(s.get('eps_growth_yoy_pct')),float(s.get('eps_growth_yoy_pct') or 0)>0),
                      kv("Mkt cap",f"${f(s.get('market_cap_b'),1)}B")])
        c2 = "".join([kv("Rev growth YoY",fp(s.get('revenue_growth_yoy_pct')),float(s.get('revenue_growth_yoy_pct') or 0)>15),
                      kv("Rev growth QoQ",fp(s.get('revenue_growth_qoq_pct'))),
                      kv("Gross margin",fp(s.get('gross_margin_pct'))), kv("Op. margin",fp(s.get('operating_margin_pct'))),
                      kv("Net margin",fp(s.get('net_margin_pct'))), kv("FCF yield",fp(s.get('fcf_yield_pct'))),
                      kv("ROE",fp(s.get('roe_pct'))), kv("Debt/equity",f(s.get('debt_to_equity')))])
        c3 = "".join([kv("RSI (14)",str(s.get('rsi_14','N/A'))), kv("MACD",s.get('macd_signal','N/A')),
                      kv("MA signal",s.get('ma_signal','N/A')), kv("Pattern",s.get('chart_pattern','N/A')),
                      kv("Vs 50MA",fp(s.get('price_vs_50ma'))), kv("Vs 200MA",fp(s.get('price_vs_200ma'))),
                      kv("52W high",f"${f(s.get('week52_high'))}"), kv("52W low",f"${f(s.get('week52_low'))}")])
        c4 = "".join([kv("Volume",fvol(s.get('volume_today'))), kv("Avg vol 30d",fvol(s.get('avg_volume_30d'))),
                      kv("Vol ratio",f"{f(s.get('volume_ratio'))}x"), kv("Earnings",s.get('earnings_streak','N/A')),
                      kv("EPS surprise",fp(s.get('last_earnings_surprise_pct'))), kv("Guidance",s.get('guidance','N/A')),
                      kv("Consensus",s.get('analyst_consensus','N/A')), kv("Analyst tgt",f"${f(s.get('analyst_avg_target'))} ({s.get('num_analysts','?')})")])
        stats_html = (f'<div style="display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid #e5e7eb">'
                      + "".join([f'<div style="padding:12px 14px;border-right:1px solid #e5e7eb"><div style="font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;font-weight:600">{t}</div>{b}</div>'
                                 for t,b in [("Valuation",c1),("Growth",c2),("Technical",c3),("Volume & Analysts",c4)]])
                      + '</div>')
    else:
        c1="".join([kv("P/E",f"{f(s.get('pe_ratio'))}x"), kv("52W high",f"${f(s.get('week52_high'))}"),
                    kv("52W low",f"${f(s.get('week52_low'))}"), kv("Analyst tgt",f"${f(s.get('analyst_avg_target'))}")])
        c2="".join([kv("RSI (14)",str(s.get('rsi_14','N/A'))), kv("Signal",signal,True),
                    kv("Consensus",s.get('analyst_consensus','N/A')), kv("Confidence",f"{score}/100")])
        stats_html=(f'<div style="display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid #e5e7eb">'
                    f'<div style="padding:12px 14px;border-right:1px solid #e5e7eb">{c1}</div>'
                    f'<div style="padding:12px 14px">{c2}</div></div>')

    # Analysis block
    if not watchlist:
        analysis = (
            f'<div style="padding:14px 18px;border-bottom:1px solid #e5e7eb">'
            f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:12px">'
            f'<div><div style="font-size:9px;color:#94a3b8;text-transform:uppercase;font-weight:600;margin-bottom:5px">Technical</div>'
            f'<p style="font-size:12px;color:#374151;line-height:1.7;margin:0">{s.get("technical_analysis","N/A")}</p></div>'
            f'<div><div style="font-size:9px;color:#94a3b8;text-transform:uppercase;font-weight:600;margin-bottom:5px">Fundamental</div>'
            f'<p style="font-size:12px;color:#374151;line-height:1.7;margin:0">{s.get("fundamental_analysis","N/A")}</p></div></div>'
            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px">'
            f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:7px;padding:10px">'
            f'<div style="font-size:9px;color:#166534;text-transform:uppercase;font-weight:600;margin-bottom:4px">⚡ Why now</div>'
            f'<p style="font-size:11px;color:#166534;line-height:1.6;margin:0">{s.get("why_now","N/A")}</p></div>'
            f'<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:7px;padding:10px">'
            f'<div style="font-size:9px;color:#92400e;text-transform:uppercase;font-weight:600;margin-bottom:4px">🎯 Catalyst</div>'
            f'<p style="font-size:11px;color:#92400e;line-height:1.6;margin:0">{s.get("catalyst_summary","N/A")}</p></div>'
            f'<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:7px;padding:10px">'
            f'<div style="font-size:9px;color:#1e40af;text-transform:uppercase;font-weight:600;margin-bottom:4px">🌐 Macro</div>'
            f'<p style="font-size:11px;color:#1e40af;line-height:1.6;margin:0">{s.get("geopolitical_factor","N/A")}</p></div>'
            f'</div></div>'
            f'<div style="padding:12px 18px;border-bottom:1px solid #e5e7eb;background:linear-gradient(135deg,#f8fafc,#f0fdf4)">'
            f'<div style="font-size:9px;color:#94a3b8;text-transform:uppercase;font-weight:600;margin-bottom:4px">Victor Kane\'s verdict</div>'
            f'<p style="font-size:13px;color:#0f172a;line-height:1.7;margin:0;font-style:italic">"{s.get("victor_verdict","N/A")}"</p></div>'
            f'<div style="padding:10px 18px;background:#fef2f2">'
            f'<span style="font-size:9px;color:#991b1b;text-transform:uppercase;font-weight:600">⚠ Risks: </span>'
            f'<span style="font-size:11px;color:#991b1b">{s.get("risks","N/A")}</span></div>')
    else:
        analysis=(f'<div style="padding:12px 18px;background:linear-gradient(135deg,#f8fafc,#f0fdf4)">'
                  f'<div style="font-size:9px;color:#94a3b8;text-transform:uppercase;font-weight:600;margin-bottom:4px">Victor\'s note</div>'
                  f'<p style="font-size:12px;color:#0f172a;line-height:1.6;margin:0;font-style:italic">"{s.get("victor_note","N/A")}"</p></div>')

    num = "" if watchlist else f'<span style="font-size:13px;font-weight:700;color:#94a3b8;font-family:monospace">#{idx} </span>'
    return (f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;margin-bottom:18px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06)">'
            f'<div style="padding:14px 18px;background:linear-gradient(135deg,#f8fafc,#f1f5f9);border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;align-items:flex-start">'
            f'<div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:3px">'
            f'{num}<span style="font-size:20px;font-weight:700;color:#0f172a;font-family:monospace">{ticker}</span>'
            f'<span style="font-size:10px;padding:2px 8px;border-radius:20px;{cat_style(cat)};font-weight:600">{cat}</span>{p_badge}</div>'
            f'<div style="font-size:12px;color:#64748b">{s.get("company_name","")} · {s.get("sector","")}'
            f'{"  ·  Next earnings: "+str(s.get("next_earnings_est","")) if s.get("next_earnings_est") and not watchlist else ""}</div></div>'
            f'<div style="text-align:right">'
            f'<div style="font-size:22px;font-weight:700;color:#0f172a">${f(s.get("current_price"))}</div>'
            f'<div style="font-size:12px;color:{cc(chg)};font-weight:500">{fp(chg)} today</div>'
            f'<div style="font-size:11px;font-weight:600;color:{sc(signal)};margin-top:2px">{signal}</div></div></div>'
            f'{"" if watchlist else conf_bar(score, bd)}'
            f'{tgt_html}{stats_html}{analysis}</div>')


def build_email(report, market):
    date_str = report.get("report_date", TODAY)
    risk     = (report.get("risk_level") or "UNKNOWN").upper()
    risk_col = {"LOW":"#059669","MODERATE":"#d97706","HIGH":"#dc2626"}.get(risk,"#6b7280")
    mood     = report.get("market_mood","NEUTRAL")
    mood_col = {"BULLISH":"#059669","NEUTRAL":"#d97706","BEARISH":"#dc2626"}.get(mood,"#6b7280")
    picks    = report.get("top_picks",[])
    watchlist= report.get("watchlist_analysis",[])
    scan     = report.get("full_scan_brief",[])
    growth   = [p for p in picks if str(p.get("category","")).upper()=="GROWTH"]
    balanced = [p for p in picks if str(p.get("category","")).upper()!="GROWTH"]

    # macro bar
    macro_html = (
        f'<div style="background:#fff;border-bottom:1px solid #e2e8f0;padding:16px 32px">'
        f'<div style="max-width:860px;margin:0 auto;display:grid;grid-template-columns:1fr auto;gap:16px;align-items:start">'
        f'<div><div style="font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:.1em;margin-bottom:5px">Victor\'s market read</div>'
        f'<p style="font-size:13px;color:#374151;line-height:1.7;margin:0 0 8px">{report.get("macro_summary","N/A")}</p>'
        f'<div style="font-size:12px;color:#64748b"><strong>Sector rotation:</strong> {report.get("sector_rotation","N/A")}</div></div>'
        f'<div style="display:grid;grid-template-columns:repeat(2,auto);gap:8px;min-width:180px">'
        + "".join([
            f'<div style="text-align:center;padding:8px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:7px">'
            f'<div style="font-size:9px;color:#94a3b8;text-transform:uppercase;margin-bottom:2px">{lb}</div>'
            f'<div style="font-size:14px;font-weight:600;color:{col}">{vl}</div></div>'
            for lb,vl,col in [
              ("Mood",    mood,                                                 mood_col),
              ("VIX",     f(market.get('vix')),                                "#374151"),
              ("S&P 500", fp(market.get('sp500_pct')),   cc(market.get('sp500_pct'))),
              ("Nasdaq",  fp(market.get('nasdaq_pct')),  cc(market.get('nasdaq_pct'))),
            ]
        ])
        + '</div></div></div>')

    def section(title, icon, col, items, wl=False):
        if not items: return ""
        cards = "".join(pick_card(s,i+1,wl) for i,s in enumerate(items))
        return (f'<div style="margin-bottom:8px">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">'
                f'<div style="width:4px;height:28px;background:{col};border-radius:2px"></div>'
                f'<div><div style="font-size:15px;font-weight:600;color:#0f172a">{icon} {title}</div>'
                f'<div style="font-size:11px;color:#64748b">{len(items)} {"pick" if len(items)==1 else "picks"}</div></div></div>'
                f'{cards}</div>')

    brief_html = ""
    if scan:
        g=[b for b in scan if str(b.get("category","")).upper()=="GROWTH"]
        b=[b for b in scan if str(b.get("category","")).upper()!="GROWTH"]
        def bi(items):
            return "".join([
                f'<span style="display:inline-flex;align-items:center;gap:5px;padding:4px 10px;margin:2px;'
                f'background:#f8fafc;border:1px solid #e2e8f0;border-radius:16px;font-size:11px">'
                f'<span style="font-weight:700;color:{"#059669" if x.get("bias")=="BULLISH" else "#dc2626" if x.get("bias")=="BEARISH" else "#d97706"}">{x.get("ticker","")}</span>'
                f'<span style="color:#64748b">{x.get("note","")}</span></span>'
                for x in items])
        brief_html = (f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px 18px;margin-bottom:18px">'
                      f'<div style="font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px">Full scan brief</div>'
                      + (f'<div style="margin-bottom:6px"><span style="font-size:10px;color:#5b21b6;font-weight:600">Growth</span></div>{bi(g)}' if g else "")
                      + (f'<div style="margin-top:8px;margin-bottom:6px"><span style="font-size:10px;color:#075985;font-weight:600">Balanced</span></div>{bi(b)}' if b else "")
                      + '</div>')

    personal_line = f'<div style="font-size:11px;color:#64748b;margin-top:3px">Tracking: {" · ".join(ALL_PERSONAL)}</div>' if ALL_PERSONAL else ""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Victor Kane Report {date_str}</title></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="background:linear-gradient(135deg,#0f172a,#1e3a5f);padding:24px 32px">
  <div style="max-width:860px;margin:0 auto;display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px">
    <div>
      <div style="font-size:10px;color:#475569;text-transform:uppercase;letter-spacing:.12em;margin-bottom:3px">Quant Signal Agent</div>
      <div style="font-size:22px;font-weight:700;color:#fff">Victor Kane's Daily Report</div>
      <div style="font-size:11px;color:#64748b;margin-top:3px">{date_str} · {NOW}</div>
      {personal_line}
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      {''.join([f'<div style="text-align:center;padding:8px 14px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:7px"><div style="font-size:9px;color:#64748b;text-transform:uppercase;margin-bottom:2px">{lb}</div><div style="font-size:14px;font-weight:700;color:{col}">{vl}</div></div>'
                for lb,vl,col in [("Risk",risk,risk_col),("Picks",str(len(picks)),"#fff"),("G/B",f"{len(growth)}/{len(balanced)}","#fff")]])}
    </div>
  </div>
</div>
{macro_html}
<div style="max-width:860px;margin:0 auto;padding:20px 14px">
  {section("🚀 Growth Picks","","#7c3aed",growth)}
  {section("🏛 Balanced Picks","","#0369a1",balanced)}
  {section("⭐ Your Watchlist","","#f59e0b",watchlist,wl=True) if watchlist else ""}
  {brief_html}
  <div style="text-align:center;padding:14px;font-size:10px;color:#94a3b8;line-height:1.7">
    {report.get("disclaimer","For educational purposes only.")}<br>
    Data via yfinance · Analysis by Claude AI · Victor Kane persona · {NOW}
  </div>
</div>
</body></html>"""


# =============================================================================
# SEND EMAIL
# =============================================================================
def send_email(html, subject):
    print(f"  → Sending to {EMAIL_TO}...")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html, "html"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as srv:
        srv.login(EMAIL_FROM, EMAIL_PASSWORD)
        srv.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    print("  → Sent.")


# =============================================================================
# MAIN
# =============================================================================
def main():
    print(f"\n{'='*60}\n  Quant Signal Agent — {NOW}")
    if ALL_PERSONAL: print(f"  Watchlist: {', '.join(ALL_PERSONAL)}")
    print(f"{'='*60}\n")

    # Step 1 — Fetch real market data (no API needed)
    print("[Step 1] Fetching market data via yfinance...")
    market = fetch_market_overview()
    print(f"  → S&P {market['sp500_pct']:+.2f}% | Nasdaq {market['nasdaq_pct']:+.2f}% | VIX {market['vix']:.1f}")

    # Use personal watchlist + defaults; cap at 15 to keep Claude prompt small
    tickers = list(dict.fromkeys(ALL_PERSONAL + DEFAULT_TICKERS))[:15]
    stock_data = fetch_stock_data(tickers)

    # Step 2 — Claude analysis (NO web search — just analyzing pre-fetched data)
    print("\n[Step 2] Victor Kane analysis via Claude...")
    stock_json = json.dumps(stock_data, indent=2)
    prompt     = build_analysis_prompt(stock_json, market, ALL_PERSONAL)
    report     = call_claude_analysis(prompt)

    picks    = report.get("top_picks",[])
    growth   = [p for p in picks if str(p.get("category","")).upper()=="GROWTH"]
    balanced = [p for p in picks if str(p.get("category","")).upper()!="GROWTH"]
    print(f"  → {len(picks)} picks: {len(growth)} growth, {len(balanced)} balanced")

    # Step 3 — Build + send email
    print("\n[Step 3] Building and sending email...")
    html    = build_email(report, market)
    mood    = report.get("market_mood","?")
    risk    = report.get("risk_level","?")
    subject = f"📈 Victor Kane — {TODAY} | {len(picks)} picks ({len(growth)}G/{len(balanced)}B) | {mood} | Risk: {risk}"
    send_email(html, subject)

    print(f"\n{'='*60}\n  Done — report sent to {EMAIL_TO}\n{'='*60}\n")


if __name__ == "__main__":
    main()
