# feather-handoff 工作索引

## Notes

- 來源為 [交接規格](spec.md)，使用者已核准四張垂直切片票及其依賴關係。
- 已開始依序實作；父規格不修改，票據依实际交付與驗收更新。
- 每張票均包含對應使用說明與隔離外部行為驗收，不另拆純測試或純文件票。沿用既有試用入口，沒有需要先獨立交付的廣泛重構。
- 真實模型測試仍需明確啟用；檔案驗證與原生行為證據分開記錄。

## Decisions-so-far

| 票 | 交付 | Blocked by |
| --- | --- | --- |
| [01](issues/01-create-update-handoff.md) | 建立與更新交接檔 | 無 |
| [02](issues/02-read-resume-handoff.md) | 新 session 讀取與接續工作 | 01 |
| [03](issues/03-archive-completed-work.md) | 完成工作歸入共同歷史 | 01 |
| [04](issues/04-read-clear-history.md) | 按要求查閱與清除交接歷史 | 03 |

- [01](issues/01-create-update-handoff.md) 已 resolved：建立、更新、Git 選擇及隔離驗收已交付；六項離線測試與獨立 Agent 行為試用通過。
- [02](issues/02-read-resume-handoff.md) 已 resolved：讀取、選擇與接續通過離線及獨立 Agent 驗收，包含全新 Agent 接續先前 Agent 留下的紀錄。
- [03](issues/03-archive-completed-work.md) 已 resolved：完成歸檔、同名歷史與重試通過驗收，故障注入確認失敗保留可恢復資料。
- [04](issues/04-read-clear-history.md) 已 resolved：查閱、部分與全部清除、歧義及失敗保留均通過離線與獨立 Agent 驗收。
- 四票已完成，目前沒有可認領的未完成票。兩路審查的 P3 首次歸檔覆蓋缺口已補測；最終工作區 36 項、獨立提交版本 31 項測試通過。詳細結果見專案交接驗收與審查文件。
- 實際取票依專案規則選第一張編號最小、未完成、未被阻擋且未被認領的票；認領與完成時再更新狀態。
- 02 與 03 共用檔案的修改協調屬實作安排，不代表額外功能依賴，也不代表已授權平行派工。
- 交接歷史採一份共用紀錄；feather-setup 與專案入口插入不在本輪。
- 使用者故事覆蓋：01 負責 01–14、29–33；02 負責 01、03、15–21、25；03 負責 22–24、27、29；04 負責 26–29。33 項均有承接票。

## Fog

- 沒有尚待使用者決定的拆票或依賴問題。
- 候選 skill 已由獨立 Agent 實際讀取與執行，跨 session 由無對話繼承的新 Agent 接續另一 Agent 的交接檔驗證。原生 CLI 自動發現／登入式 smoke 與使用者個人目錄安裝未執行，這些通道不宣稱已通過。
