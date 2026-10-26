# Qwen GGUF＋LoRA：從提出需求到訓練、部署與快取修正的完整過程紀錄

整理時間：2026-09-17 18:58:11 +0800 CST（Asia/Taipei，主機時鐘確認）。
工作目錄：`/home/chihmin/qwen-date-audit/`
服務模型名稱：`local-llama/qwen3.6-35b-q4`

> **紀錄性質**：依本次對話保留的歷程、摘要與本機證據重建的工程紀錄，不是完整原始 Discord 逐字稿。沒有可靠時間戳的階段只保留先後順序，不補造精確時間。原始資料、訓練 log、審查報告與 checkpoint 仍各自保留；本文件不取代它們。本文所稱「已驗證」均指記錄中的驗證時點，不表示整理本文時重新跑過 GPU 訓練或服務健康檢查。

## 1. 最終結果先摘要

1. 完成一個日期行為小型 pilot，以及正式採納的 **agentic v11 limited trial**。
2. v11 使用 257 筆訓練列、batch size 1、LoRA rank 4，完成 1 epoch／257 steps。
3. 同一小型驗證集的 task-weighted loss：**0.4147183197 → 0.2991137429**。
4. 保留每 10 steps 的 adapter checkpoint（10～250）及 final adapter；沒有刪除舊版本。
5. final adapter 已轉成 F32 GGUF、逐張量核對，並經使用者另外授權，以可回復方式掛載到既有 llama-server。
6. 原始底模 GGUF 沒有覆寫或合併；Discord 模型名稱不需更換。
7. 後續發現部署漏同步 Pi 快取目錄，經定位、獨立審查與實際切換測試，已修正 KV cache manager。
8. extension 修正已 commit 並 push：`b2dbf9de50f24a9d9b7708b5255751a71b7b75a1`，`AyaSakura-comp/pi-kv-cache-manager` 的 `main`。
9. **所有 checkpoint 的比較仍未執行**：獨立審查與 approval gate 綁定問題讓 evaluator 無法啟動。因此 final 是已部署版本，不是證明最好的 checkpoint。
10. 訓練改善、短題推論相容性、長上下文品質、持續速度、真實查證能力，是不同問題；不能由前兩項推論全部改善。

## 2. 最初想解決什麼

使用者要求改善模型在研究、查資料與工具使用時的行為，特別是：

- 有正確時鐘資訊，搜尋 query 卻仍把年份寫成舊的 2025。
- 應使用即時來源時，不能憑記憶回答現況。
- 應先取得時間、判斷年份和相對日期，再構造搜尋。
- 題目是明確歷史年份時，不應粗暴替換成當年。
- 查不到、來源衝突或前提錯誤時，要承認限制、修正前提或澄清。
- 靜態知識不應多餘搜尋；營業時間等問題不應機械地塞入年份。
- 真實資料、引用、工具輸出和訓練目標必須能追溯，不能拿虛構查證當成功證據。

目標是**依時鐘和上下文決策**，不是讓模型死記「現在是 2026」。

## 3. 最初診斷：直接問年份不等於 agent 搜尋行為

第一階段報告日期為 2026-09-16。

- 先做唯讀模型身分、服務設定與合成對話檢查，當時沒有訓練、沒有更改服務。
- 直接推論的有日期案例通過 **14/14**；無日期控制組會自行猜年份。
- 這一階段沒有重現「日期已注入但直接回答固定是 2025」，因此沒有立即認定是權重問題。
- 後續在**搜尋 query 的構造行為**重現帶入舊 2025 的問題，即使工具時鐘已是 2026。
- 這說明簡單日期問答測試不夠，必須測工具決策和研究軌跡。

模型也不是單純原始發布權重：本機是 selective-Q4_0／FlashHead 混合 GGUF，manifest 記錄替換了 92 個 tensor。模型卡一個 base_model 欄位與實際架構不符，沒有把它當可靠來源。原始 HF revision 與既有 GGUF 的逐值等價並未證明。

主要證據：`REPORT.md`、`baseline.jsonl`、`baseline-defaults.jsonl`、`answers.json`、`model-metadata.json`。

