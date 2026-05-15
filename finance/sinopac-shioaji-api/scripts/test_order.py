#!/usr/bin/env python3
"""永豐金 Shioaji API v1.x — 模擬環境下單測試 (零股版)"""

import os, time
from dotenv import load_dotenv
import shioaji as sj
from shioaji.constant import Action, StockPriceType, OrderType

load_dotenv("/home/chihmin/.hermes/.env")

def main():
    # 1. 初始化模擬模式
    api = sj.Shioaji(simulation=True)

    # 2. 登入
    accounts = api.login(
        api_key=os.environ["SIMULATION_API_KEY"],
        secret_key=os.environ["SIMULATION_SECRET_KEY"],
    )
    print(f"[+] Login OK. Stock account: {api.stock_account}")

    # 3. 查看 0050 契約資訊
    contract = api.Contracts.Stocks["0050"]
    print(f"\n[+] Contract 0050: {contract.name}")
    print(f"    reference={contract.reference}  limit_up={contract.limit_up}  unit={contract.unit}")

    # 4. 下單 — 零股買進 1 股 (order_lot="IntradayOdd")
    # 台股 50-200 元區間檔距為 0.1，96.05 → round 到 96.0
    tick_price = round(contract.reference, 1)

    order = sj.order.StockOrder(
        action=Action.Buy,
        price=tick_price,
        quantity=1,                  # 零股數量
        price_type=StockPriceType.LMT,
        order_type=OrderType.ROD,
        order_lot="IntradayOdd",     # ⭐ 盤中零股 (Common=整股 / Odd=盤後零股)
        account=api.stock_account,
    )
    print(f"\n[+] Order: Buy 1 share @ {tick_price} LMT ROD (order_lot={order.order_lot})")

    # 5. 送出委託
    trade = api.place_order(contract=contract, order=order)
    print(f"\n[+] Submitted:")
    print(f"    seqno = {trade.order.seqno}  ordno = {trade.order.ordno}")
    print(f"    status = {trade.status.status}")

    # 6. 等待並查詢狀態
    time.sleep(2)
    api.update_status()
    print(f"\n[+] After update:")
    print(f"    status   = {trade.status.status}")
    print(f"    deal_qty = {trade.status.deal_quantity}")

    # 7. 取消掛單 (模擬單)
    if trade.status.status not in ("Filled", "Cancelled", "Failed"):
        cancel = api.cancel_order(trade)
        time.sleep(1)
        api.update_status()
        print(f"\n[+] Cancelled: {cancel.status.status}")

    api.logout()
    print("\n[+] Done!")

if __name__ == "__main__":
    main()
