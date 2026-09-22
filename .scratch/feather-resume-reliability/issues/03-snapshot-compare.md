# 03：接續唯讀比對

Type: task
Status: resolved
Blocked by: 02

## Parent

[主規格](../spec.md)；[工作索引](../map.md)。實作結果見下方 Answer。

## What to build

依 spec A 實作 compare --work，分別回報來源差異、Git 差異與操作失敗。

## Ownership

snapshot 比對模組；cli.py 的 compare 接線；對應測試。實作前核對現況；與其它票共享的模組依依賴順序由前一 owner 完成後接手。保留現有未提交修改。所有行為契約以主規格為準。

## Acceptance criteria

- [x] unchanged/changed/created/missing/unknown 前後狀態矩陣完整。
- [x] 舊檔 absent、壞格式 invalid、部分失敗及退出碼符合 spec。
- [x] Git unavailable 仍提供檔案結果，same HEAD 不掩蓋未提交變動。
- [x] 交接版本在讀取間變動時回報 partial。
- [x] compare 不刷新基準，不執行測試或交接下一步。

## Completion

提供修改檔案、適當測試結果與限制，再依 issue tracker 規則補 Answer、更新狀態及 map。原生測試依既有明確啟用流程執行；不能以離線驗收代替原生結果。



## Answer

compare 已提供完整狀態矩陣、Git 獨立觀察、缺基準與格式錯誤分流及交接版本再核對。新增行為測試 Windows 18 項通過（1 skip），Ubuntu WSL 18 項全部通過；原生 Agent 行為由票06驗收。