## 4. 授權和保護界線

這不是一次「訓練」授權就允許所有操作。歷程分成：

1. 診斷與環境驗證。
2. 小型 pilot 與行為檢查。
3. 資料整理、獨立審查、修正和有限試訓的採納。
4. 正式訓練；第一次因記憶體門檻中止，使用者再次要求 **Start training** 後重跑。
5. checkpoint 比較與 Discord 回報的獨立授權。
6. 使用者以「好啊就這麼做」另外授權可回復部署。
7. 使用者要求快取能隨設定切換，才進行 extension 修改與安裝。
8. 使用者另外要求 commit／push，才將 extension commit 推到遠端。

全程要求保留：原始資料、底模、adapter、checkpoint、舊服務覆寫檔、無關原始碼修改及借用環境。不可用全面 kill 指令處理受保護服務；服務操作走既有 restart-service 流程。

GPU 工作的守門條件：MemAvailable 至少 12 GiB、MemoryMax 64G、禁止 swap、訓練上限兩小時、僅清理工作自身程序與子孫程序。GPU 記憶體不保證全計入 cgroup，因此仍要主機監控。

## 5. 如何在本機把 GGUF＋LoRA 訓練跑起來

### 5.1 硬體與底模

- AMD Radeon 8060S／Strix Halo，gfx1151。
- 約 122.84 GiB 共享記憶體，沒有 swap。
- 底模：
  `/home/chihmin/models/Qwen3.6-35B-A3B-selective-Q4_0-proof/Qwen3.6-35B-A3B-UD-Q4_K_M-selective-Q4_0-flashhead.gguf`
- GGUF 架構 `qwen35moe`；40 個主幹層加 MTP 層、256 experts、每 token 選 8 experts。
- 底模 SHA256：`cfb34904545c3ee779f3649985c1ec29d6a7a3aea70d9840e900300639ac88c9`。此值由 `checkpoint-eval-v1/MODEL-IDENTITY.json` 記錄，於訓練進行期間擷取，不宣稱為起跑當下的校驗收據。

### 5.2 沒有走全量 BF16 experts 展開

為避免約 60 GiB 的不必要 expert BF16 展開，選擇凍結混合 GGUF 權重、僅對必要線性權重有限展開的方式。曾下載但不再需要的 26 個 shard（約 67 GiB）已移除；不是刪除本機原始底模。

- 主模型 92 個 Q4_0 tensors 展開為凍結 BF16；expert 保留量化路徑。
- Q4_0 全體計數另有 93 個 tensors 的統計，不能與主模型 92 個混為同一口徑。
- 該 93 個 tensors 的統計約為 0.5708 GiB packed → 2.0296 GiB BF16。
- 以 `kernels._gguf_kernel=False` 使用已驗證的 fallback 路徑。
- 這是 **GGUF 混合量化＋LoRA**，不是照搬 bitsandbytes NF4 QLoRA。

### 5.3 ROCm／HIP 編譯除錯

- 使用 ROCm 7.14 headers、實際 `clang-23`、`rocisa==0.1.0`，把 `torch-ggml-ops` 建起來。
- 訓練使用 ROCm 7.2 對應環境；build headers/toolchain 與 runtime 版本分開記錄，不能混稱相同。
- Q8_0 native 測試 relative L2：forward 0.00602829、backward 0.0000833422。
- 12 個 native kernel case 中支援 7 個；沒有宣稱全部格式都支援。
- Q4_K／Q6_K fallback 結果與 reference 一致。
- 未修改借用的 Wan2.2 donor 環境。

環境：
- 訓練：`gguf-training-env/bin/python`；torch 2.12.1+rocm7.2、PEFT 0.21.0、bnb 0.50.2。
- 轉檔：`training-env-rocm72/bin/python`，使用離線 HF/Transformers 設定。
- 使用獨立轉檔環境，避免 tokenizers 0.23.2 相容性問題。

### 5.4 LoRA 與轉檔修正

