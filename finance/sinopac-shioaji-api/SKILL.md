---
name: sinopac-shioaji-api
description: 永豐金 Shioaji API 程式交易整合 — 模擬/正式環境登入、下單、查詢、取消流程。含價格檔距陷阱與新版 API 物件結構。
---

# Sinopac Shioaji API — 永豐金證券程式交易

使用永豐金 Shioaji API 進行台股自動化下單的完整流程。

## 環境需求

```bash
pip install shioaji dotenv
```

## 認證金鑰

金鑰存放在 `~/.hermes/.env`：

```bash
SIMULATION_API_KEY=H2Wigj...ey9L
SIMULATION_SECRET_KEY=J9XAWP...U6GY
```

**模擬模式仍需先簽署 API 文件！** 新帳號預設 `signed=False`，必須先到 [Sign Center](https://www.sinotrade.com.tw/newweb/signCenter/signCenterIndex/) 簽署「API 服務條款與風險預告書」，否則：
- 登入回傳 `account_type='H'`, `signed=False`
- `place_order` 回傳 `status_code=406: 'Please sign ... first.'`
- Order Event 回傳 `op_code='88', op_msg='帳號不存在'`

簽署流程：
1. 到 Sign Center 登入並閱讀、簽署文件
2. 簽署完成後重新初始化 API 並重新登入
3. 確認帳號狀態變成 `signed=True` 後即可下單

**CA 憑證：模擬模式不需要（僅正式環境需要 `api.activate_ca()`）**

## 專案結構

```
~/Desktop/trader/
├── CLAUDE.md              # 專案架構與 API 文件連結
├── simulate_order.py      # 下單測試 (零股 / 整股可切換)
├── test_shioaji_login.py  # 登入測試
├── main.py                # 回測與模擬交易
├── config.py              # 全域設定
└── ...
```

**實作前請先讀取 `CLAUDE.md` 或 `GEMINI.md`**（如果存在），以掌握專案架構與既有程式碼。

## 零股交易 (order_lot)

| 值 | 說明 |
|---|---|
| `Common` | 整股 (100股/手) |
| `IntradayOdd` | 盤中零股 (09:00-13:20 可下單) |
| `Odd` | 盤後零股 (13:20-13:30 盤後集合競價) |

```python
order = sj.order.StockOrder(
    action=Action.Buy,
    price=tick_price,
    quantity=1,                  # 零股數量 (不限整數)
    price_type=StockPriceType.LMT,
    order_type=OrderType.ROD,
    order_lot="IntradayOdd",     # ⭐ 零股關鍵參數（字串或 enum 皆可）
    account=api.stock_account,
)
```

**`order_lot` 型別：** Pydantic enum，接受字串 `"IntradayOdd"` 或 `constant.StockOrderLot.IntradayOdd`，兩者皆會自動轉成 enum。

## 核心流程

### 1. 初始化與登入

```python
import shioaji as sj
from shioaji.constant import Action, StockPriceType, OrderType

# 模擬模式 (測試用，營業日 8:00-20:00)
api = sj.Shioaji(simulation=True)

accounts = api.login(
    api_key=os.environ["SIMULATION_API_KEY"],
    secret_key=os.environ["SIMULATION_SECRET_KEY"],
)
# api.stock_account → 預設股票帳戶
```

### 2. 取得契約

```python
contract = api.Contracts.Stocks["0050"]
# 屬性：.reference, .limit_up, .limit_down, .unit, .day_trade, .symbol, .name
# 注意：contract.stock_id 不存在！用 contract.symbol
# 注意：contract.stock_name 不存在！用 contract.name
```

### 3. 下單 (重點：價格檔距)

```python
# ⚠️ 限價價格必須對齊台交所價格檔距：
#   價格 0-50    → 檔距 0.01
#   價格 50-200  → 檔距 0.1    ← 0050 在此區間
#   價格 200-500 → 檔距 0.5
#   價格 500+    → 檔距 1.0
tick_price = round(contract.reference, 1)  # 96.05 → 96.0

order = sj.order.StockOrder(
    action=Action.Buy,
    price=tick_price,
    quantity=1,
    price_type=StockPriceType.LMT,   # LMT=限價 / MKT=市價
    order_type=OrderType.ROD,        # ROD=當日有效 / IOC=立即成交否則取消
    account=api.stock_account,
)

trade = api.place_order(contract=contract, order=order)
```

**`api.Order()` vs `sj.order.StockOrder()`：** 兩者皆可。`api.Order()` 是 factory 方法，自動判斷證券/期貨類型；`sj.order.StockOrder()` 是明確的 Pydantic model，推薦用於明確的證券下單。

### 4. 查詢狀態

```python
api.update_status()

# ⚠️ `api.list_orders()` 在新版 API 中不存在！
# 查詢訂單狀態請改用以下方式：
# - Trade 物件已包含狀態：trade.status.status, trade.status.status_code
# - 使用 callback：api.set_order_callback(handler) 接收即時訂單事件
# - 或從訂單事件回調中自行維護訂單狀態

# Trade 物件結構：
trade.contract   → 契約資訊
trade.order      → 訂單資料
# trade.contract   → 契約資訊
# trade.order      → 訂單資料
#   .seqno         → 委託序號
#   .ordno         → 委託編號
# trade.status     → 狀態物件
#   .status        → PendingSubmit / Submitted / Filled / Cancelled / Failed
#   .status_code   → 00=成功
#   .deal_quantity → 已成交量
#   .deals         → 成交明細

open_orders = api.list_orders()
```

### 5. 取消訂單

```python
cancel = api.cancel_order(trade)  # ⚠️ 接收整個 Trade 物件
```

### 6. 登出

```python
api.logout()
```

## ⚠️ 常見陷阱

1. **價格檔數錯誤 (status_code=88)**：限價未對齊檔距。50-200 元區間必須是 0.1 倍數
2. **`sj.ShioajiOrder` 不存在**：新版 API 用 `sj.order.StockOrder`，不是 `sj.ShioajiOrder`
3. **`trade.id` / `trade.deals` 不存在**：改用 `trade.order.seqno`、`trade.status.deal_quantity`
4. **`cancel_order(contract=, order=)` 不存在**：新版 API 只接受單一 `trade` 物件參數
5. **舊版 `api.Order()` 已棄用**：改用 `sj.order.StockOrder()`

## 使用方式

```bash
cd /home/chihmin/Desktop/hermes-agent
source venv/bin/activate
python sinopac_test.py
```

## 正式環境注意事項

- 需 CA 憑證 (Sinopac.pfx)，先 `api.activate_ca()`
- 需先完成模擬測試並審核通過
- 同一 person_id 最多 5 個同時連線
