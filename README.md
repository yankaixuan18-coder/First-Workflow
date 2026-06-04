# Amazon 类目研究采集工具

A local browser automation tool for Amazon category research. Drives your real Edge browser (with extensions) to collect product data and export it to Excel.

**No AI scoring. No cloud dependency. Data collection only.**

---

## 🚀 一键启动 / One-Click Start (recommended)

You do **not** need to run any commands manually.

| OS | What to do |
|----|-----------|
| **Windows** | Double-click **`start.bat`** |
| **Mac / Linux** | Run `chmod +x start.sh` once, then double-click / run **`./start.sh`** |

The launcher automatically:
1. Checks that Python is installed (and tells you where to get it if not)
2. Creates a virtual environment (`.venv`) on first run
3. Installs all dependencies from `requirements.txt` + the browser driver
4. Creates your `.env` config from the template (opens Notepad on Windows so you can set your Edge path)
5. Starts the local web app and **opens your browser** at http://localhost:5000

On later runs it skips the install steps and starts instantly. To stop the app, just close the launcher window.

> ⚠️ **Close all Edge windows before collecting** — Edge cannot share a profile with another process.

The manual setup below is only needed if you prefer to run things yourself.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | https://www.python.org/downloads/ |
| Microsoft Edge | Must be installed; the tool uses your real Edge profile |
| Browser extensions | 卖家精灵 (SellerSprite) and/or SIF installed in Edge |

---

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Playwright browser binaries (optional fallback)

The tool uses your installed Edge via `channel="chrome"`. If Edge is not found on PATH, install the Playwright Chromium build:

```bash
playwright install chromium
```

### 3. Configure your Edge profile path

Copy the example env file and edit it:

```bash
copy .env.example .env      # Windows
cp .env.example .env        # Mac / Linux
```

Open `.env` in a text editor and set `CHROME_USER_DATA_DIR` to your actual Edge User Data path.

**Windows (typical path):**
```
CHROME_USER_DATA_DIR=C:\Users\YourName\AppData\Local\Microsoft\Edge\User Data
CHROME_PROFILE=Default
```

**Mac:**
```
CHROME_USER_DATA_DIR=~/Library/Application Support/Microsoft Edge
CHROME_PROFILE=Default
```

**Linux:**
```
CHROME_USER_DATA_DIR=~/.config/microsoft-edge
CHROME_PROFILE=Default
```

To find your exact path, open Edge and navigate to `edge://version` — look for **Profile Path** and copy the parent directory.

---

## Running the tool

> **Important:** Close all Edge windows completely before starting. Edge cannot share a User Data directory with another process. Check Task Manager (Windows) or Activity Monitor (Mac) for any lingering `msedge.exe` / `Microsoft Edge` processes.

```bash
python main.py
```

Then open **http://localhost:5000** in any browser (Edge, Firefox, etc.).

---

## Usage

1. Enter an **Amazon keyword** (e.g. `camping cot`) or a full **Amazon category/search URL** in the input box.
2. Choose your **marketplace** (amazon.com, amazon.co.uk, etc.).
3. Set **Max Pages** and **Max Products** to control how much data is collected.
4. Optionally check **"Also open detail pages"** to fetch BSR, listing date, and seller information from individual product pages. This is slower but provides richer data.
5. Expand **Edge Settings** if you need to override the profile path.
6. Click **开始采集 (Start)**.
7. Watch the live log. When the status turns green (**完成 Done**), click **下载 Excel** to save your file.

---

## Extension data (卖家精灵 / SIF)

Because the tool uses your real Edge profile with your extensions, 卖家精灵 and SIF will be active in the automated browser window.

The adapters (`extension_adapters/seller_sprite_adapter.py` and `sif_adapter.py`) attempt to read data that the extensions inject into the Amazon page DOM. If the extension has injected its overlay elements by the time the adapter runs, those fields (monthly sales, monthly revenue, search volume, etc.) will appear in the Excel export.

**If extension columns are empty:** The extension may not inject data on search result pages, or the DOM selectors may differ from your installed version. Try enabling **"Also open detail pages"** — extensions often inject more data on product detail pages.

---

