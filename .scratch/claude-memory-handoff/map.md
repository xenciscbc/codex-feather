# Claude memory 外部交接記錄工作票地圖

## Notes

- 母規格：[spec](spec.md)。工作進度以各票狀態與 Answer 為準。
- 每張票包含使用者可見行為、使用說明與隔離驗收；標記 ready-for-agent 不代表前置票已完成。
- [01 指定 memory 目錄查找](issues/01-read-memory-directory.md)、[02 專案路徑定位](issues/02-locate-project-memory.md) 與 [03 同專案交接連結](issues/03-follow-project-handoff-links.md) 均已完成。
- 02 與 03 沒有功能上的互相依賴；若修改同一技能或驗收工具，需協調寫入所有權或依序實作，不因依賴圖可分支就同時改寫共享檔案。

## Decisions-so-far

- 使用者已確認 3 張票的粒度及依賴：01 無前置；02、03 皆只依賴 01。
- 沿用既有技能與隔離試用入口，未識別出需要獨立前置重構票的工作。
- 01 已完成直接讀取、語意分類與來源回報；5 項新增核對器測試、23 項既有 handoff 測試與 4 個隔離原生情境通過。詳見 [01 Answer](issues/01-read-memory-directory.md#answer) 與驗收文件。
- 02 已完成定位、自訂設定、Git worktree／非 Git 與歧義選擇；累計 11 項 memory 測試，自訂位置、worktree、非 Git、等待選擇及選定後閱讀均有原生操作證據。詳見 [02 Answer](issues/02-locate-project-memory.md#answer)。
- 03 已完成同專案明確連結、未知關聯與 junction 越界控制；4 項連結測試及實際讀取失敗、專案定位整合的原生驗收完成。詳見 [03 Answer](issues/03-follow-project-handoff-links.md#answer)。

## Fog

- 適用官方定位規則已核對並記錄；啟動命名與無效設定只有離線素材／核對器覆蓋，未宣稱原生行為通過。
- Windows 實際 junction 與 FileShare.None 讀取失敗已驗證；不同平台及任意自然語言的完整分類仍不能由這些合成案例保證。
