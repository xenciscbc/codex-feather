# 05：skill 流程、使用文件與部署整合

Type: task
Status: resolved
Blocked by: 03, 04

## Parent

[主規格](../spec.md)；[工作索引](../map.md)。實作結果見下方 Answer。

## What to build

接上接續比對與保存流程，確認新模組隨完整 skill 發布，讓使用者維持自然語言操作。

## Ownership

skills/feather-handoff/SKILL.md；references/tool.md 與必要新參考文件；docs/handoff.md、docs/development.md；setup bundle 相關程式及測試，僅確有需要時修改。實作前核對現況；與其它票共享的模組依依賴順序由前一 owner 完成後接手。保留現有未提交修改。所有行為契約以主規格為準。

## Acceptance criteria

- [x] 普通 read/list 不觸發執行；resume 差異由 Agent 解讀。
- [x] 文件清楚區分檔案基準與測試證據，含舊格式和部分結果處理。
- [x] 安裝／更新／check 包含新 helper，移除保留交接資料。
- [x] 發行完整性以實際 bundle 測試，避免硬編碼檔案表漏新模組。
- [x] 按 writing-for-agents 整理條件式參考，核心限制仍可見。

## Completion

提供修改檔案、適當測試結果與限制，再依 issue tracker 規則補 Answer、更新狀態及 map。原生測試依既有明確啟用流程執行；不能以離線驗收代替原生結果。



## Answer

已接上 SKILL.md、tool.md、snapshots.md、handoff.md 與 development.md。新增實際 bundle 安裝／更新／check／移除整合測試，Windows 與 Ubuntu WSL 均通過，移除保留交接。既有 build_setup 整目錄打包已包含新 helper，無須改 installer 正常流程。WSL 須明確用 /home/cbc/.local/bin/codex（0.153.4），PATH 中的 Windows shim 不可用。

