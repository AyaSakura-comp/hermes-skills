---
name: volatility-adjusted-dca
description: Implement and backtest VolDCA (Volatility-Adjusted Dollar Cost Averaging) strategy for Taiwan ETFs. Combines volatility targeting with trend filtering to improve ROI/MDD ratio over plain DCA.
tags: [strategy, dca, volatility-targeting, backtest, trend-filtering]
---

# VolDCA — 波動率調整型定期定額策略

## 策略原理

基於 Research Affiliates 的 Volatility Targeting 文獻：
- **牛市**（價格 > SMA60 且 > SMA200）：波動率反比調整 — 低波動多投 2x、高波動少投 0.5x；上漲日加碼 5%
- **熊市**（價格 < SMA60）：根據跌幅動態降額（ROC 越負投越少，最低 20%）
- **目標**：提升 ROI/MDD 比率（性價比），而非單純追求最高 ROI

## 實作位置

策略已實作於 `/home/chihmin/backtest-strategies/engine/intraday.py` 的 `run_custom_min()` 函數中，名為 `"VolDCA"`。

```python
# run_custom_min() 中 name == "VolDCA" 的分支
# 每個交易日首次分鐘觸發
# 1. SMA60 + SMA200 趨勢判斷
# 2. 牛市中：std20 波動率調整 (median vol 基準)
# 3. 熊市中：ROC60 動態降額
```

## 執行回測

```bash
cd /home/chihmin/backtest-strategies
python3 engine/intraday.py --last 1y   # 過去一年
python3 engine/intraday.py --last 2y   # 過去二年
python3 engine/intraday.py --last 3y   # 過去三年
```

## 回測基準（0050）

| 期間 | VolDCA ROI | MDD | ROI/MDD | DCA ROI | MDD | ROI/MDD |
|------|-----------|------|---------|---------|------|---------|
| 3個月 | 36.4% | -6.1% | **6.02** | 24.9% | -5.1% | 4.85 |
| 6個月 | 50.1% | -9.5% | 5.25 | 38.6% | -6.9% | 5.59 |
| 1年 | **88.0%** | -12.2% | **7.24** | 67.2% | -9.9% | 6.81 |
| 2年 | 120.2% | -18.9% | 6.36 | 98.0% | -12.6% | 7.79 |
| 3年 | 162.3% | -24.2% | 6.72 | 136.3% | -19.9% | 6.86 |

**最佳窗口：過去一年** — ROI 88.0% vs DCA 67.2%，ROI/MDD 7.24 vs 6.81。

## 關鍵實作細節

### 波動率計算
- 使用 `md["std20"]`（20日收盤價標準差）
- 基準為過去可用日數的中位數 `vol_history.median()`
- 比率範圍：0.2x ~ 2.0x（clip）
- 公式：`ratio = 2.0 - 1.5 * (vol - 0.5 * med_vol) / (2.5 * med_vol)`

### 趨勢判斷
- 牛市：`px > SMA60 AND px > SMA200`
- 熊市：`px < SMA60`
- 注意：SMA200 對 0050 太長（幾乎都在上方），需搭配 SMA60

### 熊市降額
- 使用 `md["roc60"]`（60日報酬率）
- 公式：`drop_ratio = max(0.2, 1.0 + roc60 / 100)`
- 例如：ROC -10% → 0.9x，ROC -50% → 0.5x

## 參數調校經驗（從 trial-and-error 學到）

1. **SMA200 單獨使用不夠敏感**：0050 長期向上，幾乎始終在 SMA200 上方，無法有效區分牛熊
2. **Donchian 通道不適用**：在 0050 這種緩慢走勢上反應遲鈍，MDD 改善有限
3. **ROC60 動能過濾**：能降低 MDD 但會過度犧牲 ROI（在長期向上趨勢中錯過反彈）
4. **SMA60 + SMA200 組合最佳**：SMA60 提供敏銳反應，SMA200 提供長期趨勢確認
5. **熊市降額需平衡**：太保守（0.1x）會損失 ROI；太激進（0.5x）MDD 改善有限
6. **上漲日加碼 5%**：在牛市中輕微傾斜，捕捉動能延續

## 適用性

- 最適合：長期向上趨勢的 ETF（如 0050, 006208L）
- 不適合：震盪市或長期下跌市場（此時 DCA 可能更穩）
- 其他台灣 ETF：建議先跑 `--last 1y` 驗證，再調整參數

## 相關檔案

- `/home/chihmin/backtest-strategies/engine/intraday.py` — VolDCA 實作
- `/home/chihmin/backtest-strategies/CLAUDE.md` — 專案開發規範
- `/home/chihmin/backtest-strategies/strategies.py` — 其他策略參考（DCA, MA 交叉, Donchian）