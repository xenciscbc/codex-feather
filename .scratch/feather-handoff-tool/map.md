# Feather 交接工具票據導覽

## Notes

- [完整規格](spec.md) 維持 ready-for-agent；本次只發布已核准的八張票據，不修改或關閉原規格。
- 每票為可獨立展示及驗收的完整操作，包含工具、指引與測試。沒有另外拆出跨功能的純文件或純測試票。
- 開始前將票據標記 claimed；完成後附 Answer、標記 resolved，並在本圖 Decisions-so-far 補上結果與票據連結。
- 依編號選第一張未解決、未被認領且所有 blockers 已 resolved 的票據。八張票據均已 resolved；驗收限制見工具驗收記錄。
- 依賴允許的並行不代表可以重疊改共用檔案；實作時仍需指定所有權並協調共用介面。

| 票據 | Blocked by | 目前狀態 |
| --- | --- | --- |
| [01 安裝工具並列出交接清單](issues/01-install-and-list.md) | 無 | resolved |
| [02 查閱舊交接與處理不完整清單](issues/02-legacy-and-partial-reads.md) | 01 | resolved |
| [03 建立含簡短摘要的交接](issues/03-create-summary-handoff.md) | 01 | resolved |
| [04 更新交接並保留人工內容](issues/04-update-with-version-check.md) | 02、03 | resolved |
| [05 完成歸檔與失敗重試](issues/05-archive-and-retry.md) | 04 | resolved |
| [06 查詢共同歷史與封存紀錄](issues/06-query-history.md) | 02 | resolved |
| [07 清除指定歷史](issues/07-clear-selected-history.md) | 04、06 | resolved |
| [08 封存歷史與恢復中斷操作](issues/08-seal-history-and-recover.md) | 05、06 | resolved |

## Decisions-so-far

- [04](issues/04-update-with-version-check.md)、[05](issues/05-archive-and-retry.md)、[06](issues/06-query-history.md)、[07](issues/07-clear-selected-history.md)、[08](issues/08-seal-history-and-recover.md) 已完成版本保護、生命週期操作與指引；[整體驗收](../../docs/handoff-tool-validation.md) 區分 Windows、WSL、原生 Agent 與未確認證據。


- [03](issues/03-create-summary-handoff.md) 已完成建立到列出的操作與 Git 追蹤選擇，公開工具 6 項測試通過。

- [02](issues/02-legacy-and-partial-reads.md) 已完成舊格式、部分結果與長摘要呈現，公開工具測試及型別檢查通過。

- [01](issues/01-install-and-list.md) 已完成公開讀取與安裝環境診斷；Windows 8 項針對性測試通過，原生／Linux 證據待整體驗收。

- 使用者已核准這八張票據的拆分與依賴關係。
- 第一版由 Python 即時掃描交接，沒有持久索引；進度為簡短摘要，詳細紀錄按需保留。
- 受管理讀寫逐項接入同一工具，保留人工編輯、單一寫入者協調與內容版本檢查，不加入鎖定。
- 八項操作均已交付，所有受管理寫入使用同一 Python 工具；規格維持原發布狀態。

## Fog

- 沒有阻擋開工的產品決策；命令名稱、模組拆分與版本依據編碼由實作按規格決定。
- Windows／Linux 可執行的驗收範圍及實際 Agent 證據，在各票執行時核對並如實記錄。