- rank 4、alpha 8、dropout 0，目標為指定的 q_proj／v_proj。
- 20 個投影模組、40 個 A/B tensors，512,000 個可訓練參數。
- 其餘底模凍結；adapter 梯度仍需經凍結底模反傳。
- 修正 `/home/chihmin/llama-mtp-opt/convert_lora_to_gguf.py`：合併的 `LoraTorchTensor` 也要經 `self.filter_tensors()`；nested／legacy naming 測試通過。
- 保留該 repository 既有且無關的 CUDA/HIP 修改。

證據：`BUILD-DEBUG.md`、`ROCM72-PROGRESS.md`、`TRAINING-PREFLIGHT.md`、`test_qwen_conversion.py`、各 probe 與 build log。

## 6. 日期 pilot：先證明有限目標可學習

資料為合成小型模板集，不是私下擷取的私人聊天。

| 項目 | 結果 |
|---|---|
| 訓練／驗證 | 24／8 |
| 訓練 | 5 epochs，120 steps，batch 1，rank 4 |
| 驗證 loss | 0.6880657 → 0.0677169 |
| paired generation | 16 prompts，各做 base／adapter |
| 舊年份搜尋錯誤 | 3/8 → 0/8 |
| 營業時間硬塞年份 | 3/4 → 0/4 |

歷史日期、相對年份和澄清行為在這批測試中保留。這不是 live-web 成功證明，也不是部署證明，更不是全面泛化結果。

產物：`date-pilot/final/adapter.gguf`。
證據：`DATE-PILOT.md`、`ADAPTER-EVALUATION.md`、`adapter-eval-generations.jsonl`。

## 7. 從小 seed 到 100 個案例：資料如何整理與查證

### 7.1 v2 seed

- 35 訓練列／12 trajectories。
- 7 驗證列／2 個相關 NASA trajectories。
- 10 個 curated evidence objects。
- 合成 retrieval 例子另外隔離，不能冒充實際網站回覆。
- 實作 `agentic_training.py`：`encode_record`、`load_split`、`assert_disjoint`、`loss_weights`。
- 原始 12 個 unittest 通過；`pytest` 不存在，沒有為此擅自安裝。

### 7.2 100 個使用者案例與逐版草稿

保留 `user-conversations-v1`～`v8` 和 dataset v3～v10 草稿，不直接覆蓋舊版。

v10：207 train＋7 validation，114 trajectories；含 71 個研究前綴、27 個 no-tool 回答等不同任務類型。

全 100 案審查：

- 74 案需要來源查證、26 案屬靜態知識。
- 179 份來源紀錄，包含 30 份 unavailable。
- 原期待審查：22 pass／62 revise／16 insufficient。
- 合併處理決策：13 retain／62 revise-or-qualify／25 insufficient。
- 67 個 unresolved 項目仍明確保留。
- **100 案 scope-pass 不等於 100 案答案已驗證。**

重要案例修正包含：081／083／089 急迫安全建議、031 歷史情境、091 台北轉 PDT、012 NASA 實際發射來源、046 Microsoft ESU 條件、050 交通資訊、069 星期六市場、099 機場洗澡、094 路考要求。

完整交付曾包括 `fact-check-full-v1/FULL-REVIEW.md`（100 sections）及 `review-001-100.zip`。
ZIP SHA256：`53b4bbca4dd7500a946fbcd821e34bc39318144092525b705b7bf7b1e67dea93`。

### 7.3 v11 修復及限制

修復產物加入 100-ID catalog、ledger、quarantine，保留原始 179 份來源，另加 38 張 source cards 到原有 10 個 seed objects。

100 案分流：
- 27 案：source-grounded completed cases。
- 42 案：僅保留安全的研究前綴，不捏造查證後結論。
- 29 案：直接回答或澄清。
- 2 案：heldout，012／040。

最後採納的訓練資料：
- **257 train rows／110 trajectories**。
- **7 unchanged validation rows／2 個相關 NASA trajectories**。
- **6 heldout rows**。

案例數、trajectory 數、row 數是不同單位；一案可以有多列。

provenance 明載：`grounded_reconstruction_curated_excerpts_not_raw_tool_capture`。它是根據查證來源整理重建的訓練軌跡，不是逐字保存的 live agent tool capture。

