---
name: deep-research
category: research
description: 一套遞迴式資訊獲取流程，結合研究日誌、術語優化與三角論證，用於處理高度複雜、未知度高或需要交叉驗證的深度研究任務。
---

# Deep Research 遞迴研究法 (V2)

## 觸發條件
- 當使用者要求 "deep research", 「深度調查」、「全面分析」或針對一個陌生領域進行「盡職調查 (Due Diligence)」時。
- 當單次 `web_search` 無法提供完整答案，且結果中出現多個需要進一步追蹤的關鍵實體、技術名詞或爭議點時。

## 核心邏輯 (Recursive Loop)
本技能要求 Agent 透過 **研究日誌 (Research Log)** 進行狀態管理，並模擬以下遞迴邏輯：
`Refine(topic) -> Search -> Log(findings) -> Identify Gaps -> Priority Check -> Recursive Dive -> Synthesis`

## 執行步驟

### 1. 初始化研究日誌 (Initialization & Logging)
- **建立 Artifact：** 建立一個名為 `research_log.md` 的檔案，用於記錄：
    - **探索地圖：** 已搜尋的關鍵字、URL 與節點狀態 (Done/Pending)。
    - **核心發現：** 每個節點提取的關鍵事實與來源連結。
- **定義目標 (Goal)：** 明確最終要回答的問題與停止標準 (如：特定數據點已尋獲、或達到 3 層深度且邊際效益遞減)。

### 2. 術語優化與初始掃描 (Query Refinement)
- 使用 `web_search` 獲取主題概況。
- **關鍵步驟：** 從初步結果中提取該領域的「專業術語 (Jargon)」、「縮寫」或「產業標準」。
- **優化指令：** 利用這些術語重新構建搜尋指令 (如使用 `site:.gov`, `site:.edu`, `filetype:pdf` 或特定學術資料庫關鍵字)。

### 3. 缺口識別與三角論證 (Gap Identification & Triangulation)
- 分析目前獲取的內容，標註：
    - **已知 (Known):** 已有明確答案。
    - **衝突 (Contradiction):** 不同來源說說法不一。
    - **未知 (Gap):** 關鍵細節缺失。
- **三角論證要求：** 對於核心事實，必須尋找 **至少 3 個獨立來源**。若來源不足或存在衝突，將其列為高優先級的 `New Search Target`。

### 4. 遞迴下鑽與邊際價值評估 (Recursive Dive)
- 對於每個 `New Search Target`，重複步驟 2 與 3。
- **優先級與剪枝：** 
    - 優先處理對核心目標影響最大的缺口。
    - **邊際價值評估：** 若繼續下鑽僅能獲得極細微細節，應果斷停止該分支 (Pruning)。
- **工具組合：** 
    - 廣度搜尋：`web_search`
    - 深度閱讀：`web_extract` / `read_url_content`
    - 互動式/動態頁面：`browser`

### 5. 結構化綜合合成 (Structured Synthesis)
- 當核心缺口填補完畢或達到限制時，產出最終報告，結構如下：
    1. **執行摘要 (Executive Summary)：** 直擊核心問題的結論。
    2. **詳細分析：** 按主題分類，標註來源 [1][2]。
    3. **三角驗證結果：** 標註哪些部分已獲多方證實，哪些部分來源單一。
    4. **矛盾與未解之謎：** 明確指出網路資訊中缺失或衝突的部分，嚴禁幻覺補完。
    5. **參考文獻 (References)：** 列出所有關鍵 URL。

## 陷阱與防範 (Pitfalls)
- **研究迷路：** 若無 `research_log.md`，極易在大量分頁中迷失。
- **同溫層效應：** 避免只採用同一立場的來源。若主題具爭議性，必須搜索反對觀點。
- **資訊過載：** 僅記錄對達成 `Goal` 有貢獻的資訊，不要做無意義的資料堆疊。

## 驗證步驟
- [ ] 是否建立了 `research_log.md` 紀錄研究路徑？
- [ ] 是否針對關鍵事實進行了至少 3 個來源的交叉驗證？
- [ ] 最終報告是否包含「矛盾與不確定性」的說明？
- [ ] 是否使用了領域專業術語優化過搜尋指令？
