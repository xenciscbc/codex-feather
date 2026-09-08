# 最終安裝包跨專案、新 session 實測

2026-09-08，依使用者要求，在另一個已保存的 Codex 專案 `D:/work_data/project/other/test_gpt`，使用最終 Windows x64 完整包安裝 handoff 元件與專案入口，然後建立四個全新的 Codex app session。各 session 使用相同測試專案磁碟，但沒有 fork 或傳入前一輪對話，也沒有派子代理。背景由實際交接與來源取得。

## 安裝與測試素材

- 發行包：`feather-setup-0.1.0-windows-x64.zip`，SHA-256 `7221e4ef891f1d8ff95d2fe83319e5a906f96d16aeb3253067fb4f64c13e8a24`。
- 核對校驗碼後重新解壓，直接執行內附 `feather-setup.exe install --components handoff --scope project --entrance project`；未指定替代素材包。
- skill 部署至測試專案 `.agents/skills/feather-handoff/SKILL.md`；入口追加到原有 `AGENTS.md`。新 session 實際讀取此安裝路徑的 skill 並操作，不以載入探測請求取代真實工作。
- 原生 Codex 版本 `0.153.4`。沿用 app 的模型與 reasoning 預設，本次沒有驗證模型綁定。測試專案不是 Git repository，未將 Git 忽略行為列為本輪驗收。
- 新素材 `round6_handoff/service.json`：name `handoff-demo`、port `8427`、readiness `/ready-v6`、timeout_seconds `19`。

## 四個 session 的結果

| 新 session | 實際結果 |
| --- | --- |
| `01a07fff-8059-7783-97d7-67bc991287f0`：建立進度 | 載入安裝的 skill，核對名稱與 port，建立 `round6-service-audit.md`，將 readiness、timeout 與報告留給下一輪；另建立等待監控頻率的受阻交接 `round6-follow-up.md`。未提前建立報告或歷史。 |
| `01a08001-2f96-7562-a458-795b88e9a083`：接續 | 只給工作名稱與接續要求，從磁碟取得背景。測試協調者在兩輪間把素材 port 改為 `8428`，未把新值傳給此 session；它自行讀來源發現舊值過時，核對其餘配置並寫出 `round6_handoff/RESULT.md`。 |
| 同一接續 session：完成歸檔 | 保存完成版交接，以 `2026-09-08T15:53:57+08:00` 歸檔到首次建立的 `history.md`；工具紀錄顯示完整讀回歷史、再次核對原交接，再移除原工作檔。受阻工作與來源雜湊不變。 |
| `01a08003-3abb-7912-ace1-56344845a725`：查閱 | 回報完成時間、`8428`、readiness、timeout 與尚未執行的服務測試；另讀取受阻交接，沒有執行下一步。整個測試專案 169 個檔案的前後 SHA-256 完全一致。 |
| `01a08004-456f-74e0-b84f-27b611d79736`：指定清除 | 明確指定工作及完成時間，只移除該筆測試歷史，讀回確認留下歷史標題。全專案比對只有 `history.md` 改變；受阻交接、結果報告及來源均未變。當時沒有第二筆歷史，本輪不宣稱驗證了其他歷史筆目的保留。 |

## 保全與證據

安裝前記錄 160 個原有檔案的 SHA-256。完成後，159 個完全不變；只有本次授權加入入口的 `AGENTS.md` 改變，並核對原始全部位元組仍是其完整前綴。測試協調者只準備素材、在兩輪間改動測試 port、保存快照及核對結果，沒有代寫交接、報告、歸檔或歷史清除產物。

原始 session 工具紀錄、安裝摘要、檔案基準、清除前歷史與最後核對 JSON 位於本機被 Git 忽略的 `.scratch/feather-setup/build/live-handoff/`。`history.before-read.md` 保留實際歸檔內容；現行測試專案歷史只剩標題，是清除測試的預期結果。skill、入口、結果報告與受阻交接保留在測試專案供檢視。

這輪是 Windows Codex app 的真實獨立 session 使用流程，補足先前安裝器僅驗證原生載入的邊界。沒有服務啟動、HTTP 或 timeout 行為測試；Linux 真實模型跨 session 流程、一般多寫入者競態與所有歷史清除變體不在本輪範圍。沒有修改產品程式碼，也沒有重建或更改已交付壓縮包。
