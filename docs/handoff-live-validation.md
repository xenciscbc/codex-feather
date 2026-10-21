# 最終安裝包跨專案、新 session 實測

2026-09-08，依使用者要求，在另一個已保存的 Codex 專案 `D:/work_data/project/other/test_gpt`，使用最終 Windows x64 完整包安裝 handoff 元件與專案入口，然後建立四個全新的 Codex app session。各 session 使用相同測試專案磁碟，但沒有 fork 或傳入前一輪對話，也沒有派子代理。背景由實際交接與來源取得。

## 安裝與測試素材

- 發行包：`feather-setup-0.1.0-windows-x64.zip`，SHA-256 `7221e4ef891f1d8ff95d2fe83319e5a906f96d16aeb3253067fb4f64c13e8a24`。
- 核對校驗碼後重新解壓，直接執行內附 `feather-setup.exe install --components handoff --scope project --entrance project`；未指定替代素材包。
- skill 部署至測試專案 `.agents/skills/handoff/SKILL.md`；入口追加到原有 `AGENTS.md`。新 session 實際讀取此安裝路徑的 skill 並操作，不以載入探測請求取代真實工作。
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

## 2026-10-21：handoff-tidy 候選 skill 原生演練

本輪以原生子 Agent 直接讀取隔離專案內的候選 `handoff-tidy`、共享 handoff skill 與工具，演練模式選擇、提案、委派核對、確認、衝突、保存失敗及復原。測試協調者提供模擬使用者回覆與確認，並在提案後透過工具加入外部修改；交接的實際讀取、整理與寫回由受測 Agent 執行，協調者另以雜湊及公開 CLI 驗收。

| 原生工作 | Session | 原生回合 model／effort |
| --- | --- | --- |
| 整理操作，executor | `01a15c35-9de1-7fc2-b3c8-af3d980842e0` | `gpt-6.1-sol`／`medium` |
| Selected check 的委派讀取，analyst | `01a15c37-dbf2-76a3-9bee-e5e82038e0e6` | `gpt-6.1-sol`／`high` |

兩者皆為主 Agent 的一層子任務，沒有巢狀分派。角色與 model／effort 已核對原生 `session_meta`、`turn_context`，不另宣稱能核實後端實體模型。

| 階段 | 驗收結果 |
| --- | --- |
| 無參數 | 只詢問 Proposal、Full check、Selected check；未讀工作記錄或來源，30 個工作區檔案完全不變。 |
| Proposal | 透過工具完整列出與讀取三份記錄，只讀歷史完成標題及本機 Git 主旨／標籤；提出 timeout 合併、過時等待與缺漏建議，保存提案版本。工作區及 59 個 Git metadata 檔案不變。 |
| Full check 確認邊界 | 先回報 3 份記錄、6 個明列待辦及成本，停在讀取確認；未執行全查來源讀取或寫入。 |
| Selected check | 原生 analyst 讀取現行來源，確認 port=8428、readiness=/ready；timeout=4000 只是設定值，policy 仍待決；部署平台缺少證據。指出進度與等待 migration 的下一步過時，報告 baseline commit 與 dirty README；未執行專案程式或測試。 |
| 外部版本衝突 | 提案後由協調者加入 `EXTERNAL_V1`，再模擬確認舊提案。Agent 比對版本，暫停目標及相依來源寫入並重新提案；89 個工作區與 Git 檔案完全不變。 |
| 再確認與部分保存 | 新提案獲確認後，Agent 保存且完整讀回目標。專案磁碟的沙箱寫入受限，提權後的 Git 身分又觸發 dubious ownership；工具回報 `tracking-failed`／`state: saved`，Agent 保留來源及歷史，回報復原資訊。 |
| 復原與完成來源歸檔 | 協調者將全部 89 個 fixture 檔案原樣複製至沙箱允許的隔離目錄，保留原失敗現場；Agent 在正常權限下沿用 saved version 重試 target update、完整讀回，再核對來源版本、完成來源並由工具自動歸檔。沒有更改 Git 信任設定。 |

最終目標 `service-audit.md` 仍為進行中，版本 `83899eccbbc6e4015900b7295f7ad12a4392d6e5eb59f8cb39b67510dd67e38a`。未決 TIMEOUT acceptance、review-fixture／call count=1／REVISE／blocker、metrics 待決、舊驗證、人工補充及外部標記均保留。`timeout-notes` 只歸檔一次，完成時間 `2026-10-21T10:17:03.387618+08:00`；既有 migration 歷史保留。獨立驗收確認只改變 `.feather/handoffs/service-audit.md`、`timeout-notes.md` 與 `history.md`，專案來源、`unrelated.md`、Git metadata 均不變，執行 canary 未出現。

原始 CLI 兩次嘗試及回歸測試保存在 `.scratch/feather-handoff/runs/tidy-v030-20261021-01/`、`tidy-v030-20261021-02/`；子 Agent 素材、版本衝突注入、完整原生工具事件、雜湊驗收與 `verify_native.py` 保存在同層 `tidy-v030-20261021-native/`。最終可寫 fixture 位於 `D:/codex/visualizations/2026/10/21/01a15c11-33e2-75e1-98e2-9199010de851/handoff-tidy-native`；重跑 `python -B .scratch/feather-handoff/runs/tidy-v030-20261021-native/verify_native.py` 只驗收現存成果，不再次呼叫模型。

演練中發現 PowerShell 預設解碼會使原生輸出中文字亂碼；設定 `[Console]::OutputEncoding` 為 UTF-8 後恢復。新增公開 CLI 回歸，在 cp950、cp1252 的 process encoding 下確認工具輸出原本即為正確 UTF-8，無需改動 runtime 編碼。工具文件補上 shell 解碼指引。

原生 CLI `0.163.0-alpha.10.2` 雖指定 workspace-write，兩次回合仍被環境套用為 read-only，連讀取技能命令也遭政策封鎖，因此不列為成功。使用既有登入 home，未複製憑證或修改設定。上述成功證據屬於本 chat 的原生子 Agent 直接載入候選 skill；不宣稱已驗證 CLI／已安裝 plugin 的自動技能載入、Full check 的確認後全查，或未協調並行寫入的安全性。