審查曾發現時間區間 grammar 接受畸形／倒置区間，以及來源 status 放行過寬。修正為完整 timezone-aware interval grammar 與 `available` allowlist；缺 status 的 legacy C01～C33 必須完全符合釘選身分。另刪除 097 無支持的「150 公尺」。

修復 re-review：24 repair＋12 regression tests 通過；270 rows 的 masks／metadata 擾動檢查、200 tool roundtrips、max 1536、無截斷、54 個舊檔 hash 不變。

證據：`repair-v1/`、`REPAIR-ACCEPTANCE.md`、`repair-parent-final-verification.json`、`agentic-data-v11-limited-trial/`。

## 8. 訓練器、審查與正式批准

正式 runner 加入：

- 每 10 steps 的 atomic adapter snapshot。
- 不 prune 舊 checkpoint。
- 通用 `guarded_agentic_job.py`。
- 重複 signal 與 owned descendant cleanup 防護。
- 精確綁定資料、證據、審查、preflight、runner/helper/audit hashes 的 `require_approval()`。

runner／regression 共 39 tests；加 repair tests 的組合 63 tests。經獨立 re-review 才採納。

採納目錄：`agentic-data-v11-limited-trial/`。原始 draft、舊授權和失敗審查保留。

guarded preflight 跑 2 次 1536-token update：40 tensors 每次均變動、loss／grad 有限；peak allocated/reserved 約 27.89／36.10 GiB，主機最低 available 約 20.97 GiB。

注意：trajectory-weighted loss 讓 objective mass 按設計分配，但不等於每個 trajectory 對 optimizer 的實際影響完全一樣，也不等同 pooled token loss。

## 9. 正式訓練：一次中止，一次完整完成

### 9.1 第一次

`agentic-v11-trial-job/` 在 step 1 前，主機 available 降到 **9.308 GiB**，guard 中止，returncode -9。

這是資源門檻保護觸發，不是成功訓練。`training-memory-fix-task.txt` 曾提出 allocator 修法，但**沒有實作**，不能把第二次成功歸因於該 patch。

### 9.2 再次授權後重跑

使用者要求 **Start training** 後，以同一套已審查實作再跑；起跑可用主機記憶體約 111.8 GiB。

目錄：`agentic-v11-trial-job-02/`。

| 項目 | 結果 |
|---|---|
| 完成 steps | 257／257 |
| epochs | 1 |
| batch size／rank | 1／4 |
| optimizer／lr | AdamW／5e-5 |
| gradient clip norm | 1 |
| baseline validation | 0.4147183197152723 |
| final validation | 0.2991137429368488 |
| task-weighted train loss | 0.939121379074098 |
| runner 耗時 | 7066.5795 秒 |
| supervisor 耗時 | 約 7072.13 秒 |
| peak allocated／reserved | 27.8796／58.1270 GiB |
| 主機最低 available | 約 51.41 GiB |
| exit | 正常，0 |

checkpoint：step 10、20、……、250 共 25 份 periodic adapter，加 final adapter。

final：`agentic-v11-trial-job-02/train/final-adapter/`。

`train/latest-checkpoint.json` 的 step250／epoch_complete=false 描述最後一次 periodic checkpoint，不是 final 訓練失敗。應同時讀 `train/progress.json` 的 completed257 與 supervisor result。

這些 checkpoint 是 adapter 與 metadata，**不含 optimizer state**，所以不能稱可無縫接續訓練。

訓練器內的「no deployment」字樣描述當次訓練程式不部署；後來另行授權的部署已完成，不可把這個歷史註記當現況。

## 10. 所有 checkpoint 比較：準備完成，但沒有跑成

使用者曾授權比較 base、final、所有每 10-step snapshots，並向 Discord channel `1549461638732582943` 回報。

規劃內容：固定相同 7 列 weighted validation；檢查 40 keys／shape／rank4／alpha8／q-v targets；權重有限且為正；不得殘留上一個 adapter；baseline 比對容許值 atol1e-4＋rtol1e-3，不符就中止。

實作含輸出路徑限制、exclusive claim、symlink protection、子孫程序清理、checkpoint gap／metadata／model identities 檢查。第一次獨立審查列出 8 個 blockers，修正後凍結 36 tests／63 artifact hashes。

