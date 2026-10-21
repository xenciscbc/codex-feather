# v1.7.0

新增明確呼叫入口 `$handoff-tidy`，可提出交接整理建議、核對指定記錄，或在說明成本並取得確認後核對全部記錄。寫回須另行確認具體變更；合併先保存並讀回目標，再處理來源。遇到外部版本變動會重新提案，保留舊驗證、人工補充、未決問題及審查限制。

共享 Python handoff 工具從 cc-feather v0.16.0 對齊至 v0.30.0（`03c9c24`），同步 Git 呼叫與復原、promisor remote 的 lazy-fetch 防護，以及一致的 Markdown 標頭邊界。既有交接格式可繼續使用，保留 Codex 的計畫審查紀錄與 Windows ctime 檢查。修正 mypy 型別標註，並補上 PowerShell UTF-8 輸出解碼指引。

驗證：mypy 30 個來源檔通過；handoff 回歸 260 項（18 項條件略過），另加一項 cp950／cp1252 編碼測試；plugin setup 28 項、部署 2 項均通過。原生 executor 與 analyst 的候選 skill 演練涵蓋模式選擇、提案、指定核對、版本衝突、確認寫回與部分保存後的復原歸檔。CLI 自動載入仍受測試環境政策限制，Full check 確認後的全查未列入本輪模型演練；詳見 [工具驗收](handoff-tool-validation.md) 與 [原生演練](handoff-live-validation.md#2026-10-21handoff-tidy-候選-skill-原生演練)。

更新 marketplace 後重新安裝 `codex-feather@codex-feather`，核對已安裝版本並開新 session 載入新版技能。本次發布為 Git marketplace plugin，未重建獨立安裝器執行檔。
