# feather-setup：Feather 獨立安裝器

Status: ready-for-agent

## Problem Statement

Feather 已有任務分工的角色模板與指引，以及 feather-handoff skill。目前部署仍靠手動複製及隔離試用流程，缺乏一致的正式安裝、更新、移除與衝突處理。只加入入口宣告，不能確保對應能力已安裝。

## Solution

提供服務整套 Feather 的獨立安裝器 feather-setup。使用者下載完整發行包，選擇元件、安裝範圍，以及是否加入入口宣告與宣告範圍。安裝器負責確定性的檔案與設定操作，無須先安裝 setup skill。

第一版提供 Windows x64 與 Linux x64 的可直接執行安裝器，不要求使用者另裝 Python。每個平台的發行包包含安裝器、同版本元件素材、版本與元件清單。從發行包取用元件，不在安裝途中逐項從網路下載。取得新版發行包後執行更新。

## User Stories

1. As a Feather 使用者, I want 下載包含安裝器與所有元件的完整發行包, so that 不必自行尋找或配對版本。
2. As a Windows x64 使用者, I want 直接執行安裝器, so that 不必先安裝 Python。
3. As a Linux x64 使用者, I want 直接執行安裝器, so that 不必先安裝 Python。
4. As a Feather 使用者, I want 從本地發行包部署元件, so that 安裝途中不依賴逐項網路下載。
5. As a Feather 使用者, I want 選擇只安裝任務分工, so that 能採用需要的角色能力。
6. As a Feather 使用者, I want 選擇只安裝交接, so that 不必同時啟用任務分工。
7. As a Feather 使用者, I want 一次安裝整套 Feather, so that 不必重複執行各元件安裝。
8. As a 專案使用者, I want 預設將元件安裝到目前專案, so that 安裝範圍容易掌握。
9. As a 多專案使用者, I want 選擇使用者範圍安裝, so that 多個專案可共用能力。
10. As a Feather 使用者, I want 安裝目標獨立於發行包解壓位置, so that 可以從下載資料夾部署到指定專案。
11. As a Feather 使用者, I want 安裝元件但不加入入口宣告, so that 可以自行決定何時加入使用指引。
12. As a 專案使用者, I want 選擇專案範圍入口, so that 指引適用於所選專案。
13. As a 多專案使用者, I want 選擇使用者範圍入口, so that 能共用使用指引。
14. As a Feather 使用者, I want 分別選擇元件與入口的範圍, so that 使用方式不被安裝位置綁定。
15. As a 混合範圍使用者, I want 共用入口僅在目前環境具備能力時生效, so that 其他專案不會被要求使用不存在的元件。
16. As a 已有覆寫指引的使用者, I want 入口加入實際會被讀取的指引檔, so that 設定不會因載入優先序而失效。
17. As a Feather 使用者, I want 操作摘要列出元件與入口的實際位置, so that 能核對此次影響範圍。
18. As a 已有安裝的使用者, I want 偵測跨範圍同名元件並沿用既有安裝, so that 不會產生重複能力。
19. As a Feather 使用者, I want 明確執行範圍遷移, so that 能控制來源移除與目的部署。
20. As a 多專案使用者, I want 遷移摘要說明使用者範圍來源的影響, so that 不會誤以為只改變目的專案。
21. As a Feather 使用者, I want 直接啟動安裝器取得互動引導, so that 不必記住所有參數。
22. As a 腳本使用者, I want 完整參數直接執行, so that 自動化不會被重複確認打斷。
23. As a Feather 使用者, I want 預覽變更而不套用, so that 可以先檢查結果。
24. As a Feather 使用者, I want 檢查目前安裝狀態, so that 能辨識已安裝、沿用、缺少或衝突的內容。
25. As a 已有專案指引的使用者, I want 安裝器只管理 Feather 區塊, so that 其他指引保持完整。
26. As a 已有 Codex 設定的使用者, I want 只合併必要項目, so that 我的模型、reasoning 與並行偏好不被重設。
27. As a Feather 使用者, I want 重複安裝不產生重複內容, so that 可以安心重新執行操作。
28. As a Feather 使用者, I want 取得新版發行包後更新已選元件, so that 不必手動替換各個檔案。
29. As a 自訂角色的使用者, I want 更新前辨識我的手動修改, so that 自訂內容不會被直接覆寫。
30. As a 自訂入口的使用者, I want 衝突時保留現況並顯示差異, so that 能決定保留或替換。
31. As a Feather 使用者, I want 明確替換前保存備份, so that 必要時能取回原有內容。
32. As a 腳本使用者, I want 衝突以非成功結果結束且不改寫現況, so that 上層流程可可靠處理失敗。
33. As a Feather 使用者, I want 移除所選的受管理元件與入口, so that 不再使用時能清理安裝內容。
34. As a 交接使用者, I want 移除安裝時保留交接檔與交接歷史, so that 工作進度不會遺失。
35. As a Feather 使用者, I want 來源不明的同名內容保持完整, so that 安裝器不會誤刪其他工具或我的資料。
36. As a Feather 使用者, I want 多元件操作途中失敗時整次還原, so that 環境不留下半套安裝。
37. As a Feather 使用者, I want 復原失敗時得到剩餘變更與備份位置, so that 可以接續修復。
38. As a 尚未安裝 Codex 的使用者, I want 得到安裝指引並停止 Feather 安裝, so that 不會留下無法使用的部分設定。
39. As a Codex 使用者, I want Feather 安裝器不代裝 Codex 或處理登入, so that 帳號與主程式由我自行管理。
40. As a Windows 與 Linux 使用者, I want 發行包經過實際啟動與 Codex 載入驗證, so that 檔案部署成功也有可使用的證據。