但啟動控制器仍失敗：

1. 第一個 controller 約 40 分鐘後因 literal「fix-ready」條件失敗，已誠實通知。
2. 第二次 recovery controller 的最新紀錄為 failed。
3. 根因：凍結的 gates 寫死 `INDEPENDENT-REVIEW.json`，它是必須保留的舊 passed:false 審查；新的通過結果在 `INDEPENDENT-REREVIEW.json`。
4. 綁新報告被拒、綁舊報告也被拒；授權範圍不允許擅自改另一份 review input 或程式碼來繞過。
5. `approval_created=false`、`evaluator_armed=false`、`gpu_evaluation_run=false`。
6. 沒有 `EVAL-APPROVAL.json`、`STARTED.json` 或 output。

第二次失敗通知 message id：`1549870792786051073`。這是行政狀態通知，不是評估成功報告。

**沒有 checkpoint 排名、沒有最佳步數結論，final 也不是已證明勝過所有較早 checkpoint。**

證據：`checkpoint-eval-v1/CONTROLLER-STATUS.json`、`CONTROLLER-ATTEMPT-1.json`、各 tests／review／identity 文件。

## 11. 使用者另行批准後的可回復部署

### 11.1 匯出與核對

- final safetensors 轉為 `deployment-v11/agentic-v11-final-f32.gguf`。
- 40 個 F32 tensors，約 2.05 MB。
- 每個 tensor 的名字、shape、值與 safetensors 完全比對。
- 外掛 alpha/r=8/4=2；llama-server 外部 scale=1，兩者不是相同參數。

### 11.2 部署前相容性測試

- CPU reviewer 針對 commit `50385541344cbb774db6ab9620a40f2a1ee1231d` 做 exact-commit 靜態檢查，conditional PASS，未改 dirty worktree。
- context16384 下，base／adapter 共 14 個 HTTP smoke responses，涵蓋算術、翻譯、急迫建議、gettime、保留 2023、固定時鐘 2032→去年 2031。
- 長醫療回答有 256-token 截斷，後來以三句限制補測；不稱完整醫療事實驗證。
- context520000 配置成功，兩個 concurrent 短 prompt 成功；最低主機 available 87.04 GiB。
- **沒有塞滿 260k tokens 測品質**，也沒有持續 throughput benchmark。
- smoke units 在正式服務重新啟動前停止。

### 11.3 正式改動

唯一新增 systemd override：
`/etc/systemd/system/qwen-mtp.service.d/zzzz-agentic-lora-v11.conf`

改動只有：
1. 加 `--lora /home/chihmin/models/qwen-agentic-lora-v11/agentic-v11-final-f32.gguf`。
2. slot namespace 改為 `/home/chihmin/.cache/llama-slots-agentic-v11/`。

argv 比對證明沒有別的設定變更；舊 unit／drop-ins 已備份。原底模與 binary 保持不變，沒有 merge weights。

部署前原服務已是 stopped／failed，不是本步驟殺掉一個健康服務。經批准以 `sudo systemctl restart qwen-mtp` 啟動。

2026-09-17 04:06 +0800 紀錄：active/running，PID3215817，health OK、adapter path／scale1 正確、算術與 gettime schema 成功。一次短請求 MTP draft18／accepted18，不能視為穩定接受率或長期速度結果。

服務名稱／使用方式不變：Discord 仍選 `local-llama/qwen3.6-35b-q4`。

### 11.4 MTP／FlashHead 的正確解釋

檢查的實作中 LoRA 加在 target，不傳入 draft context。target 保持 dense；draft 可保留 FlashHead。使用同一個優化 binary 不表示兩邊 execution path 完全相同，也不保證掛 LoRA 後速度一樣。

### 11.5 回復原服務的方法（本次沒有執行）

需要且再次授權時，只移除新 override，再經 restart-service 流程 daemon-reload／restart；不可刪其他原有覆寫檔，不可刪 adapter／checkpoint。舊 base namespace 保留。

