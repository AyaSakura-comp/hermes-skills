# 故障手冊：先定位，再修改

遇到bug先讀systematic-debugging skill。以下是歷史教訓，不是看到相似字串就盲套patch。

| 症狀 | 核對／根因線索 | 安全下一步 |
|---|---|---|
| 日期問答正常，搜尋卻帶舊年份 | 不同任務層：query生成／tool trace | 重播真實agent payload，別只加「現在幾年」資料 |
| 載入就暴增約60GiB | MoE experts被全量BF16展開 | 查量化模組、materialization與實際tensor清單 |
| HIP compile missing header／ISA失敗 | compiler本體、ROCm headers、rocisa版本不匹配 | 獨立build環境核對；別污染借用venv |
| native kernel只支援部分quant types | forward/backward支援矩陣不同 | 用reference驗證fallback，明確列unsupported |
| converter/tokenizers版本冲突 | 訓練與轉檔環境互相依賴 | 隔離converter venv、offline config，不全域升級 |
| LoRA GGUF少tensor或name錯 | combined LoraTorchTensor filtering | nested／legacy name regression＋逐值比對 |
| train前就memory_guard/-9 | MemAvailable低於門檻，可能有別的工作 | 保存receipt；不擅自kill別人、開swap或降低threshold |
| 提出allocator patch後重跑成功 | patch可能根本沒實作；可用RAM已變 | 對照code hash與起跑RAM，不編造因果 |
| step250 epoch_complete=false | latest periodic checkpoint，不是final狀態 | 查completed steps、final adapter、supervisor exit |
| loss下降很多 | tiny/related validation或模板重複 | 做獨立heldout／paired generation，不宣稱全面成功 |
| evaluator review pass但無法啟動 | gate仍寫死舊failed report路徑 | 改gate需授權與新review；不覆寫歷史failed審查 |
| 有script卻沒有評估排名 | prepared不等於armed／started／completed | 檢查approval/claim/output/result實際存在性 |
| production看似沒有LoRA效果 | alias相同但可能未載入、scale不符 | 查實際adapter API與argv，不靠模型自述 |
| MTP仍快，是否代表draft也套LoRA | target/draft context分離 | 查exact commit與runtime，不推測 |
| 每個新Pi session都warm一次 | server path與client eligibility cacheDir不同 | 驗證local metadata/bin與restore request是否發生 |
| cacheRead很高但耗時仍長 | 先warm再同session命中也會高cacheRead | 抓restoreHTTP與prefill，不只usage欄位 |
| fetch observer沒trace | library可能走undici而非global fetch | 用低敏感diagnostics hook，不記headers/token |
| localhost被拒，但127.0.0.1可用 | loopback驗證過嚴／DNS未安全固定 | 驗證localhost解析＋transport pinning，別偷改模型URL |
| 設定切換後卡住 | queued header/body request無deadline | bounded transport＋lifecycle abort，測取消與重排 |
| test把正式cache metadata改掉 | HOME在import後才隔離／fixture落正式目錄 | 停測，保存checksum evidence，精確復原，先隔離再import |
| 換了extension碼仍舊行為 | persistent worker未重載 | 安全reload/recreate，不刪對話、不重啟模型來碰運氣 |
| GGUF QLoRA图說NF4 | 混淆container和codec | 按實際tensor type畫decode，區分標準QLoRA與GGUF做法 |

## 事故處理

1. 先停止有問題的測試，保存受影響檔案和hash，不靠記憶判斷。
2. 列出可證明被修改的範圍；沒有證據不要宣稱「完全無影響」。
3. 有已知備份才復原；刪除fixture前必須確認path＋預期checksum。
4. 不刪真實KV／底模來掩蓋錯誤。
5. 向使用者說明影響、復原與新增隔離測試。

## 五個常見錯誤結論

- 「可以跑」≠「正確」；「正確一題」≠「全面改善」。
- 「artifact名稱叫best」≠「所有checkpoint已比較」。
- 「same binary」≠「same execution path」。
- 「metadata存在」≠「server保存成功且權重相容」。
- 「訓練授權」≠「部署／公開upload授權」。
