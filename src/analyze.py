"""
Quant Signal Agent — Daily Stock Report
Victor Kane persona | Growth + Balanced split | Personal watchlist via GitHub Variable
"""

import os
import json
import urllib.request
import urllib.error
import smtplib
import ssl
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

# ── CREDENTIALS (GitHub Secrets — never edit here) ───────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
EMAIL_FROM        = os.environ["EMAIL_FROM"]
EMAIL_PASSWORD    = os.environ["EMAIL_PASSWORD"]
EMAIL_TO          = os.environ["EMAIL_TO"]

# ── PERSONAL WATCHLIST (GitHub Variable: PERSONAL_WATCHLIST) ─────────────────
# Set this in: Repo → Settings → Secrets and variables → Actions → Variables tab
# Format: comma-separated tickers, e.g.  AAPL, TSLA, NVDA, AMZN
# To update: just edit the Variable — no code changes needed
_raw_watchlist = os.environ.get("PERSONAL_WATCHLIST", "")
PERSONAL_WATCHLIST = [t.strip().upper() for t in _raw_watchlist.split(",") if t.strip()]

# ── EXTRA TICKERS passed at manual trigger time ───────────────────────────────
# When triggering manually via GitHub Actions UI, you can add extra tickers
_extra = os.environ.get("EXTRA_TICKERS", "")
EXTRA_TICKERS = [t.strip().upper() for t in _extra.split(",") if t.strip()]

# ── COMBINED WATCHLIST (personal + any manual extras) ────────────────────────
ALL_PERSONAL = list(dict.fromkeys(PERSONAL_WATCHLIST + EXTRA_TICKERS))  # deduplicated

