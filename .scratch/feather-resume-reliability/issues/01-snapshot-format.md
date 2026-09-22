# 01：基準格式與相容解析

Type: task
Status: resolved
Blocked by: 無

## Parent

[主規格](../spec.md)；[工作索引](../map.md)。實作結果見下方 Answer。

## What to build

依 spec 的 A「資料與相容性」定義 v1，增加選填區段解析與 list 的摘要狀態。

## Ownership

skills/feather-handoff/scripts/feather_handoff/records.py；新 snapshot 格式模組；相關格式測試。實作前核對現況；與其它票共享的模組依依賴順序由前一 owner 完成後接手。保留現有未提交修改。所有行為契約以主規格為準。

## Acceptance criteria

- [x] 舊檔完整可讀，不強制轉換。
- [x] 壞 JSON、未知版本、重複區段、重複路徑及不合法摘要都有明確結果。
- [x] 格式 API 可供 create/update/read/compare 共用，不另建儲存。
- [x] BOM、LF/CRLF、人工段落及 details 邊界有回歸案例。

## Completion

提供修改檔案、適當測試結果與限制，再依 issue tracker 規則補 Answer、更新狀態及 map。原生測試依既有明確啟用流程執行；不能以離線驗收代替原生結果。



## Answer

已加入 baseline.py 格式、路徑驗證與 fenced Markdown 解析，records.py 提供 snapshot_state；4 項格式測試通過。擷取與寫入接線由後續票實作。

