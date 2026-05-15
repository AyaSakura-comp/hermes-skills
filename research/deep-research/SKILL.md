---
name: deep-research
category: research
description: 一套遞迴式資訊獲取流程，結合內建 todo 工具、研究日誌與三角論證，處理高度複雜研究任務。
---

# Deep Research 遞迴研究法 (V2.4 - Integrated FC Workflow)

## 觸發條件
- 當使用者要求 "deep research", 「深度調查」或「盡職調查 (Due Diligence)」時。
- 當單次搜尋無法完整回答，且結果中出現多個需要進一步追蹤的關鍵點時。

## 核心邏輯 (Recursive Loop)
本技能要求 Agent 使用內建 **`todo` 工具** 進行動態任務管理，並遵循以下核心原則：
- **二次研究迴圈 (Secondary Research Loop)：** 當第一份研究報告產出後，將該報告視為新輸入，針對新發現的實體或未釐清細節啟動第二輪 `deep-research` 流程。
- **遞迴流程：** `Refine -> Todo(Plan) -> /fc (Search & Scrape) -> Log(Findings) -> Todo(Update Gaps & New Branches) -> Recursive Dive -> Synthesis`

## 關於 /fc 工作流 (Understanding the /fc Process)
`/fc` 是本技能的核心數據獲取引擎，其目標是將「淺層的搜尋結果」轉化為「深層的結構化知識」。其操作邏輯如下：
- **Search (搜尋)**：利用 `web_search` 定位最相關的頂層網頁（最高 5 個）。
- **Scrape (抓取)**：不只讀取搜尋摘要，而是透過 Firecrawl SDK/CLI 將整個頁面轉化為乾淨的 Markdown 格式，保留所有細節。
- **Fallback (備援)**：當目標網站（如 X/Twitter）封鎖自動化抓取時，自動切換至 `browser` 模式，透過截圖分析或 DOM 提取來獲取資訊。
- **Combine (整合)**：將多個來源的深度內容彙整，形成一個完整的資訊快照，供後續分析與三角論證使用。

## 執行步驟

### 1. 初始化任務與知識庫 (Initialization)
- **內建 Todo 管理：** 立即調用 `todo` 工具將目標拆解為任務清單。
- **建立 Artifact：** 建立 `research_log.md` 作為長期知識庫，記錄事實、數據與來源 URL。

### 2. 術語優化與深度掃描 (Integrated /fc Workflow)
- **執行深度抓取 (/fc 邏輯)：** 不要僅僅執行單次 `web_search`。針對每個研究分支，執行以下流程：
    1. **搜尋 (Search)：** 使用 `web_search` 獲取頂級結果（最高 5 個）。
    2. **深度抓取 (Scrape)：** 對每個 URL 使用 Firecrawl SDK 或 CLI (`npx -y firecrawl@latest scrape \"<url>\"`) 獲取完整 Markdown 內容。
    3. **備援接管 (Fallback)：** 若 Firecrawl 遇到 `InternalServerError` 或 403，切換至 `browser_navigate` $\to$ `browser_snapshot` / `browser_vision` 模式手動提取。
    4. **整合 (Combine)：** 將所有內容按 `## Source: <url>` 格式整合。
- **術語提取：** 從深度內容中提取「專業術語 (Jargon)」或「產業代碼」。
- **優化指令：** 更新 `todo` 任務，利用提取術語重新構建精確搜尋指令。

### 3. 缺口識別與三角論證 (Gap Identification & Triangulation)
- 分析內容並在 `research_log.md` 標註 **已知 (Known)** 與 **衝突 (Contradiction)**。
- **三角論證：** 核心事實必須尋找 **至少 3 個獨立來源**。
- **產地驗證：** 區分「品牌國籍 (Brand Origin)」與「實際產地 (Country of Origin)」，優先搜索供應鏈報告。
- **動態更新 Todo：** 發現新缺口或衝突時立即新增「驗證」或「下鑽」任務。

### 4. 遞迴下鑽與邊際價值評估 (Recursive Dive)
- **自主執行：** 每步完成後立即啟動下一輪 `/fc` 流程 $\to$ Log $\to$ Update Todo，無需等待指令。
- **並行加速：** 調用 `delegate_task` 開啟子代理並行執行獨立項目，結果整合至 `research_log.md`。
- **邊際價值評估：** 貢獻極低的挖掘分支應標註為已完成或取消 (Pruning)。

### 5. 結構化綜合合成 (Structured Synthesis)
- 核心任務完成後產出極其詳盡的報告：
  1. **執行摘要 (Executive Summary)**
  2. **詳盡分析 (Exhaustive Analysis)**：包含具體數據、邏輯推演。**強制要求：**
     - **文中直接嵌入完整 URL**：每個結論或數據點後必須附上對應的完整 URL，格式如 `[來源名稱](https://full-https-url-here)`，不可僅用編號、簡略名稱或自訂參考 ID 代替。
     - **URL 必須完整可點擊**：不可省略域名、路徑或查詢參數，確保讀者可以直接複製貼上開啟。
     - **每個引用段落下都要有 URL**：不要只在段落末尾給一個總 URL，每個有引用的句子或數據點都應獨立附上 URL。
  3. **三角驗證結果**：說明高度確信與單一來源之結論。
  4. **矛盾、缺口與未解之謎**
  5. **完整詳細的參考文獻列表 (References)**：
     - **必須列出所有使用過（含搜尋結果中獲得但未在正文引用）的 URL。**
     - 格式：`[編號] 來源名稱 — https://full-https-url-here (獲取日期：YYYY-MM-DD)`
     - **不得省略任何一個曾獲取內容的 URL。**

### 6. 提取失敗之備援方案 (Extraction Failure Recovery)
- **診斷模式**: 失敗時使用 `terminal` 執行 `curl -ILs` 檢查 HTTP 狀態碼。
- **瀏覽器接管**: 針對 403 或動態頁面使用 `browser_navigate` 與 `browser_console` / `browser_snapshot`。

## 7. 陷阱與防範 (Pitfalls)
- **同溫層效應**：必須搜索反對觀點。
- **資訊過載**：聚焦於對目標有貢獻的深度資訊。
- **忽視內建工具**：保持 `todo` 與進度同步。
- **日期敏感性**：明確指定 Fiscal Quarter/Year 避免週期錯誤。

## 驗證步驟
- [ ] 是否已調用內建 `todo` 工具管理搜尋路徑？
- [ ] 是否在每個研究分支使用了 /fc 的「搜尋 → 深度抓取 → 整合」完整流程？
- [ ] `research_log.md` 是否完整記錄了事實與來源？
- [ ] 是否針對關鍵事實進行了至少 3 個來源的交叉驗證？
- [ ] **最終報告中的每個結論/數據點是否都嵌入了完整可點擊的 URL？（不可省略域名或查詢參數）**
- [ ] **參考文獻列表是否包含所有使用過的 URL（含搜尋結果中獲得的），且格式為 `[編號] 來源名 — https://full-url (日期)`？**
- [ ] 報告是否包含「矛盾與不確定性」的詳細說明？