# ── REPORT DATE ───────────────────────────────────────────────────────────────
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 PROMPT — Market Discovery
# Finds the best candidates from the whole market + evaluates personal watchlist
# ─────────────────────────────────────────────────────────────────────────────
DISCOVERY_PROMPT = f"""
Today is {TODAY}. You are a quantitative research system running a pre-market scan.

Use web_search extensively to find the following RIGHT NOW with live data:

TASK 1 — MARKET DISCOVERY (find the best setups in the whole market):
Search for:
- "top momentum stocks {TODAY}"
- "stocks breaking out today {TODAY}"
- "analyst upgrades today {TODAY}"
- "unusual volume stocks premarket {TODAY}"
- "best growth stocks to buy {TODAY}"
- "hot sectors today {TODAY}"
- "stocks with earnings catalyst {TODAY}"
- Current S&P 500, Nasdaq, and sector ETF performance

TASK 2 — PERSONAL WATCHLIST STATUS:
{"Evaluate these specific tickers the user always wants tracked: " + ", ".join(ALL_PERSONAL) if ALL_PERSONAL else "No personal watchlist set."}
For each: fetch current price, recent news, analyst rating changes, any catalysts.

TASK 3 — MACRO CONTEXT:
Search for current: Fed policy news, interest rate expectations, inflation data,
geopolitical headlines affecting markets, dollar index, VIX level, oil price.

Return ONLY valid JSON (no markdown, no backticks):
{{
  "scan_date": "{TODAY}",
  "macro": {{
    "market_mood": "BULLISH|NEUTRAL|BEARISH",
    "vix": 0.0,
    "sp500_today_pct": 0.0,
    "nasdaq_today_pct": 0.0,
    "fed_note": "one sentence on Fed/rates",
    "key_risk": "biggest macro risk today in one sentence",
    "sector_leaders": ["sector1", "sector2"],
    "sector_laggards": ["sector1", "sector2"],
    "geopolitical_note": "one sentence on geopolitical factor"
  }},
  "discovered_tickers": ["TICK1","TICK2","TICK3","TICK4","TICK5","TICK6","TICK7","TICK8","TICK9","TICK10"],
  "discovery_reasons": {{
    "TICK1": "why discovered — one line",
    "TICK2": "why discovered — one line"
  }},
  "personal_watchlist_status": [
    {{
      "ticker": "XXX",
      "current_price": 0.00,
      "price_change_pct_today": 0.0,
      "signal": "STRONG BUY|BUY|WATCH|AVOID",
      "one_line": "brief status note"
    }}
  ]
}}
"""

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 PROMPT — Deep Analysis (Victor Kane persona)
# ─────────────────────────────────────────────────────────────────────────────
def build_analysis_prompt(tickers, macro_context, personal_status):
    personal_context = ""
    if ALL_PERSONAL:
        personal_context = f"""
PERSONAL WATCHLIST TICKERS (user always tracks these — include them in analysis
even if they don't rank as top picks, they must appear in the watchlist_analysis section):
{", ".join(ALL_PERSONAL)}
"""

    return f"""
Today is {TODAY}. You are Victor Kane — 25 years on Wall Street, former head of
quantitative equities at a top-tier hedge fund. You called NVDA at $12, TSLA at $18,
AMD at $6. You are known for being brutally precise, never vague, always giving exact
levels. You do not tolerate weak setups. Your minimum R:R is 2.5:1.

MACRO CONTEXT FROM PRE-MARKET SCAN:
{json.dumps(macro_context, indent=2)}

{personal_context}

TICKERS TO DEEPLY ANALYSE (use web_search to get LIVE data for each):
{", ".join(tickers)}

For EVERY ticker, search for:
- Current price, today's change, pre-market move
- P/E ratio, forward P/E, PEG ratio, P/S ratio, EV/EBITDA
- Market cap, enterprise value
- Revenue (last 4 quarters + YoY growth), gross margin, operating margin, net income, EPS
- Free cash flow, cash on balance sheet, total debt, debt/equity ratio
- Last 4 earnings: beat or miss and by how much, guidance raised/lowered
- RSI(14), MACD, 50-day MA, 200-day MA, current price vs both MAs
- 52-week high and low, current price position
- Volume today vs 30-day average
- Analyst consensus, average price target, number of analysts
- Insider buying/selling last 90 days
- Institutional ownership % and recent change
- Recent news and upcoming catalysts
- Chart pattern (cup & handle, flag, breakout, consolidation, etc.)

CLASSIFICATION RULES:
- GROWTH: High-growth companies (revenue growth >20% YoY), often tech/biotech/emerging.
  Higher volatility, higher upside. Examples: NVDA, PLTR, CRWD, ARM, SMCI.
- BALANCED: Solid companies with strong fundamentals, moderate growth (5–20% YoY),
  lower volatility. Examples: AAPL, MSFT, GOOGL, JPM, BRK.B.

CONFIDENCE SCORING (0–100):
- Technical setup quality: 30 points max
- Fundamental strength: 25 points max
- Catalyst clarity: 20 points max
- Macro alignment: 15 points max
- Risk/reward ratio: 10 points max
Score each component explicitly. Only recommend BUY if total >= 65.
STRONG BUY requires >= 80.

Return ONLY valid JSON (no markdown, no backticks, no extra text):
{{
  "report_date": "{TODAY}",
  "generated_at": "{NOW}",
  "macro_summary": "3-sentence market overview in Victor's voice — direct, no fluff",
  "risk_level": "LOW|MODERATE|HIGH",
  "sector_rotation": "which sectors seeing money flow in vs out today",
  "top_picks": [
    {{
      "ticker": "XXXX",
      "company_name": "Full Company Name",
      "category": "GROWTH|BALANCED",
      "sector": "Technology|Healthcare|Energy|etc",
      "current_price": 0.00,
      "price_change_today_pct": 0.0,
      "signal": "STRONG BUY|BUY|WATCH|AVOID",
      "confidence_score": 0,
      "confidence_breakdown": {{
        "technical": 0,
        "fundamental": 0,
        "catalyst": 0,
        "macro_alignment": 0,
        "risk_reward": 0
      }},
      "entry_range_low": 0.00,
      "entry_range_high": 0.00,
      "target_1m": 0.00,
      "target_6m": 0.00,
      "target_1y": 0.00,
      "stop_loss": 0.00,
      "upside_1m_pct": 0.0,
      "upside_6m_pct": 0.0,
      "upside_1y_pct": 0.0,
      "target_1m_probability_pct": 0,
      "target_6m_probability_pct": 0,
      "target_1y_probability_pct": 0,
      "risk_reward_ratio": 0.0,
      "pe_ratio": 0.0,
      "forward_pe": 0.0,
      "peg_ratio": 0.0,
      "ps_ratio": 0.0,
      "ev_ebitda": 0.0,
      "eps_ttm": 0.00,
      "eps_growth_yoy_pct": 0.0,
      "market_cap_b": 0.0,
      "revenue_growth_yoy_pct": 0.0,
      "revenue_growth_qoq_pct": 0.0,
      "gross_margin_pct": 0.0,
      "operating_margin_pct": 0.0,
      "net_margin_pct": 0.0,
      "fcf_yield_pct": 0.0,
      "roe_pct": 0.0,
      "debt_to_equity": 0.0,
      "cash_position_b": 0.0,
      "earnings_streak": "beat/miss last 4Q e.g. Beat Beat Beat Miss",
      "last_earnings_surprise_pct": 0.0,
      "guidance": "Raised|Maintained|Lowered|N/A",
      "volume_today": 0,
      "avg_volume_30d": 0,
      "volume_ratio": 0.0,
      "week52_high": 0.00,
      "week52_low": 0.00,
      "price_vs_52h_pct": 0.0,
      "rsi_14": 0,
      "macd_signal": "BULLISH|NEUTRAL|BEARISH",
      "macd_histogram": "POSITIVE|NEGATIVE",
      "price_vs_50ma": 0.0,
      "price_vs_200ma": 0.0,
      "ma_signal": "GOLDEN CROSS|ABOVE BOTH|ABOVE 200 ONLY|BELOW BOTH|DEATH CROSS",
      "chart_pattern": "Cup & Handle|Bull Flag|Breakout|Consolidation|Ascending Triangle|etc",
      "support_level": 0.00,
      "resistance_level": 0.00,
      "analyst_consensus": "Strong Buy|Buy|Hold|Sell",
      "analyst_avg_target": 0.00,
      "num_analysts": 0,
      "insider_activity": "Buying|Selling|Neutral",
      "institutional_ownership_pct": 0.0,
      "institutional_change": "Increasing|Decreasing|Stable",
      "next_earnings_est": "YYYY-MM-DD or Q3 2025",
      "catalyst_summary": "Key upcoming catalyst 2 sentences",
      "geopolitical_factor": "Relevant macro/geopolitical factor 1-2 sentences",
      "technical_analysis": "Victor's detailed technical read — 4-5 sentences, exact levels, pattern, confirmation signals",
      "fundamental_analysis": "Victor's fundamental take — 4-5 sentences, what the numbers say, quality of the business",
      "victor_verdict": "Victor's personal 3-sentence statement — his exact recommendation, entry rationale, what he's watching for",
      "why_now": "Why THIS week is the right entry — specific, not generic — 2-3 sentences",
      "risks": "Top 2 risks that could invalidate the thesis — specific, not generic",
      "is_personal_watchlist": false
    }}
  ],
  "watchlist_analysis": [
    {{
      "ticker": "XXX",
      "company_name": "Full Name",
      "category": "GROWTH|BALANCED",
      "current_price": 0.00,
      "price_change_today_pct": 0.0,
      "signal": "STRONG BUY|BUY|WATCH|AVOID",
      "confidence_score": 0,
      "entry_range_low": 0.00,
      "entry_range_high": 0.00,
      "target_1y": 0.00,
      "stop_loss": 0.00,
      "upside_1y_pct": 0.0,
      "pe_ratio": 0.0,
      "week52_high": 0.00,
      "week52_low": 0.00,
      "rsi_14": 0,
      "analyst_consensus": "Strong Buy|Buy|Hold|Sell",
      "analyst_avg_target": 0.00,
      "victor_note": "Victor's 2-sentence take on this stock today",
      "is_personal_watchlist": true
    }}
  ],
  "full_scan_brief": [
    {{"ticker": "XXX", "bias": "BULLISH|NEUTRAL|BEARISH", "note": "one line", "category": "GROWTH|BALANCED"}}
  ],
  "disclaimer": "For educational purposes only. Not financial advice. Always do your own research."
}}

Include ALL personal watchlist tickers in watchlist_analysis.
Include top picks in top_picks (only STRONG BUY and BUY signals, confidence >= 65).
Separate GROWTH and BALANCED clearly via the category field.
"""