## Implementation Decisions

### 元件與範圍

- 服務整套 Feather；第一版可選「任務分工」「交接」，並提供整套安裝。
- 任務分工包含既有角色設定及相應分工指引；交接包含完整 feather-handoff skill。選擇入口宣告時加入相應指引。
- 支援專案與使用者兩種元件安裝範圍，預設專案。下載或解壓位置不決定安裝目標。
- 入口宣告另行選擇：不加入、加入專案範圍、加入使用者範圍。元件安裝範圍不替使用者決定入口位置。
- 允許使用者範圍入口搭配專案元件；入口必須明示僅在目前環境具備對應能力時使用。操作摘要分別列出元件與入口的範圍，不宣稱入口能使專案元件全域可用。
- 同一目錄已有 Codex 覆寫指引檔時，在該檔加入 Feather 區塊；否則使用一般指引檔。摘要顯示實際目標檔案；載入規則見 Further Notes。
- 偵測跨範圍同名元件，提示沿用既有安裝。第一版不主動建立跨範圍同名副本；變更範圍須明確執行遷移，不假設專案副本會覆蓋使用者副本。

### 操作入口

- 提供檢查、安裝、更新、移除；另支援明確的範圍遷移流程。
- 直接啟動時提供互動引導，選擇操作、元件、元件範圍與入口位置，顯示變更摘要後執行。
- 完整命令參數直接執行已指定操作，不重複確認；提供 --dry-run 預覽。
- 非互動模式遇到衝突即停止並回報，不等待輸入或自行覆寫。
- 檢查與預覽不套用安裝變更；摘要區分已安裝、將修改、沿用、衝突及未完成的內容。

### 既有內容與所有權

- AGENTS 類檔案只管理清楚標記的 Feather 區塊，保留區塊以外內容。不存在目標檔案時才建立。
- Codex 設定只管理 Feather 必要項目，保留其他設定。保留主 Agent 的模型、reasoning 與並行偏好。
- 重複安裝不重複加入內容。更新與移除依安裝紀錄辨識自身管理的項目，不能把同名且來源不明的內容直接當作可覆寫內容。
- 安裝紀錄需足以辨識元件、版本、範圍、目標、上次安裝內容及相關入口，支援後續比較與復原；具體儲存格式由實作決定。
- 更新或移除前比較上次安裝內容。若使用者手動修改了受管理內容，保留現況並列出衝突，由使用者明確選擇保留或替換；替換前保存備份。
- 移除只處理所選、由安裝器管理的元件及入口，不刪除交接檔、交接歷史或無關資料。
- 遷移須明確列出來源、目的地及將移除的來源項目。使用者範圍遷移會改變其他專案可見的能力，摘要不得把它描述成只影響目的專案。

### 失敗復原

- 一次操作採整體成功原則，包含同次選擇的多個元件、設定及入口。
- 寫入前完成檢查、變更計畫與備份。途中失敗時，還原本次已套用的修改，不保留未告知的部分成功狀態。
- 還原失敗時不得宣稱操作成功或已完整還原；列出剩餘變更、備份位置及可採取的復原步驟。
- 復原及移除只處理本次操作或既有安裝紀錄所管理的內容，保留操作前已存在的其他資料。

### Codex 邊界

- 安裝器只負責 Feather，不代為下載或安裝 Codex，也不處理帳號登入。
- 找不到可用 Codex 環境時，提供安裝指引並停止安裝，不寫入半套 Feather 設定。
- 不把 Codex CLI 不在 PATH 單獨視為未安裝；實作需核對可用環境的辨識方式。
- 不以現有隔離試用曾使用的 Codex 版本直接宣告最低支援版本。

## Testing Decisions