證據：`deployment-v11/DEPLOYMENT.md`、`TENSOR-EQUIVALENCE.json`、`STATIC-REVIEW.json`、`PRODUCTION-VERIFY.json`、`PRODUCTION-TOOL-MTP.json`、`FULL-CONTEXT-SMOKE.json`、`before/`。

## 12. 部署後才抓到的快取問題與說明更正

### 12.1 真正根因

部署將 server 的 slot-save-path 換成新 LoRA namespace，但**漏同步 Pi client 的 cacheDir**。

- llama.cpp 決定 `.bin` 真正寫入／讀取的目錄。
- Pi 只傳檔名給 save／restore API，不會以 cacheDir 控制 server 路徑。
- Pi 自己在本機用 cacheDir 檢查 metadata 與 bin 是否存在。
- 因目錄不一致，Pi 在送 restore 前就判定 miss，重新 warm。

先前曾把路徑責任說得不精確，經使用者指出後已明確更正：**不是 llama.cpp 在錯目錄找檔，而是 Pi 的本機 eligibility check 提前拒絕。**

### 12.2 修正前 A/B 證據

一般全新 Pi sessions：17.29／17.25 秒，兩次都重新 warm 17,681 tokens。

僅在測試子程序設 `LLAMA_SLOT_SAVE_PATH` 對齊：prime17.36 秒；下個全新 session0.815 秒，另一次0.765 秒；重用17,681 tokens，只算32個新增 tokens。

用 `undici:request:headers` 被動觀察確認 `/slots/0?action=restore` HTTP200。最初 global-fetch observer 沒產出 trace，發生 FileNotFoundError，後改 diagnostics-channel observer 成功；沒有把失敗觀測算成功。

`cacheRead` 本身不是磁碟命中證據：先重新 warm 再沿用同一 session 也會出現 cached tokens，所以同時看 restore API 與 server prefill log。

### 12.3 快取內容與隔離原則

- `.bin`：target state。
- `.bin.dft`：MTP draft sidecar。
- `.meta.json`：本機 snapshot 資訊、prompt/tools hash 等。
- 舊 metadata 缺 model／adapter identity，因此不能把 base-only KV 恢復到 LoRA 權重。
- 舊快照沒有複製進 LoRA namespace。

證據：`golden-cache-test/REPORT.md`、default/aligned sessions 與 trace。

## 13. KV cache manager 的完整修復過程

使用者要求切換設定時能自己找到正確快取，於隔離 worktree 開發：
`kv-cache-fix/worktree/`。

新增能力：
- 對支援的本機 Linux loopback endpoint，確認 listener／PID／ownership／namespace，找出 server 的實際 slot-save-path。
- metadata 隨 server-authoritative 目錄管理。
- 以模型檔案、LoRA 身分與 scale、相關設定、prompt/tools 等建立版本化 namespace。
- 偵測 runtime／設定變更，清掉失效 RAM 管理狀態與舊工作；保留 `.dft` sidecar。
- 無法確認的 remote／proxy／ambiguous server 採安全不重用，不碰錯誤目錄。
- 不信任無綁定身分的 legacy cache。

第一次獨立審查阻擋上線：真實 `http://localhost:8001/v1` 被拒，以及排隊 HTTP 操作可能無期限等待。修正為 validated／DNS-pinned localhost transport、headers/body deadline、lifecycle cancellation。re-review PASS，44/44 tests、typecheck、generated dist 比對通過。

### 測試隔離事故，及處置

初始 RED test 意外覆寫**舊 cacheDir 的 `base_tools.json`**，並新增 fixture `base_system_prompt.meta.json`。沒有動到真實 KV／model binaries。

處置：先保存、checksum 比對；由已知備份復原 tools，只刪除 checksum 完全符合測試 fixture 的新增 metadata。已向使用者說明，不把事故藏掉。之後測試在載入正式模組前隔離 HOME，並阻擋非 fixture 網路。

證據：`kv-cache-fix/INCIDENT-REMEDIATION.json`。

### 真實測試與安裝

