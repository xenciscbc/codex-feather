# 06：整體回歸與原生行為驗收

Type: task
Status: claimed
Blocked by: 05

## Parent

[主規格](../spec.md)；[工作索引](../map.md)。自動回歸、部署與原生試用成果已完成；完整原生事件驗收仍未關閉。

## What to build

按 spec 的 A/B 驗收矩陣跑離線與隔離原生案例，彙整平台與證據限制。

## Ownership

tests/ 必要整合案例；scripts/handoff_trials.py 與分工試用驗收器；新增 docs/resume-reliability-validation.md；本 effort 工作票狀態。實作前核對現況；與其它票共享的模組依依賴順序由前一 owner 完成後接手。保留現有未提交修改。所有行為契約以主規格為準。

## Acceptance criteria

- [x] 舊交接全流程、基準保存／比對、歸檔封存與失敗重試回歸通過。
- [x] Windows／Linux 部署與來源邊界案例記錄實測或明確未驗證。
- [ ] 原生案例涵蓋過期驗證、普通 read、partial 結果、假 completed、阻塞接手及停止後移交。
- [ ] 核對原生事件與來源基準，不以手填結果或模板冒充行為證據。
- [ ] 必要測試通過且所有未驗證項可見，才記錄相應完成狀態；未通過不標整体驗收完成。

## Completion

提供修改檔案、適當測試結果與限制，再依 issue tracker 規則補 Answer、更新狀態及 map。原生測試依既有明確啟用流程執行；不能以離線驗收代替原生結果。

## Comments

2026-09-12：Windows 全套 190 tests OK（3 skipped），後新增的 payload 測試及完整部署共 2 項通過；Linux 交接 94 tests OK（3 skipped），部署 2 項通過。五個原生隔離 trial 的成果及寫入範圍驗證通過。審查所見程式問題已修復。

完整原生事件尚未持久保存，不能由 answer.md 與產物值獨立證明拒收、兩次重試及 writer 停止時序；本票保持 claimed，不能標為整版原生驗收完成。後續需明確啟用的 smoke run 留存原生事件並逐條核對。詳見 [驗證與修正紀錄](../../../docs/resume-reliability-validation.md)。