- 以一個最高層整合驗收切入點為主：使用者輸入或安裝器命令 → 隔離環境中的輸出、退出結果、檔案及設定。測試安裝器外部行為，不把內部函式、資料結構、提示文案或步驟順序當成正確性的替代證據。
- 測試範圍包含發行包啟動、互動及命令操作、元件部署、入口與設定合併、重複偵測與遷移、更新及移除、衝突保留與備份、失敗復原。
- 沿用現有 Python 標準函式庫命令列測試及隔離 prepare／check／verify 試用方式；優先擴充同一情境層，不為各內部模組另建測試框架。測試環境可用 Python，交付給使用者的執行檔仍不得要求另裝 Python。
- 在 Windows x64 與 Linux x64 執行實際發行包；角色、skill 與入口的 Codex 原生載入檢查作為同一部署情境的後續驗收，區分檔案成果證據與原生使用證據。
- 成功路徑之外，必須覆蓋手動修改、同名衝突、權限或寫入失敗，以及復原再次失敗；使用隔離素材與故障注入，保留既有檔案基準以驗證未遺失或誤刪。

### 驗收條件

1. Windows x64 與 Linux x64 發行包皆能在沒有另裝 Python 的環境啟動；包內安裝器與元件版本一致，安裝不需逐項下載元件。
2. 可分別安裝任務分工、交接或整套；支援專案與使用者範圍，未選元件不被安裝。
3. 入口可選不加入、專案或使用者，與元件位置獨立；混合範圍入口包含能力可用條件。
4. 有 AGENTS.override.md 時修改該檔的 Feather 區塊，否則使用 AGENTS.md；保留其他文字，重複執行不重複加入。
5. 已有 Codex 設定與其他元件時保留無關內容；模型、reasoning 與並行偏好不被重設。
6. 跨範圍同名元件得到沿用或明確遷移流程，不暗中新增副本。遷移失敗遵守整體復原規則。
7. 互動與完整參數模式得到一致結果；完整參數不重複確認，檢查及 --dry-run 不套用變更。
8. 使用新版完整發行包更新已選元件及其受管理入口；重複安裝或更新不產生重複內容。
9. 手動修改後的更新與移除回報衝突且保持現況；明確替換前建立可用備份，非互動衝突以非成功結果結束。
10. 在多元件操作的中途注入寫入失敗，原有檔案與設定恢復，沒有本次遺留的半套安裝；再注入復原失敗時，回報剩餘變更與備份位置。
11. 移除只刪除所選且由安裝器管理的內容；既有無關資料、交接檔與交接歷史保持完整。
12. 找不到可用 Codex 時提供指引並停止安裝；不下載 Codex、不觸發登入、不留下部分安裝。
13. 在 Windows 與 Linux 分別驗證原生 Codex 對角色、skill 與入口的實際發現，包含專案、使用者及混合範圍；檔案比對與原生載入證據分開記錄。

## Out of Scope

- macOS、Windows ARM64 與 Linux ARM64 發行包。
- 安裝或管理 Codex 本體、帳號與憑證。
- 必須先安裝才能使用的 setup skill；未來可另加薄型引導入口。
- 背景自動更新、線上逐元件下載器、一般套件管理平台。
- 更改 feather-handoff 的交接資料語意或自動清理交接資料。

## Further Notes

以下為規劃時查核的官方規則；實作需以支援平台驗證。路徑表是發現規則，不代替使用者的範圍選擇。

| 內容 | 使用者範圍 | 專案範圍 |
| --- | --- | --- |
| Agent 指引 | Codex home 的 AGENTS.override.md 或 AGENTS.md | 專案根目錄到目前目錄的逐層指引 |
| 角色 | Codex home 的 agents/ | 專案 .codex/agents/ |
| Skills | 使用者 home 的 .agents/skills/ | 目前目錄至 repo root 各層 .agents/skills/ |
| Codex 設定 | Codex home 的 config.toml | 專案 .codex/config.toml |

- Codex home 預設為 ~/.codex，可由 CODEX_HOME 改變。Skills 的 user-home 規則不同，不可一律隨 CODEX_HOME 改寫。
- Windows 原生與 WSL 是不同環境；WSL 使用 Linux home，不能假設兩者共用安裝。
- 同一目錄只載入優先的 AGENTS 檔案，較深層指引可覆蓋較外層指引，且存在文件大小限制。寫入成功不等於所有工作目錄都已正確啟用。
- 同名 skills 不合併，可能同時出現在選擇器。官方資料未明訂 user/project 同名自訂角色的勝出規則；第一版依已確認的重複偵測及明確遷移規則處理。
- agents.enabled 現行預設為 true，不應因設定項缺省就視為停用，也不應為了補預設值而無必要地修改設定。
- 專案設定受信任狀態與設定優先序影響；不得自行改變專案信任或把檔案存在直接等同於生效。
- Linux 執行檔的最低系統相容性、Codex 環境辨識方式，以及混合範圍下的實際角色與 skill 發現，需在實作驗收中取得證據。尚未完成的平台或情境不得列為已驗證。

官方來源：

- [AGENTS 載入規則](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Skills](https://learn.chatgpt.com/docs/build-skills)
- [設定優先序](https://learn.chatgpt.com/docs/config-file/config-basic)
- [Windows 與 WSL](https://learn.chatgpt.com/docs/windows/windows-app)
