# 🛒 亚马逊 AI 选品分析 · Amazon Product Picker

A Flask web app that helps you evaluate Amazon products for selection. Feed it
the metrics you already collect with **Helium 10 / SellerSprite / SIF**, and
Claude AI scores the product across five dimensions and gives you a clear
**Go / Maybe / No-Go** verdict — on screen and as a downloadable Excel report.

## Features

- **Two ways to input data**
  - 📄 **Upload Excel** — drop in a filled spreadsheet in the same 69-column
    template as your sample (data read from row 3).
  - ✍️ **Manual entry** — a clean form grouped into collapsible sections
    (basics, sales, financials, logistics, ads, keywords, competition, visuals,
    consumer insights, marketing).
- **AI scorecard** — Claude (`claude-sonnet-4-6`) rates the product 0–10 on:
  - 市场机会 Market Opportunity
  - 盈利能力 Profitability
  - 竞争程度 Competition Level
  - 产品质量信号 Product Quality Signal
  - 趋势与持续性 Trend & Longevity
  - …plus an **overall score** and **Go / Maybe / No-Go** verdict with reasoning,
    key risks, and key opportunities.
- **Excel report** — download a formatted `AI分析` sheet appended to your
  original workbook.

## Quick start

```bash
# 1. Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Set your Anthropic API key
cp .env.example .env
# then edit .env and paste your key:  ANTHROPIC_API_KEY=sk-ant-...

# 3. Run the app
python app.py
```

Open <http://localhost:5000> in your browser.

## How it works

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Excel upload │────▶│              │     │  claude_analyzer │
│      or       │     │    app.py    │────▶│  (Claude API)    │
│  manual form  │────▶│   (Flask)    │     │  scores + verdict│
└──────────────┘     └──────┬───────┘     └────────┬─────────┘
                            │                       │
                            ▼                       ▼
                   ┌──────────────┐        ┌──────────────────┐
                   │ on-screen    │        │  excel_handler   │
                   │ scorecard    │        │  AI分析 .xlsx     │
                   └──────────────┘        └──────────────────┘
```

## Project structure

| File | Purpose |
|------|---------|
| `app.py` | Flask routes: `/` (UI), `/analyze` (JSON), `/upload` (Excel), `/download/<id>` |
| `claude_analyzer.py` | Builds the Chinese analysis prompt and calls the Claude API |
| `excel_handler.py` | Parses the 69-column template and writes the formatted report |
| `templates/index.html` | Single-page UI (Tailwind CDN) with tabs, form, and results |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for your API key |

## The 69 metrics

The template covers everything from your sample: product/brand/ASIN, monthly
sales, variants, rating & reviews, full cost & profit breakdown (cost RMB/USD,
commission, FBA, first-leg shipping, exchange rate, gross profit & margin),
package dimensions, CPC / ROAS / ad share, up to 5 keywords with 3-year trends,
visuals (images / video / A+), and qualitative insights (consumer profile, use
cases, unmet needs, pros/cons, purchase motivation, return reasons, repurchase
cycle). Missing fields are handled gracefully.

## Notes

- Requires an Anthropic API key with access to `claude-sonnet-4-6`.
- Analysis results are kept in memory keyed by a UUID for the download endpoint;
  they reset when the server restarts.
