---
name: deep-research
category: research
description: 一套遞迴式資訊獲取流程，用於處理高度複雜、未知度高或需要交叉驗證的深度研究任務。
---

# Deep Research 遞迴研究法

## 觸發條件
- 當使用者要求 "deep research", 「深度調查」、「全面分析」或針對一個陌生領域進行「盡職調查 (Due Diligence)」時。
- 當單次 `web_search` 無法提供完整答案，且結果中出現多個需要進一步追蹤的關鍵實體、技術名詞或爭議點時。

## 核心邏輯 (Recursive Loop)
本技能要求 Agent 模擬以下遞迴邏輯：
`search(topic, knowledge_graph)` $\rightarrow$ `if topic in knowledge_graph: return` $\rightarrow$ `fetch_data(topic)` $\rightarrow$ `identify_gaps(data)` $\rightarrow$ `for gap in gaps: search(gap, knowledge_graph)`

## 執行步驟

### 1. 初始化知識圖譜 (Initialization)
- 建立一個暫時性的 `knowledge_graph` (可用 TODO list 或 內部筆記紀錄)，記錄已探索的關鍵字，防止重複搜尋。
- 定義最終目標 (Goal) 與成功的判定標準 (Stopping Condition)。

### 2. 初始掃描 (Surface Scan)
- 使用 `web_search` 獲取主題的概況。
- 使用 `web_extract` 閱讀高權威性的 index 頁面（如 Wikipedia, 官方文件, 專業論壇）。

### 3. 缺口識別 (Gap Identification)
- 分析目前獲取的內容，將資訊分為：
    - **已知 (Known):** 已有明確答案。
    - **未知/模糊 (Gap):** 出現了新名詞、引用了未讀的文獻、或不同來源之間存在矛盾。
- **關鍵：** 如果對內容中的某個概念「沒有頭緒 (don't have idea)」，必須將其標記為 `New Search Target`。

### 4. 遞迴下鑽 (Recursive Dive)
- 對於每一個 `New Search Target`，重複步驟 2 與 3：
    - **優先級：** 優先處理對核心目標影響最大的缺口。
    - **工具切換：** 
        - 概論 $\rightarrow$ `web_search`
        - 詳細內容 $\rightarrow$ `web_extract`
        - 動態內容/複雜交互 $\rightarrow$ `browser` (模擬操作或深入挖掘)

### 5. 綜合合成 (Synthesis)
- 當所有核心缺口被填滿，或達到遞迴深度上限（建議 3 層）時，停止搜尋。
- 將所有碎片化資訊重新組織，對比不同來源的衝突點，產出最終報告。

## 陷阱與防範 (Pitfalls)
- **無限迴圈：** 嚴禁在兩個互相引用但無實質內容的頁面之間跳轉。若連續兩次遞迴未獲得新資訊，強制終止該分支。
- **資訊過載：** 不要嘗試記錄所有細節，僅記錄對達成 `Goal` 有貢獻的資訊。
- **幻覺補完：** 當遞迴結束仍有缺口時，必須在報告中明確標註「該部分資訊在公開網路中缺失」，不可自行腦補。

## 驗證步驟
- [ ] 是否建立了已搜尋清單以避免重複？
- [ ] 是否針對內容中的「未知名詞」進行了二次追蹤？
- [ ] 最終結果是否由多個遞迴路徑的資訊合成而成，而非單一頁面摘要？
