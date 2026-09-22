# 04：子任務回傳與有界收回

Type: task
Status: resolved
Blocked by: 無

## Parent

[主規格](../spec.md)；[工作索引](../map.md)。實作結果見下方 Answer。

## What to build

依 spec B 更新短回傳約定、主 Agent 驗收與收回程序，擴充對應試用情境。

## Ownership

templates/AGENTS.md；四角色 templates/*.toml；scripts/scenarios.py；tests/fixtures 的新增分工情境；tests/test_trial.py。實作前核對現況；與其它票共享的模組依依賴順序由前一 owner 完成後接手。保留現有未提交修改。所有行為契約以主規格為準。

## Acceptance criteria

- [x] 四角色與通用子任務均有 outcome、證據、變更、驗證、阻礙資訊，允許簡短合併。
- [x] completed 不直接等於整體驗收完成。
- [x] 同原因第二次失敗會收回，轉交保留已知結果。
- [x] 部分修改與寫入所有權移交、停止確認有可核對情境。
- [x] 既有模型逐欄解析、單層派工、來源保護與使用者偏好維持。
- [x] 小任務不新增強制檔案或多餘流程；離線驗收與原生行為分開。

## Completion

提供修改檔案、適當測試結果與限制，再依 issue tracker 規則補 Answer、更新狀態及 map。原生測試依既有明確啟用流程執行；不能以離線驗收代替原生結果。



## Answer

executor 已完成 templates 與兩個分工情境，主 Agent 審查後另補真正成果驗證與負向案例。test_trial 19項全過；原生行为由06驗收。scripts/trial.py 所有權已交回主 Agent。模型請求 gpt-5.6-sol/medium 被接受，實際逐回應模型未確認。