- 不改模型 endpoint、不加 `LLAMA_SLOT_SAVE_PATH`，完整正式 Pi extensions／skills 的兩個新程序：prime13.63秒、fresh **1.616秒**。
- fresh 重用 **17,681 tokens**，新增32 input＋3 output；restoreHTTP200，沒有 full `/completion` warm，回答 OK。
- 同一 persistent Pi worker，配獨立 temporary GPU server port18011：A prime → A restore → B prime → B restore → 回A restore；再測同資料夾 LoRA scale1→0.5 cold warm→回1 restore。
- 共7階段通過，3個 golden binaries 都有 `.dft`。
- 所有 owned test servers 清理；production8001 沒被切換，scale保持1。

已安裝到 `/home/chihmin/src/pi-kv-cache-manager`，保留 extension symlink；`before-live-repo.tar` 可回溯原碼。

既有 Pi worker 不會自動載入新程式；閒置時 Discord `/pi model` 重選同模型會關閉該 channel 舊 RPC worker，下一次載入新碼，保留對話。不需要重啟模型 server。

限制：不是任意遠端／container／proxy 都能推導路徑；stat identity 假設載入期間模型檔 immutable，不是完整內容防竄改證明；跨 worker server transaction 競態仍無法全面消除；quota 以 active namespace 為單位。

### Commit 與 push

- commit：`b2dbf9de50f24a9d9b7708b5255751a71b7b75a1`
- message：`[verified] Resolve server-owned KV cache paths and isolate runtime snapshots`
- 55 個 committed changed files 全部對上獨立審查 hashes。
- push 前重跑 44/44 tests、tsc --noEmit、diff check；working tree clean。
- `git push origin main` 成功，`git ls-remote origin refs/heads/main` 與 local HEAD 相同。
- repository：`AyaSakura-comp/pi-kv-cache-manager`。

`kv-cache-fix/DEPLOYMENT.md` 的「not pushed」是較早安裝時點的紀錄；之後已完成 push，以本節和實際 git 結果為準。

## 14. GitHub 備份範圍

LoRA audit 的 private repository：
`https://github.com/AyaSakura-comp/qwen-agentic-lora-audit`

已確認備份：
- commit `18cfe74`。
- archive `snapshots/v11-deployed-final-all-checkpoints.tar.gz`。
- 650 files，72,860,245 bytes。
- remote blob `fb3fd92dfcc9324fd7a19093e678a6cb41a7403b`，local／remote 已核對。
- final HF／GGUF adapter、全部 periodic checkpoints、資料／程式／審查、服務備份及部署證據。
- 未含底模大型權重、虛擬環境、可重新下載的 vendor clones、credentials 或 KV caches。
- secret scan 無命中；約69.48MB archive 超過 GitHub 建議50MB而出現警告，但 push 成功。
- 早期 commit `3c3e1f9`、`88aeb17` 的備份保留。

**這份 LoRA 備份早於快取修復與本文件，不能聲稱本文件／最新 cache-test 證據已在該 archive。** extension 原始碼則已另外 push 到其 repository。

## 15. 圖解與說明的後續整理

使用者要求圖解 QLoRA／LoRA operators，曾依序產生：

- `lora-gguf-explained.html` 及 desktop／mobile PNG。
- `diagrams/qlora-operators.png`：量化、前向、反向和 optimizer 大圖。
- `diagrams/qlora-simple.png`：兩分支的簡單圖。
- `diagrams/gguf-qlora-all-ops.png`：NF4 與 GGUF 區分，Q4_0／Q4_K／Q6_K decode、LoRA forward/backward、AdamW 及實際設定。
- 圖的 SVG／HTML 與繪圖程式一起保留。

其中曾把「隨便畫一畫給我」誤解為「下次簡單畫」，使用者回問後才補上簡圖，已道歉更正。

operator 圖是核心數學／儲存流程，不是所有 Transformer 層或所有 GPU kernel 的實際 trace。GGUF 是容器；不同 tensor quant type 的解碼算子不同。

## 16. 哪些已證明，哪些仍沒證明