## Output

Excel files are saved to the `exports/` folder (created automatically). Filename format:

```
amazon_<keyword>_<YYYYMMDD_HHMMSS>.xlsx
```

### Columns exported

| Column | Field |
|---|---|
| ASIN | Unique Amazon product ID |
| 产品标题(Title) | Product title |
| 品牌(Brand) | Brand name |
| 价格(Price) | Current price |
| 评分(Rating) | Star rating |
| 评论数(Reviews) | Review count |
| 优惠券(Coupon) | Coupon/discount text |
| 配送方式(Fulfillment) | FBA / FBM / Amazon |
| 卖家(Seller) | Seller name |
| 卖家数量(Seller Count) | Number of sellers (from SIF) |
| BSR排名(BSR) | Best Sellers Rank |
| 主类目(Main Category) | Top-level category |
| 子类目(Subcategory) | Sub-category |
| 上架时间(Launch Date) | Date first available |
| 变体数量(Variations) | Number of product variations |
| 月销量(Monthly Sales) | From 卖家精灵 extension |
| 月销售额(Monthly Revenue) | From 卖家精灵 extension |
| 评论增长(Review Growth) | From 卖家精灵 extension |
| 评分趋势(Rating Trend) | From 卖家精灵 extension |
| 关键词搜索量(Search Volume) | From 卖家精灵 extension |
| 主图URL(Main Image URL) | Product image URL |
| 产品URL(Product URL) | Full Amazon product page URL |
| 页码(Page) | Search result page number |
| 采集时间(Timestamp) | UTC timestamp of collection |
| 来源URL(Source URL) | The search/category URL |

---

## Troubleshooting

### "Edge profile is locked"
Another Edge process is still running. On Windows, open Task Manager, find all `msedge.exe` processes, and end them. Then restart the tool.

### "Edge user data directory not found"
The path in your `.env` file is incorrect. Open Edge, go to `edge://version`, copy the **Profile Path** value, and strip the last folder (the profile directory name). That parent directory is your `CHROME_USER_DATA_DIR`.

### Extensions not loading
- Make sure the extensions are installed in the Edge profile specified in `.env`.
- Check that `CHROME_PROFILE` matches the folder name under your User Data directory (usually `Default`, or `Profile 1`, `Profile 2`, etc.).
- Open `edge://version` to confirm the exact profile directory name.

### Amazon shows CAPTCHA
Amazon may show a CAPTCHA if it detects automated access. The tool adds random delays between requests to reduce this. If CAPTCHAs appear frequently:
- Increase `REQUEST_DELAY_MIN` and `REQUEST_DELAY_MAX` in `config.py`.
- Reduce the number of pages collected per session.

### The browser window doesn't open
The tool always runs Edge in headed (visible) mode because extensions require a display. On a headless server, set up a virtual display (e.g. Xvfb on Linux) or run the tool on a desktop machine.

---

## Optional: API provider configuration

The `api_providers/` module contains stubs for Anthropic, OpenAI, Gemini, and DeepSeek. These are **not used** by the data collection pipeline — they are included for future optional AI features. To enable them, add keys to your `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
DEEPSEEK_API_KEY=sk-...
```

And install the corresponding SDK:
```bash
pip install anthropic        # for Anthropic
pip install openai           # for OpenAI / DeepSeek
pip install google-generativeai  # for Gemini
```

---

## Project structure

```
├── main.py                    Flask entry point, routes, task management
├── config.py                  Marketplace URLs, paths, defaults
├── browser_automation.py      Playwright Edge controller
├── amazon_scraper.py          HTML parser for search & detail pages
├── extension_adapters/
│   ├── base_adapter.py        Abstract base class
│   ├── seller_sprite_adapter.py  卖家精灵 DOM reader
│   └── sif_adapter.py         SIF DOM reader
├── exporters/
│   └── excel_exporter.py      openpyxl Excel export
├── api_providers/             Optional LLM provider stubs
├── templates/index.html       Web UI (Tailwind CSS)
├── static/app.js              SSE + fetch client JS
├── exports/                   Generated Excel files (git-ignored)
└── .env                       Your local config (git-ignored)
```
