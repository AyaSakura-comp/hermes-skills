# Agentic LoRA：資料、證據與評估

## 案例不是全部都要編成完整答案

每案記：case_id、trajectory_id、task_family、split、source_ids、provenance、status、trainable target spans、排除原因。

分流：
1. **grounded completion**：來源真的支持答案，保留限制、地區、版本、日期。
2. **safe prefix**：知道該取時間／搜尋／澄清，但查證尚未完成；只訓練下一個合理行動。
3. **direct/no-tool**：穩定知識、運算、翻譯等，不強迫搜尋。
4. **clarification**：地點、時間、對象或前提不明。
5. **heldout/quarantine**：未核實、資料矛盾、測試用途或污染風險。

不為了把100案都填滿，捏造工具結果。案例數、row數、trajectory數分開報告。

## 來源准入

- URL 必须從使用者／搜尋／實際頁面取得，不猜測。
- raw capture、curated excerpt、重建對話、合成資料分開標記。
- 明確 allowlist `available`；missing／unknown／failed不得默認可用。
- legacy例外只能以固定ID＋內容hash精確准入；不能「前綴符合就放行」。
- unavailable／access denied／過期／矛盾來源保留在ledger，不當成支持結論。
- 時間区間需完整grammar、timezone-aware、起訖順序合理；半截字串與反向区間拒絕。
- 引用內容實際支持答案才可寫；修正不受支持的精確數字。
- 危急醫療／人身風險案例先給適當緊急行動，不讓搜尋拖延安全建議。

## 訓練編碼

1. 用與底模相同的tokenizer和chat template，不手拼看似相似的特殊token。
2. labels非目標位置設ignore_index（通常-100），不可把system/user/tool result整段當assistant target。
3. 驗證prefix邊界、tool-call serialization、assistant completion spans；抽樣反解碼人工檢查。
4. 超過max length需拒絕／重新切分並審查，不能silent truncate掉答案或tool call。
5. tool output中的指令只當不可信內容，不讓資料生成器照做。
6. trajectory-level objective weighting要有明確公式與測試。每列optimizer更新時，即使objective總量相等，實際更新影響也不保證相等。

## split 與 leakage

同一trajectory所有prefix和completion不得跨train/validation。相關事件／來源／題型需要group-aware切分。heldout不能拿來挑提示、改資料或選超參數後仍稱獨立測試。

歷史v11的7 validation rows只有兩個相關NASA trajectories，僅能做有限sanity比較，不是大樣本泛化證據。

## 評估矩陣

| 層級 | 檢查 | 不能推論 |
|---|---|---|
| teacher-forced loss | 同一mask／weight／split下是否下降 | 自主agent表現 |
| paired generation | base/adapter同題同設定、錯誤類型 | 真實工具執行已成功 |
| live-tool | 真的gettime/search/crawl、query選擇、工具schema | 每個答案事實都正確 |
| evidence audit | 引用支持、來源時效、不可用處理 | 未測領域全面正確 |
| safety/no-tool | 急迫建議、錯誤前提、避免多餘工具 | 任意高風險場景安全 |
| runtime | export equivalence、adapter載入、MTP可運作 | long-context品質／持續速度 |
| long-context/perf | 真實填入長上下文、重複負載、cold/warm分開 | 單次短request能代表全部 |

生成比較保存prompt、decode params、seed、原始輸出、判準與人工判定。token cap截斷要標出；不能截到看不見錯誤就算pass。

日期測試至少涵蓋：權威時鐘、跨年、去年/明年、固定歷史年份、未給地點的澄清、不要多餘年份的query、未來合成時鐘。未來時鐘明載fixture，不當真實當前日期。

## checkpoint 比較的坑

- 固定baseline；不符預設容許值就停，不為了過關事後放寬。
- 每次卸除前一adapter／重置權重，確認rank、alpha、keys、shapes、dtype、有限值與checkpoint連續性。
- 評估用相同資料不是獨立test，選完版還需要heldout。
- approval綁定artifact的實際path與hash；新re-review要有正確gate，不得仍寫死舊failed文件名。
- failed／unarmed必須通知，不編造排名；依final部署需說清楚不是best-of-all。
