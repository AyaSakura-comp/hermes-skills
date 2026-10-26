# LoRA 工作紀錄：<run-id>

> 此為模板，不是授權或通過證明。複製到新工作目錄後逐項填寫；未做保留 not-run。

## 1. 目標與範圍
- authoritative time / timezone：
- 使用者目標與失敗例：
- 工作目錄：
- 不做事項：
- 成功判準／獨立heldout：

## 2. 授權收據
| 階段 | 狀態 | 使用者批准範圍／證據 | 綁定artifact hashes |
|---|---|---|---|
| diagnose/data | not-run | | |
| GPU preflight | not-run | | |
| training | not-run | | |
| checkpoint evaluation | not-run | | |
| production deployment | not-run | | |
| backup/upload | not-run | | |

## 3. 模型與環境
- base path / SHA256 / capture時點：
- upstream revision／與GGUF等價證據或限制：
- tokenizer/config/template hashes：
- quant types／materialized tensors／kernel fallback：
- hardware／RAM／swap／concurrent workloads：
- env paths／packages／compiler／runtime versions：
- git revisions／既有dirty changes與保護方式：

## 4. 資料
- 每split的cases／trajectories／rows分別統計：
- source evidence／unavailable／curated vs raw／synthetic：
- prefix／completion／no-tool／clarification／quarantine：
- masks／tool roundtrip／max length／split leakage tests：
- loss weight formula與限制：
- dataset/evidence manifests／hashes：

## 5. 獨立審查
- reviewer report path/hash：
- failed findings／修正者／re-review：
- 確認approval指向正確通過版本：
- tests／typecheck／static security scan：

## 6. 訓練設定與守門
- rank／alpha／dropout／target names／trainable count：
- optimizer／lr／clip／batch／epochs／seed：
- checkpoint interval／optimizer state保存與否：
- max context／activation checkpointing／dtype：
- host-memory threshold／cgroup／swap／wall limit：
- supervisor path/hash／owned scope/process cleanup：

## 7. Preflight 與每次嘗試（失敗也保留）
| attempt | code/data版本 | 起跑available | peak allocated/reserved | steps | exit/reason | evidence |
|---|---|---|---|---|---|---|
| | | | | | | |

- baseline validation：
- final validation／train loss與定義：
- final artifact／tensor checks：
- periodic snapshots／final狀態分辨：
- 事故／修正／未實作提案：

## 8. 評估
| 檢查 | 狀態 | 結果 | 限制／證據 |
|---|---|---|---|
| baseline reproduction | not-run | | |
| all-checkpoint comparison | not-run | | |
| independent generation | not-run | | |
| live tools + source correctness | not-run | | |
| safety/no-tool regression | not-run | | |
| long-context quality | not-run | | |
| sustained throughput/MTP | not-run | | |

- 選哪個adapter、為何；是否有資格叫best：
- evaluator armed/started/output存在性：

## 9. Export／部署（需單獨授權）
- converter/config/revision／export dtype：
- names/shapes/values等價結果：
- temporary server結果／清理結果：
- 原service argv/env/drop-ins備份：
- 最小新增改動／diff：
- model identity／adapter scale／target vs draft：
- 新KV namespace／client cacheDir或autodiscovery：
- target .bin＋draft .dft相容性／fresh-session restore證據：
- production verification時間／有限測試：
- rollback計畫（是否執行）：

## 10. 備份與回報
- manifest／archive hash／size：
- excluded credentials/base/venvs/KV/private raw conversations：
- destination／visibility／remote blob驗證：
- 未上傳的最新檔案：
- notification channel與成功／失敗實際送達證據：
- 使用者交付檔案：

## 11. 未解決問題與下一個批准點
- blocked原因：
- 已證明／未證明的主張：
- 後續步驟與授權需要：
