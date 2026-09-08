# feather-setup 工作地圖

## Notes

- 使用者已核准 8 張票券的粒度與相依關係；已開始依序實作及驗收。
- 規格：[Feather 獨立安裝器](spec.md)。規格維持 ready-for-agent，沒有修改或關閉母規格。
- 各票均為 task；只有全部阻擋票完成後才可開工。
- 驗收以安裝器命令或互動輸入到隔離檔案、設定、輸出及退出結果為主，搭配支援平台上的原生 Codex 載入證據。

## Decisions-so-far

| 票券 | 阻擋票 | 完成後可展示的行為 |
| --- | --- | --- |
| [01：最小可用安裝器](issues/01-project-handoff-installer.md) | 無 | 獨立發行包的專案交接檢查、預覽、安裝及失敗復原 |
| [02：元件選擇](issues/02-component-selection.md) | 01 | 任務分工、交接及整套安裝 |
| [03：使用者範圍](issues/03-user-scope.md) | 01 | 使用者安裝與跨範圍同名偵測 |
| [04：入口宣告](issues/04-optional-entrances.md) | 02、03 | 可選入口、override 指引及混合範圍 |
| [05：更新與衝突](issues/05-update-and-conflicts.md) | 04 | 新版更新、手動修改保留與明確替換 |
| [06：選擇性移除](issues/06-selective-removal.md) | 04 | 安全移除所選元件與入口，保留交接資料 |
| [07：範圍遷移](issues/07-scope-migration.md) | 06 | 專案與使用者範圍間的明確遷移 |
| [08：互動體驗](issues/08-interactive-experience.md) | 05、07 | 完整引導與命令模式的一致結果 |

01–08 全部完成；[08 Answer](issues/08-interactive-experience.md) 記錄最終 Windows／Linux 完整包與來源驗收。完整來源 92 項、兩平台解壓包各 56 項，通過與略過數量分列於驗證紀錄。[雙軸審查](review.md) 修正後均無剩餘發現。

規格驗收條件對應：1 → 01、08；2 → 02、03、04；3 → 04；4 → 04；5 → 02；6 → 03、07；7 → 01、08；8 → 05；9 → 05、06；10 → 01、02、04、05、06、07；11 → 06、07；12 → 01；13 → 01、02、03、04、05、07、08。

## Fog

- 沒有待確認的產品拆分決策。Linux 實測 Ubuntu／WSL2 x86_64、glibc 2.39；其他 Linux 系統與最低支援 Codex 版本尚未驗證，不擴大宣稱相容性。
- 原生探測證明角色註冊、skill 與入口載入，沒有真實模型派工；不宣稱角色模型與 reasoning 已執行。
- 沒有剩餘實作或驗收工作。完整包位於 dist/，附 SHA-256 與使用／復原文件；素材與安裝器來源雜湊保存在 bundle.json。
