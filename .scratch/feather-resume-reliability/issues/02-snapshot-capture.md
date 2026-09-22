# 02：唯讀擷取與基準保存

Type: task
Status: resolved
Blocked by: 01

## Parent

[主規格](../spec.md)；[工作索引](../map.md)。實作結果見下方 Answer。

## What to build

依 spec A 實作 snapshot、穩定性與讀取上限，讓 create/update 透過既有版本檢查保存基準。

## Ownership

新 snapshot 擷取模組；writing.py；cli.py 的 snapshot/create/update 接線；對應測試。實作前核對現況；與其它票共享的模組依依賴順序由前一 owner 完成後接手。保留現有未提交修改。所有行為契約以主規格為準。

## Acceptance criteria

- [x] 路徑及 Git 邊界、未知／缺失、非 Git、讀取競態與上限符合 spec。
- [x] 唯讀擷取不修改來源、交接及 Git metadata。
- [x] 保存前驗證已觀察狀態；變動則拒絕，不自動刷新。
- [x] 更新進度保留舊基準；partial 可以保存但不宣稱完整。
- [x] 完成歸檔與重試保留完整基準及完成身份。

## Completion

提供修改檔案、適當測試結果與限制，再依 issue tracker 規則補 Answer、更新狀態及 map。原生測試依既有明確啟用流程執行；不能以離線驗收代替原生結果。



## Answer

已實作 observations.py 擷取、讀取上限、穩定性、Git 狀態與 writing.py 基準保存；18 項新行為測試通過（Windows symlink 1 項跳過），另已通過既有交接回歸。保存失敗、版本衝突與 tracking partial 均有案例。