# ─────────────────────────────────────────────────────────────────────────────
# API CALLS
# ─────────────────────────────────────────────────────────────────────────────
def call_claude(prompt, label="Claude API"):
    print(f"  → {label}...")
    payload = json.dumps({
        "model": "claude-sonnet-4-5",
        "max_tokens": 8000,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "web-search-2025-03-05,interleaved-thinking-2025-05-14"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"  ✗ API error {e.code}: {body}")
        raise

    full_text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            full_text += block.get("text", "")

    full_text = full_text.strip()
    # Strip markdown fences
    if "```" in full_text:
        parts = full_text.split("```")
        for part in parts:
            if part.startswith("json"):
                part = part[4:]
            part = part.strip()
            if part.startswith("{"):
                full_text = part
                break

    start = full_text.find("{")
    end   = full_text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON found in {label} response.\nRaw: {full_text[:500]}")

    return json.loads(full_text[start:end])


# ─────────────────────────────────────────────────────────────────────────────
# HTML HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def f(val, d=2):
    if val is None: return "N/A"
    try: return f"{float(val):.{d}f}"
    except: return str(val)

def fp(val):
    if val is None: return "N/A"
    try:
        v = float(val)
        return f"{'+'if v>0 else ''}{v:.1f}%"
    except: return str(val)

def fvol(val):
    if val is None: return "N/A"
    try:
        v = float(val)
        if v >= 1e9: return f"{v/1e9:.2f}B"
        if v >= 1e6: return f"{v/1e6:.1f}M"
        if v >= 1e3: return f"{v/1e3:.0f}K"
        return str(int(v))
    except: return str(val)

def sig_col(s):
    s = (s or "").upper()
    if "STRONG BUY" in s: return "#059669"
    if "BUY" in s:        return "#10b981"
    if "WATCH" in s:      return "#d97706"
    return "#dc2626"

def chg_col(v):
    try: return "#059669" if float(v) >= 0 else "#dc2626"
    except: return "#6b7280"

def conf_bar_color(score):
    s = int(score or 0)
    if s >= 80: return "#059669"
    if s >= 65: return "#10b981"
    if s >= 50: return "#d97706"
    return "#dc2626"

def conf_label(score):
    s = int(score or 0)
    if s >= 80: return ("STRONG BUY", "#d1fae5", "#065f46", "#6ee7b7")
    if s >= 65: return ("BUY",        "#d1fae5", "#065f46", "#6ee7b7")
    if s >= 50: return ("WATCH",      "#fef3c7", "#92400e", "#fcd34d")
    return              ("AVOID",      "#fee2e2", "#991b1b", "#fca5a5")

def cat_badge(cat):
    if (cat or "").upper() == "GROWTH":
        return "background:#ede9fe;color:#5b21b6;border:1px solid #c4b5fd"
    return "background:#e0f2fe;color:#075985;border:1px solid #7dd3fc"

def kv_row(k, v, highlight=False):
    bg = "background:#f0fdf4;" if highlight else ""
    return (f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:5px 0;border-bottom:1px solid #f1f5f9;font-size:12px;{bg}">'
            f'<span style="color:#64748b">{k}</span>'
            f'<span style="color:#0f172a;font-weight:500">{v}</span></div>')


def confidence_bar_html(score, breakdown):
    s     = int(score or 0)
    color = conf_bar_color(s)
    label, bg, tc, bc = conf_label(s)
    bars  = ""
    components = [
        ("Technical",    breakdown.get("technical", 0),    30),
        ("Fundamental",  breakdown.get("fundamental", 0),  25),
        ("Catalyst",     breakdown.get("catalyst", 0),     20),
        ("Macro align.", breakdown.get("macro_alignment",0),15),
        ("Risk/Reward",  breakdown.get("risk_reward", 0),  10),
    ]
    for name, got, max_pts in components:
        pct = int((got / max_pts) * 100) if max_pts else 0
        bars += f"""
        <div style="margin-bottom:5px">
          <div style="display:flex;justify-content:space-between;font-size:10px;
                      color:#64748b;margin-bottom:2px">
            <span>{name}</span><span>{got}/{max_pts}</span>
          </div>
          <div style="background:#e2e8f0;border-radius:4px;height:5px">
            <div style="background:{color};width:{pct}%;height:5px;border-radius:4px;
                        transition:width .3s"></div>
          </div>
        </div>"""
    return f"""
    <div style="padding:16px 20px;border-bottom:1px solid #e5e7eb">
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
        <div style="text-align:center;min-width:64px">
          <div style="font-size:32px;font-weight:700;color:{color};line-height:1">{s}</div>
          <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em">/ 100</div>
        </div>
        <div style="flex:1">
          <div style="font-size:11px;padding:3px 10px;border-radius:20px;
                      background:{bg};color:{tc};border:1px solid {bc};
                      display:inline-block;font-weight:600;margin-bottom:8px">{label}</div>
          {bars}
        </div>
      </div>
    </div>"""


def stock_card_html(s, idx, is_watchlist=False):
    ticker   = s.get("ticker", "?")
    score    = s.get("confidence_score", 0)
    signal   = s.get("signal", "")
    cat      = s.get("category", "BALANCED")
    chg      = s.get("price_change_today_pct", 0)
    personal = s.get("is_personal_watchlist", False)

    personal_badge = (
        '<span style="font-size:10px;padding:2px 8px;border-radius:20px;'
        'background:#fef3c7;color:#92400e;border:1px solid #fcd34d;margin-left:6px">'
        '★ Your watchlist</span>'
    ) if personal else ""

    breakdown = s.get("confidence_breakdown", {}) if not is_watchlist else {}

    # targets section
    if not is_watchlist:
        targets_html = f"""
        <div style="display:grid;grid-template-columns:repeat(5,1fr);
                    border-bottom:1px solid #e5e7eb;text-align:center">
          {"".join([
            f'<div style="padding:12px 8px;border-right:1px solid #e5e7eb">'
            f'<div style="font-size:9px;color:#94a3b8;text-transform:uppercase;'
            f'letter-spacing:.05em;margin-bottom:3px">{lbl}</div>'
            f'<div style="font-size:13px;font-weight:600;color:{col}">{val}</div>'
            f'{"<div style=font-size:9px;color:#94a3b8>" + sub + "</div>" if sub else ""}'
            f'</div>'
            for lbl,val,col,sub in [
              ("Entry range",   f"${f(s.get('entry_range_low'))}–${f(s.get('entry_range_high'))}", "#0369a1",""),
              ("1-month",       f"${f(s.get('target_1m'))}",  "#059669", f"{fp(s.get('upside_1m_pct'))} · {s.get('target_1m_probability_pct','?')}% prob"),
              ("6-month",       f"${f(s.get('target_6m'))}",  "#059669", f"{fp(s.get('upside_6m_pct'))} · {s.get('target_6m_probability_pct','?')}% prob"),
              ("1-year",        f"${f(s.get('target_1y'))}",  "#059669", f"{fp(s.get('upside_1y_pct'))} · {s.get('target_1y_probability_pct','?')}% prob"),
              ("Stop loss",     f"${f(s.get('stop_loss'))}",  "#dc2626", f"R:R {f(s.get('risk_reward_ratio'),1)}:1"),
            ]
          ])}
        </div>"""
    else:
        targets_html = f"""
        <div style="display:grid;grid-template-columns:repeat(4,1fr);
                    border-bottom:1px solid #e5e7eb;text-align:center">
          {"".join([
            f'<div style="padding:10px 8px;border-right:1px solid #e5e7eb">'
            f'<div style="font-size:9px;color:#94a3b8;text-transform:uppercase;'
            f'letter-spacing:.05em;margin-bottom:3px">{lbl}</div>'
            f'<div style="font-size:13px;font-weight:600;color:{col}">{val}</div></div>'
            for lbl,val,col in [
              ("Entry range",  f"${f(s.get('entry_range_low'))}–${f(s.get('entry_range_high'))}", "#0369a1"),
              ("1-year target",f"${f(s.get('target_1y'))}",  "#059669"),
              ("Upside",       fp(s.get('upside_1y_pct')),   "#059669"),
              ("Stop loss",    f"${f(s.get('stop_loss'))}",  "#dc2626"),
            ]
          ])}
        </div>"""

    # stats columns
    col1 = "".join([
        kv_row("P/E ratio",          f"{f(s.get('pe_ratio'))}x"),
        kv_row("Forward P/E",        f"{f(s.get('forward_pe'))}x"),
        kv_row("PEG ratio",          f(s.get('peg_ratio'))),
        kv_row("P/S ratio",          f"{f(s.get('ps_ratio'))}x"),
        kv_row("EV/EBITDA",          f"{f(s.get('ev_ebitda'))}x"),
        kv_row("EPS (TTM)",          f"${f(s.get('eps_ttm'))}"),
        kv_row("EPS growth YoY",     fp(s.get('eps_growth_yoy_pct')), float(s.get('eps_growth_yoy_pct') or 0) > 0),
        kv_row("Market cap",         f"${f(s.get('market_cap_b'),1)}B"),
    ]) if not is_watchlist else "".join([
        kv_row("P/E ratio",   f"{f(s.get('pe_ratio'))}x"),
        kv_row("52W high",    f"${f(s.get('week52_high'))}"),
        kv_row("52W low",     f"${f(s.get('week52_low'))}"),
        kv_row("Analyst tgt", f"${f(s.get('analyst_avg_target'))}"),
    ])

    col2 = "".join([
        kv_row("Rev growth YoY",  fp(s.get('revenue_growth_yoy_pct')), float(s.get('revenue_growth_yoy_pct') or 0) > 15),
        kv_row("Rev growth QoQ",  fp(s.get('revenue_growth_qoq_pct'))),
        kv_row("Gross margin",    fp(s.get('gross_margin_pct'))),
        kv_row("Op. margin",      fp(s.get('operating_margin_pct'))),
        kv_row("Net margin",      fp(s.get('net_margin_pct'))),
        kv_row("FCF yield",       fp(s.get('fcf_yield_pct'))),
        kv_row("ROE",             fp(s.get('roe_pct'))),
        kv_row("Debt/equity",     f(s.get('debt_to_equity'))),
    ]) if not is_watchlist else "".join([
        kv_row("RSI (14)",   str(s.get('rsi_14','N/A'))),
        kv_row("Signal",     signal, True),
        kv_row("Consensus",  s.get('analyst_consensus','N/A')),
        kv_row("Confidence", f"{score}/100"),
    ])

    col3 = "".join([
        kv_row("RSI (14)",          str(s.get('rsi_14','N/A'))),
        kv_row("MACD",              s.get('macd_signal','N/A')),
        kv_row("MA signal",         s.get('ma_signal','N/A')),
        kv_row("Chart pattern",     s.get('chart_pattern','N/A')),
        kv_row("Vs 50-day MA",      fp(s.get('price_vs_50ma'))),
        kv_row("Vs 200-day MA",     fp(s.get('price_vs_200ma'))),
        kv_row("52W high",          f"${f(s.get('week52_high'))}"),
        kv_row("52W low",           f"${f(s.get('week52_low'))}"),
    ]) if not is_watchlist else ""

    col4 = "".join([
        kv_row("Volume today",       fvol(s.get('volume_today'))),
        kv_row("Avg vol (30d)",      fvol(s.get('avg_volume_30d'))),
        kv_row("Volume ratio",       f"{f(s.get('volume_ratio'))}x"),
        kv_row("Earnings streak",    s.get('earnings_streak','N/A')),
        kv_row("Last EPS surprise",  fp(s.get('last_earnings_surprise_pct'))),
        kv_row("Guidance",           s.get('guidance','N/A')),
        kv_row("Analyst consensus",  s.get('analyst_consensus','N/A')),
        kv_row("Analyst avg target", f"${f(s.get('analyst_avg_target'))} ({s.get('num_analysts','?')} analysts)"),
    ]) if not is_watchlist else ""

    stats_html = ""
    if not is_watchlist:
        cols = [
            ("Valuation & earnings", col1),
            ("Growth & margins",     col2),
            ("Technical",            col3),
            ("Volume & analysts",    col4),
        ]
        stats_html = f"""
        <div style="display:grid;grid-template-columns:repeat(4,1fr);
                    gap:0;border-bottom:1px solid #e5e7eb">
          {"".join([
            f'<div style="padding:14px 16px;border-right:1px solid #e5e7eb">'
            f'<div style="font-size:9px;color:#94a3b8;text-transform:uppercase;'
            f'letter-spacing:.06em;margin-bottom:8px;font-weight:600">{title}</div>'
            f'{body}</div>'
            for title, body in cols
          ])}
        </div>"""
    else:
        stats_html = f"""
        <div style="display:grid;grid-template-columns:1fr 1fr;
                    gap:0;border-bottom:1px solid #e5e7eb">
          <div style="padding:14px 16px;border-right:1px solid #e5e7eb">{col1}</div>
          <div style="padding:14px 16px">{col2}</div>
        </div>"""

    analysis_html = ""
    if not is_watchlist:
        analysis_html = f"""
        <div style="padding:16px 20px;border-bottom:1px solid #e5e7eb">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:14px">
            <div>
              <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;
                          letter-spacing:.06em;font-weight:600;margin-bottom:6px">Technical analysis</div>
              <p style="font-size:12px;color:#374151;line-height:1.7;margin:0">
                {s.get('technical_analysis','N/A')}</p>
            </div>
            <div>
              <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;
                          letter-spacing:.06em;font-weight:600;margin-bottom:6px">Fundamental analysis</div>
              <p style="font-size:12px;color:#374151;line-height:1.7;margin:0">
                {s.get('fundamental_analysis','N/A')}</p>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px">
              <div style="font-size:9px;color:#166534;text-transform:uppercase;
                          letter-spacing:.06em;font-weight:600;margin-bottom:5px">⚡ Why now</div>
              <p style="font-size:11px;color:#166534;line-height:1.6;margin:0">{s.get('why_now','N/A')}</p>
            </div>
            <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px">
              <div style="font-size:9px;color:#92400e;text-transform:uppercase;
                          letter-spacing:.06em;font-weight:600;margin-bottom:5px">🎯 Catalyst</div>
              <p style="font-size:11px;color:#92400e;line-height:1.6;margin:0">{s.get('catalyst_summary','N/A')}</p>
            </div>
            <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:12px">
              <div style="font-size:9px;color:#1e40af;text-transform:uppercase;
                          letter-spacing:.06em;font-weight:600;margin-bottom:5px">🌐 Geopolitical</div>
              <p style="font-size:11px;color:#1e40af;line-height:1.6;margin:0">{s.get('geopolitical_factor','N/A')}</p>
            </div>
          </div>
        </div>
        <div style="padding:14px 20px;border-bottom:1px solid #e5e7eb;
                    background:linear-gradient(135deg,#f8fafc,#f0fdf4)">
          <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;
                      letter-spacing:.06em;font-weight:600;margin-bottom:6px">
            Victor Kane's verdict
          </div>
          <p style="font-size:13px;color:#0f172a;line-height:1.7;margin:0;font-style:italic">
            "{s.get('victor_verdict','N/A')}"
          </p>
        </div>
        <div style="padding:12px 20px;background:#fef2f2">
          <span style="font-size:9px;color:#991b1b;text-transform:uppercase;
                       letter-spacing:.06em;font-weight:600">⚠ Risks: </span>
          <span style="font-size:11px;color:#991b1b">{s.get('risks','N/A')}</span>
        </div>"""
    else:
        analysis_html = f"""
        <div style="padding:14px 20px;background:linear-gradient(135deg,#f8fafc,#f0fdf4)">
          <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;
                      letter-spacing:.06em;font-weight:600;margin-bottom:5px">
            Victor's note
          </div>
          <p style="font-size:12px;color:#0f172a;line-height:1.6;margin:0;font-style:italic">
            "{s.get('victor_note','N/A')}"
          </p>
        </div>"""

    return f"""
    <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;
                margin-bottom:20px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.06)">
      <!-- Card header -->
      <div style="padding:16px 20px;background:linear-gradient(135deg,#f8fafc,#f1f5f9);
                  border-bottom:1px solid #e5e7eb;display:flex;
                  justify-content:space-between;align-items:flex-start">
        <div>
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px">
            {"" if is_watchlist else f'<span style="font-size:13px;font-weight:700;color:#94a3b8;font-family:monospace">#{idx}</span>'}
            <span style="font-size:20px;font-weight:700;color:#0f172a;font-family:monospace">
              {ticker}
            </span>
            <span style="font-size:10px;padding:2px 9px;border-radius:20px;{cat_badge(cat)};font-weight:600">
              {cat}
            </span>
            {personal_badge}
          </div>
          <div style="font-size:12px;color:#64748b">
            {s.get('company_name','')} &nbsp;·&nbsp; {s.get('sector','')}
            {"&nbsp;·&nbsp; Next earnings: " + s.get('next_earnings_est','') if s.get('next_earnings_est') and not is_watchlist else ""}
          </div>
        </div>
        <div style="text-align:right">
          <div style="font-size:22px;font-weight:700;color:#0f172a">
            ${f(s.get('current_price'))}
          </div>
          <div style="font-size:12px;color:{chg_col(chg)};font-weight:500">
            {fp(chg)} today
          </div>
          <div style="font-size:11px;font-weight:600;color:{sig_col(signal)};margin-top:2px">
            {signal}
          </div>
        </div>
      </div>
      {"" if is_watchlist else confidence_bar_html(score, breakdown)}
      {targets_html}
      {stats_html}
      {analysis_html}
    </div>"""


def build_section(title, picks, color, icon):
    if not picks:
        return ""
    cards = "".join(stock_card_html(s, i+1) for i, s in enumerate(picks))
    return f"""
    <div style="margin-bottom:8px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
        <div style="width:4px;height:32px;background:{color};border-radius:2px"></div>
        <div>
          <div style="font-size:16px;font-weight:600;color:#0f172a">{icon} {title}</div>
          <div style="font-size:12px;color:#64748b">{len(picks)} {'pick' if len(picks)==1 else 'picks'}</div>
        </div>
      </div>
      {cards}
    </div>"""


def build_html_email(report, macro):
    date_str  = report.get("report_date", TODAY)
    risk      = (report.get("risk_level") or "UNKNOWN").upper()
    risk_cols = {"LOW":"#059669","MODERATE":"#d97706","HIGH":"#dc2626"}
    risk_col  = risk_cols.get(risk, "#6b7280")
    mood      = macro.get("market_mood","UNKNOWN")
    mood_col  = {"BULLISH":"#059669","NEUTRAL":"#d97706","BEARISH":"#dc2626"}.get(mood,"#6b7280")

    all_picks    = report.get("top_picks", [])
    growth_picks = [p for p in all_picks if (p.get("category","") or "").upper() == "GROWTH"]
    bal_picks    = [p for p in all_picks if (p.get("category","") or "").upper() == "BALANCED"]
    watchlist    = report.get("watchlist_analysis", [])
    scan_brief   = report.get("full_scan_brief", [])

    personal_note = ""
    if ALL_PERSONAL:
        personal_note = f"""
        <div style="font-size:12px;color:#64748b;margin-top:4px">
          Tracking your watchlist: {" · ".join(ALL_PERSONAL)}
        </div>"""

    macro_html = f"""
    <div style="background:#ffffff;border-bottom:1px solid #e2e8f0;padding:18px 32px">
      <div style="max-width:860px;margin:0 auto">
        <div style="display:grid;grid-template-columns:1fr auto;gap:20px;align-items:start">
          <div>
            <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;
                        letter-spacing:.1em;margin-bottom:6px">Victor's market read</div>
            <p style="font-size:13px;color:#374151;line-height:1.7;margin:0 0 10px">
              {report.get('macro_summary','N/A')}
            </p>
            <div style="font-size:12px;color:#64748b">
              <strong style="color:#374151">Sector rotation:</strong> {report.get('sector_rotation','N/A')}
            </div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(2,auto);gap:12px;min-width:200px">
            {"".join([
              f'<div style="text-align:center;padding:10px 14px;background:#f8fafc;'
              f'border:1px solid #e2e8f0;border-radius:8px">'
              f'<div style="font-size:9px;color:#94a3b8;text-transform:uppercase;'
              f'letter-spacing:.06em;margin-bottom:3px">{lbl}</div>'
              f'<div style="font-size:15px;font-weight:600;color:{col}">{val}</div></div>'
              for lbl,val,col in [
                ("Mood",    mood,          mood_col),
                ("VIX",     f(macro.get('vix')), "#374151"),
                ("S&P 500", fp(macro.get('sp500_today_pct')), chg_col(macro.get('sp500_today_pct'))),
                ("Nasdaq",  fp(macro.get('nasdaq_today_pct')), chg_col(macro.get('nasdaq_today_pct'))),
              ]
            ])}
          </div>
        </div>
        <div style="display:flex;gap:16px;margin-top:12px;flex-wrap:wrap">
          <div style="font-size:11px;color:#64748b">
            🏦 <strong style="color:#374151">Fed:</strong> {macro.get('fed_note','N/A')}
          </div>
          <div style="font-size:11px;color:#64748b">
            ⚠ <strong style="color:#374151">Key risk:</strong> {macro.get('key_risk','N/A')}
          </div>
          <div style="font-size:11px;color:#64748b">
            🌐 <strong style="color:#374151">Geopolitical:</strong> {macro.get('geopolitical_note','N/A')}
          </div>
        </div>
      </div>
    </div>"""

    # Watchlist section
    watchlist_html = ""
    if watchlist:
        w_cards = "".join(stock_card_html(w, i+1, is_watchlist=True) for i, w in enumerate(watchlist))
        watchlist_html = f"""
        <div style="margin-bottom:24px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
            <div style="width:4px;height:32px;background:#f59e0b;border-radius:2px"></div>
            <div>
              <div style="font-size:16px;font-weight:600;color:#0f172a">⭐ Your Personal Watchlist</div>
              <div style="font-size:12px;color:#64748b">
                Stocks you always track — {len(watchlist)} tickers analysed today
              </div>
            </div>
          </div>
          {w_cards}
        </div>"""

    # Scan brief
    brief_html = ""
    if scan_brief:
        g_brief = [b for b in scan_brief if (b.get("category","") or "").upper() == "GROWTH"]
        b_brief = [b for b in scan_brief if (b.get("category","") or "").upper() != "GROWTH"]

        def brief_items(items):
            return "".join([
                f'<span style="display:inline-flex;align-items:center;gap:5px;padding:4px 10px;'
                f'margin:2px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:16px;font-size:11px">'
                f'<span style="font-weight:700;color:{"#059669" if b.get("bias")=="BULLISH" else "#dc2626" if b.get("bias")=="BEARISH" else "#d97706"}">'
                f'{b.get("ticker","")}</span>'
                f'<span style="color:#64748b">{b.get("note","")}</span>'
                f'</span>'
                for b in items
            ])

        brief_html = f"""
        <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;
                    padding:18px 20px;margin-bottom:20px">
          <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;
                      letter-spacing:.1em;margin-bottom:12px">Full scan brief</div>
          {"<div style='margin-bottom:8px'><span style='font-size:10px;color:#5b21b6;font-weight:600;text-transform:uppercase;letter-spacing:.06em'>Growth</span></div>" + brief_items(g_brief) if g_brief else ""}
          {"<div style='margin-top:10px;margin-bottom:8px'><span style='font-size:10px;color:#075985;font-weight:600;text-transform:uppercase;letter-spacing:.06em'>Balanced</span></div>" + brief_items(b_brief) if b_brief else ""}
        </div>"""

    total_picks = len(all_picks)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Victor Kane — Stock Report {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,sans-serif">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);padding:28px 32px">
    <div style="max-width:860px;margin:0 auto">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
        <div>
          <div style="font-size:11px;color:#475569;text-transform:uppercase;
                      letter-spacing:.12em;margin-bottom:4px">Quant Signal Agent</div>
          <div style="font-size:24px;font-weight:700;color:#ffffff;letter-spacing:-.02em">
            Victor Kane's Daily Report
          </div>
          <div style="font-size:12px;color:#64748b;margin-top:4px">
            {date_str} &nbsp;·&nbsp; Generated at {NOW}
          </div>
          {personal_note}
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <div style="text-align:center;padding:10px 16px;background:rgba(255,255,255,.06);
                      border:1px solid rgba(255,255,255,.1);border-radius:8px">
            <div style="font-size:9px;color:#64748b;text-transform:uppercase;
                        letter-spacing:.08em;margin-bottom:3px">Market risk</div>
            <div style="font-size:16px;font-weight:700;color:{risk_col}">{risk}</div>
          </div>
          <div style="text-align:center;padding:10px 16px;background:rgba(255,255,255,.06);
                      border:1px solid rgba(255,255,255,.1);border-radius:8px">
            <div style="font-size:9px;color:#64748b;text-transform:uppercase;
                        letter-spacing:.08em;margin-bottom:3px">Top picks</div>
            <div style="font-size:16px;font-weight:700;color:#ffffff">{total_picks}</div>
          </div>
          <div style="text-align:center;padding:10px 16px;background:rgba(255,255,255,.06);
                      border:1px solid rgba(255,255,255,.1);border-radius:8px">
            <div style="font-size:9px;color:#64748b;text-transform:uppercase;
                        letter-spacing:.08em;margin-bottom:3px">Growth / Balanced</div>
            <div style="font-size:16px;font-weight:700;color:#ffffff">
              {len(growth_picks)} / {len(bal_picks)}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  {macro_html}

  <!-- Main content -->
  <div style="max-width:860px;margin:0 auto;padding:24px 16px">

    {build_section("Growth Picks", growth_picks, "#7c3aed", "🚀")}
    {build_section("Balanced Picks", bal_picks,  "#0369a1", "🏛")}
    {watchlist_html}
    {brief_html}

    <div style="text-align:center;padding:16px;font-size:10px;color:#94a3b8;line-height:1.7">
      {report.get('disclaimer','For educational purposes only. Not financial advice.')}<br>
      Powered by Claude AI with live web search &nbsp;·&nbsp; Victor Kane persona &nbsp;·&nbsp; {NOW}
    </div>
  </div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# SEND EMAIL
# ─────────────────────────────────────────────────────────────────────────────
def send_email(html_body, subject):
    print(f"  → Sending email to {EMAIL_TO}...")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html_body, "html"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as srv:
        srv.login(EMAIL_FROM, EMAIL_PASSWORD)
        srv.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    print("  → Email sent.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print(f"  Quant Signal Agent — {NOW}")
    if ALL_PERSONAL:
        print(f"  Personal watchlist: {', '.join(ALL_PERSONAL)}")
    if EXTRA_TICKERS:
        print(f"  Extra tickers (manual run): {', '.join(EXTRA_TICKERS)}")
    print(f"{'='*60}\n")

    # Phase 1 — Discovery
    print("[Phase 1] Market discovery scan...")
    discovery = call_claude(DISCOVERY_PROMPT, "Discovery scan")
    macro     = discovery.get("macro", {})
    discovered = discovery.get("discovered_tickers", [])
    personal_status = discovery.get("personal_watchlist_status", [])

    print(f"  → Discovered {len(discovered)} tickers: {', '.join(discovered)}")
    print(f"  → Market mood: {macro.get('market_mood','?')} | VIX: {macro.get('vix','?')}")

    # Combine all tickers for deep analysis
    all_tickers = list(dict.fromkeys(discovered + ALL_PERSONAL))
    print(f"  → Total for deep analysis: {len(all_tickers)} tickers")

    # Phase 2 — Deep Analysis
    print("\n[Phase 2] Deep analysis (Victor Kane)...")
    time.sleep(2)  # brief pause between API calls
    prompt = build_analysis_prompt(all_tickers, macro, personal_status)
    report = call_claude(prompt, "Deep analysis")

    picks    = report.get("top_picks", [])
    growth   = [p for p in picks if (p.get("category","") or "").upper() == "GROWTH"]
    balanced = [p for p in picks if (p.get("category","") or "").upper() == "BALANCED"]

    print(f"  → {len(picks)} top picks: {len(growth)} growth, {len(balanced)} balanced")

    # Build + send email
    print("\n[Phase 3] Building report and sending email...")
    html     = build_html_email(report, macro)
    mood     = macro.get("market_mood","?")
    risk     = report.get("risk_level","?")
    subject  = (f"📈 Victor Kane — {TODAY} | {len(picks)} picks "
                f"({len(growth)}G/{len(balanced)}B) | {mood} | Risk: {risk}")

    send_email(html, subject)

    print(f"\n{'='*60}")
    print(f"  Done. Report sent to {EMAIL_TO}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
