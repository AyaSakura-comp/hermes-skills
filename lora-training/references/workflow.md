# 階段流程、授權與驗收 gates

## 0. 先建立工作空間與狀態表

建立新 run directory，不覆蓋原工作。從 `../assets/RUN-RECORD.template.md` 複製紀錄模板。讀取現有 source、manifest、review、supervisor result，而非只讀 latest receipt。

狀態只能是 planned / authorized / running / passed / failed / blocked / not-run。每個 gate 必須有證據路徑與版本。說「請訓練」不等於授權停止 production、部署新權重、公開資料或略過安全門檻。

## Gate 1 — 根因與衡量方式

輸入：使用者目標、可重現失敗例、預期行為。

檢查：
- 保存 sanitized 原 request，包括 system、messages、tools、template、seed、解碼參數。
- 對照 fresh context／舊 context、時鐘位置、tools、cache；一次只變一個因素。
- 明確區分時鐘是否取得、日期計算是否正確、query 是否選對年份、search 是否真的執行、引用是否支持結論。
- 在訓練前定義 failure taxonomy 和獨立 heldout，避免看到結果後重新定義成功。

通過：至少能界定想訓練的行為，不把基礎设施 bug 當資料問題。

## Gate 2 — 模型與工具鏈身分

固定：底模實際檔案、SHA256、HF revision（若有）、GGUF architecture／quant types、tokenizer／config／chat template hashes、adapter targets、framework revisions、compiler／ROCm runtime、kernel paths。

GGUF 來自混合 patch 時，不能只記上游模型名。HF config 同架構不表示權重等價。若 hash 是開跑後才算，紀錄捕捉時點，不回溯聲稱是 launch proof。

保存 relevant git diff；不重設髒工作樹。不擅自升級共享環境。

## Gate 3 — 資料與審查

參照 `data-and-evaluation.md`。

必要測試：唯一 IDs、trajectory split、heldout 隔離、來源 status、日期区間文法及時區、assistant-only masks、chat-template/tokenizer roundtrip、tool-call JSON、max length、不截斷、objective weights 有限且正值。

獨立 reviewer 可阻擋；修正由另一 context 執行，重新審查。保留 failed report，不把其內容改成 pass。

## Gate 4 — GPU preflight

先核對資源與新授權。用與正式訓練相同 code、資料編碼、quant path 與目標長度跑代表性 updates。

核對：
- loss/grad finite；所有預期可訓練張量有合理更新；frozen tensors 不進 optimizer。
- 真實 allocated／reserved、主機 available、swap total、時間上限。
- supervisor 只擁有自己建立的 scope/process group；終止後檢查 descendants 已結束。
- 不能以單 token 前向通過替代 1536-token backward 的資源證據。

## Gate 5 — 正式有限訓練

批准綁定：code、dataset、evidence、reviews、preflight、model identities、hyperparameters。

runner 成功條件：child 正常 exit + 最終狀態 completed + steps符合 + final adapter存在。單看log的最後一句或latest periodic snapshot不足。

每10步 atomic save是歷史profile；新工作可由使用者與計畫決定間距。永不默認prune。記錄是否包含optimizer/RNG/scheduler；只有adapter時只稱snapshot。

監督程序若因記憶體或timeout終止，不能自動放寬門檻、增加swap或修改allocator後偷偷重跑。先報告根因與新提案。

## Gate 6 — checkpoint / behavioral evaluation

固定評估器與評分法、所有候選身份、輸出路徑與准入條件。建立exclusive execution claim，拒絕symlink逃逸，防重複worker覆寫。

先復現base loss；偏差超過已審查容許值則停。比較adapter前確認40 tensors之類的數量是此模型預期，不用歷史數字套新模型。

沒有跑完整比較，只能說某版已測／已選，不能說best。

## Gate 7 — 匯出、部署與回復

另外確認部署與服務停機範圍，讀restart-service hub。離線轉檔 → tensor equivalence → temporary server smoke → context allocation → 另行批准正式變更。

單獨可移除的drop-in、不變的底模、獨立KV namespace、原設定備份，是此案例的可回復設計。其它平台選同等可回復方法，不盲貼systemd指令。

## Gate 8 — 交付與備份

輸出結果、適用範圍、未完成項目、rollback計畫、artifact manifest。上傳需要明確目標與隱私範圍。完整保存過程不等於把所有cache和聊天公開上傳。

## 需要停止的情況

- 底模或資料身份不明且無法證明測試適用性。
- review／approval hashes 不符，或指向歷史failed review。
- 來源不可用但目標答案假裝已查證。
- host memory/swap/time gate失敗。
- baseline無法復現、adapter跨版本殘留、mask空白或silent truncation。
- 非本人工作占用服務／GPU，需要超出授權的操作才能繼續。
- 想用舊cache或覆寫原底模來省時間。