| 主張 | 證據狀態 |
|---|---|
| 本機混合 GGUF 可完成有限 LoRA 訓練 | 已完成 pilot 與 v11 |
| v11 小驗證集 loss 下降 | 已證明；只限7列／2相關NASA軌跡 |
| 日期 pilot 的有限生成行為改善 | 已證明；不是獨立全面 benchmark |
| final GGUF adapter 與 safetensors 一致 | 40張量逐值核對 |
| 能掛到既有服務並呼叫工具 | 短 smoke 與 production verification 通過 |
| final 是所有 checkpoint 中最好 | **未證明；比較未啟動** |
| 所有研究案例的答案都正確 | **未證明；42案仍為安全前綴** |
| 真實 live-web 全鏈路普遍改善 | **未證明** |
| 填滿長上下文仍正確 | **未證明；只驗證配置＋短請求** |
| 掛 LoRA 不影響持續速度 | **未證明；没有完整持續benchmark** |
| target 與 MTP draft 都掛同一 LoRA | 不成立於檢查的實作；draft 未傳入LoRA |
| 新 Pi 能恢復正確磁碟快取 | 本機完整session與7階段切換已驗證 |
| 任意遠端／proxy都可自動選快取 | 不宣稱；無法驗證時安全略過 |
| checkpoint 可無縫續訓 | 不宣稱；缺optimizer state |

## 17. 後續若要繼續，依序做什麼

1. 另行批准修改 checkpoint evaluator 的 review-binding，經重新審查後才啟動比較；保留歷史 failed review，不偽改為 pass。
2. 加入獨立、未參與資料修正的行為評估；避免只看同一7列驗證集。
3. 補完整研究案例和真實可追溯工具軌跡，不把 curated reconstruction 當 raw capture。
4. 如需正式品質保證，另測長上下文、真實搜尋／引用正確性、安全案例、多seed與MTP持續速度。
5. 舊 Pi workers 需載入新版extension；remote／proxy支援應另有明確驗證規格。
6. 若要把本文件及最新快取證據放入 private audit backup，另做一次明確範圍的備份，排除測試KV二進位與credentials。

## 18. 核心證據索引

相對路徑全部以 `/home/chihmin/qwen-date-audit/` 為根目錄：

- 初始诊斷：`REPORT.md`
- 工具鏈：`BUILD-DEBUG.md`、`ROCM72-PROGRESS.md`、`TRAINING-PREFLIGHT.md`
- pilot：`DATE-PILOT.md`、`ADAPTER-EVALUATION.md`
- 全100案：`fact-check-full-v1/FULL-REVIEW.md`、`fact-check-full-v1/CROSS-CUTTING-REVIEW.md`
- v11採納：`REPAIR-ACCEPTANCE.md`、`agentic-data-v11-limited-trial/ACCEPTANCE.json`、`TRAINING-APPROVAL.json`（位於同目錄）
- runner：`run_agentic_training.py`、`guarded_agentic_job.py`、`agentic_training.py`
- 訓練授權：`USER-TRAINING-AUTHORIZATION.json`
- 訓練結果：`agentic-v11-trial-job-02/train/progress.json`、`agentic-v11-trial-job-02/supervisor-result.json`
- final：`agentic-v11-trial-job-02/train/final-adapter/`
- checkpoint比較：`checkpoint-eval-v1/CONTROLLER-STATUS.json`
- 部署：`deployment-v11/DEPLOYMENT.md`、`TENSOR-EQUIVALENCE.json`、`PRODUCTION-VERIFY.json`（後兩者位於同部署目錄）
- 快取定位：`golden-cache-test/REPORT.md`
- 快取修復：`kv-cache-fix/DEPLOYMENT.md`、`INDEPENDENT-REREVIEW.json`、`INCIDENT-REMEDIATION.json`（後兩者位於同修復目錄）
- A/B切換：`kv-cache-fix/live-switch/RESULTS.json`
- 備份：`GITHUB-BACKUP.json`
- 本文件：`LORA-TRAINING-END-TO-END-RECORD.zh-TW.md`
- 隨附證據雜湊索引：`LORA-TRAINING-END-TO-END-EVIDENCE.json`

這份紀錄保留「發現問題 → 試驗 → 失敗 → 修正 → 審查 → 訓練 → 有限驗證 → 授權部署 → 發現漏項 → 再修復」的完整脈絡，而不是只留下最後成功結果。
