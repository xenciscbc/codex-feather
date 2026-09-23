# codex-feather

[English](README.md) | **繁體中文**

讓 Codex 依工作需要分工，並把可接續的進度與證據留給下一個 session。

- **分工**：主 Agent 安排查找、分析與實作，核對子任務成果後整合；小任務直接處理。
- **交接**：保存進度、決策與驗證紀錄，接續前核對相關來源的變動。

交接保存在專案內的 Markdown，工具使用 Python 標準函式庫；不需要資料庫或常駐服務。分工與交接可分別安裝。

## 安裝

### 原生 Codex plugin

Repository 包含 `handoff`、`setup`、`model`、`auto-on` 與 `auto-off` 五個 skills 的 plugin 封裝。可透過 Git marketplace 安裝已發布版本：

```powershell
codex plugin marketplace add xenciscbc/codex-feather
codex plugin add codex-feather@codex-feather
```

Codex 可能以 `codex-feather:handoff` 等 plugin 命名空間顯示技能；其短名稱為 `handoff`／`setup`／`model`／`auto-on`／`auto-off`，子 Agent 名稱不帶此前綴。

開新 session，說「使用 setup 設定目前專案」或指定全域使用。Setup 先列出專案與使用者範圍的安裝狀態，再詢問要安裝、更新、移除或遷移哪一項；已指明的選擇不會重複詢問。

| 可選項目 | 安裝內容 |
| --- | --- |
| handoff | 交接自動維護規則，使用 plugin 已提供的 skill；既有工作交接會隨重要進展、受阻與完成更新。 |
| delegation | Agent 分派規則及五個原生角色檔案。 |
| 兩者 | 同時安裝上述兩項，也可日後分別更新、移除或選不同適用範圍。 |

例如：「用 setup 只安裝目前專案的 handoff 自動維護規則」、「用 setup 全域安裝 agent 分派規則與角色，保留 handoff 現況」或「用 setup 在目前專案安裝兩者」。單純安裝 plugin 不會寫入這些外部設定。來源 setup 需要 Python 3.11+ 與 PyYAML（`requirements-setup.txt`）。

更新 plugin 後，再請 setup 同步外部設定；移除 plugin 前，先讓 setup 清理受管理的角色與入口。既有獨立交接 skill 須明確選擇切換，setup 不會再安裝重複副本。詳見 [plugin 設定與生命週期](docs/plugin.md)。`v1.0.1` 及更早 tag 不含本次 plugin 封裝。

### 獨立安裝器

先準備好 Codex；交接功能另需 Python 3.11+。安裝器本身不需要 Python。

1. 依 [安裝說明](docs/setup.md) 取得或建置對應平台的完整安裝包。
2. Windows 開啟 `feather-setup.exe`；Linux 執行 `./feather-setup`。依引導選擇目標專案、功能、專案或使用者範圍，並決定是否加入入口指引。
3. 在目標專案開啟新的 Codex session，確認選用的 skill／角色已列出後使用。

目前尚未提供公開的二進位下載；來源建置方式也在安裝說明中。

使用者範圍是本機共用的全域安裝；專案範圍只安裝到指定專案。安裝器支援檢查、更新、範圍遷移與移除，更新前檢查衝突並備份。**Git pull／push 不會同步已安裝的 skill**；要套用新版，需從新版完整包更新對應範圍，再開新 session。

## 分工方式

| 角色 | 用途 | 原生權限 | 模型／推理預設 |
| --- | --- | --- | --- |
| scout | 找位置、擷取可引用事實 | read-only，不產出檔案 | gpt-6-luna／low |
| analyst | 因果、影響、安全分析及計畫審查 | workspace-write；來源禁止修改，只能寫明確指定成果 | gpt-6-sol／high |
| mech-executor | 依完整規格重複修改 | workspace-write，僅指定範圍 | gpt-6-luna／medium |
| executor | 需要局部工程判斷的實作 | workspace-write，僅指定範圍 | gpt-6-sol／medium |
| security-executor | 已授權安全敏感實作，驗證正常與濫用／拒絕案例 | workspace-write，僅指定範圍 | gpt-6-sol／high |

只有主 Agent 派工，子 Agent 不再向下委派。每個子任務回報成果、變更、驗證與阻礙，由主 Agent 驗收；共享寫入依序處理。同一原因再次阻塞時收回處理，保留已有成果，避免原樣無限重試。

模型與 reasoning 各自依適用任務指定、session 覆寫、已保存設定、封裝預設決定。五角色預設為 scout `gpt-6-luna/low`、analyst `gpt-6-sol/high`、mech-executor `gpt-6-luna/medium`、executor `gpt-6-sol/medium`、security-executor `gpt-6-sol/high`。主模型與並行偏好不變。原生派工傳入兩欄；設定或子 Agent 自述不能證明實際模型。預設值與完整規則見 [分工規則](templates/AGENTS.md)。

### 修改角色模型

說 **「用 model 列出目前角色設定」**。它會先列出每個角色的模型、推理強度與安裝來源，再詢問想修改的項目。列出修改前後的值後，最後詢問是 **僅本次 session** 還是 **永久修改**；已在請求中說明的選擇不會重複詢問。

Session 修改只套用到這段對話後續的子 Agent 派工，不寫入檔案。永久修改依角色實際安裝位置決定：專案安裝修改專案，共用的使用者安裝修改全域。因此，專案若沿用全域角色，永久修改也會影響共用該安裝的其他專案。套用前會預覽影響路徑；所有權不明或指引衝突時停止寫入。

永久設定會在支援的 setup 更新與範圍遷移後保留。未指定的欄位維持原值，已啟動的子 Agent 不變；保存的指引由新 session 載入。`model` 由 plugin 提供，需要 Python 3.11+ 與 PyYAML，也能管理既有獨立安裝器部署的角色。單純安裝 plugin 不會部署角色。

### 自動計畫審查

封裝預設為 **off**。`$auto-on` 或 `$auto-off` 不帶參數或使用 `session` 時，只改這段對話，不寫檔。加上 `project` 或 `user` 才保存到已有所有權紀錄的安裝；工具先預覽路徑，再用計畫 ID 套用並讀回。使用者範圍可能影響多個專案，支援的更新會保留設定。詳見 [審查模式說明](skills/setup/references/auto-review.md)。

Auto 模式只在重大安全邊界變更、資料遷移、不可逆操作或複雜跨模組工作實作前交由全新脈絡的 analyst 審查。每個邏輯計畫最多兩次自動呼叫，失敗也計入。READY 可接續已授權工作；第二次仍 REVISE 時暫停依賴該計畫的實作，獨立的已授權工作可繼續。再次審查須明確要求。切換模式不重置次數；off 模式仍可明確要求審查。這是 Agent 指引，並非 runtime hook。

專案政策寫入 `<project>/AGENTS.md`（或既有 `AGENTS.override.md`）與 `<project>/.feather/setup/state.json`；使用者政策寫入 `<CODEX_HOME>/AGENTS.md`（或 override）與 `<CODEX_HOME>/feather-setup/state.json`，未設定 CODEX_HOME 時使用 `~/.codex`。入口所有權另記於相同 state 目錄的 `entrances.json`。必須已有該範圍的 setup 與可驗證入口；永久開關不會隱式安裝角色。任務／session 明確偏好優先於保存值，切換不清除阻礙或重置次數。既有交接會保存計畫 ID、呼叫數、判定與未解阻礙，換模型、改名或新 session 都不重算。

## 使用

安裝後，直接對 Codex 說你要做什麼：

| 想做的事 | 可以這樣說 |
| --- | --- |
| 指定分析角色與模型 | 用 analyst，以 gpt-6-luna 審查這個授權計畫；推理強度 high。 |
| 指定安全實作 | 用 security-executor，以 gpt-6-sol 修正已確認的授權漏洞並驗證拒絕案例。 |
| 分工處理任務 | 幫我分工檢查登入功能，找出問題並修正。 |
| 查看角色設定 | 用 model 列出目前模型與推理強度。 |
| 本次調整推理強度 | 用 model 將 scout 的推理強度改成 medium，只限這次 session。 |
| 永久修改角色設定 | 用 model 永久將 executor 設成 gpt-6-sol，推理強度 high。 |
| 切換計畫審查 | 用 $auto-on 設定本次 session；用 $auto-off project 保存到目前專案。 |
| 保存目前進度 | 用 handoff 交接目前工作。 |
| 查看工作清單 | 用 handoff 列出目前的交接。 |
| 接續工作 | 用 handoff 接續登入功能的工作。 |
| 只看進度 | 用 handoff 讀取登入功能的交接。 |
| 保存來源基準 | 保存登入功能的交接，記錄 `src/auth.py` 與 `config/auth.json` 的基準。 |
| 搜尋完成紀錄 | 用 handoff 搜尋交接歷史，找出提到登入功能的紀錄。 |
| 封存指定歷史 | 用 handoff 封存已選定的完成紀錄，保留完整內容。 |
| 查找 Claude 交接 | 用 handoff 查找專案 `D:/work/my-project` 對應的 Claude memory 中的交接，只讀取並摘要。 |

## 交接與接續

第一次要求交接後，每項工作維護一份 `.feather/handoffs/<工作名稱>.md`。Agent 在重要進展、受阻與完成時更新目標、進度、下一步及必要限制，也可記錄環境、驗證與決策。整項工作經主 Agent 驗收完成後歸檔；若歸檔失敗，保留原檔供重試。

接續時先讀完整交接，核對相關來源，再簡短交代 **目前進度、保存後的變動、下一步與阻礙**，繼續已授權工作。多項工作無法辨識時才詢問要接續哪一項。只查看進度不會比對來源或執行下一步。

- **來源基準**：可選擇保存相關檔案的內容摘要與 Git 狀態。接續時辨識未變、已變、新增、缺失與無法確認；一般進度更新保留舊基準。只比對選定範圍，不代表全專案都未變。
- **驗證對應**：沿用 `驗證：` 記錄測試命令、工作目錄、時間及結果，並可對應基準擷取時間、檔案範圍與測試後比對結果。基準相符不等於測試通過，更新基準也不會讓舊測試自動適用於新內容。
- **根目錄診斷**：辨識失敗時回報讀取路徑與原因，保留可讀結果，並在寫入前停止。確認根目錄後可明確指定，避免在子目錄另建交接；不自動改變 Git 信任設定。
- **歷史管理**：依工作名稱、日期或關鍵字搜尋完成紀錄；可明確選取封存或清除。封存保留完整內容，清除才會移除選定紀錄。
- **Claude memory 查找**：指定專案路徑後，依 Claude 設定與專案關聯定位對應的 memory 目錄，包含自訂位置與 Git worktree 的共用儲存庫關聯；也可直接指定 memory 目錄。位置無法唯一確認時會先釐清，不猜測。定位後唯讀查找交接及同專案連結，不自動匯入或執行記錄中的工作。

舊交接沒有來源基準仍可使用，接續時採人工核對。交接資料預設被 Git 忽略；既有或明確指定的追蹤選擇會保留。請在同一份專案目錄接續，跨 worktree 同步需另外處理；不同 session 的共同歷史寫入也需協調，工具沒有跨 session 鎖定。

分工與接續流程由 Agent 指引執行，工具負責格式、檔案與來源比對。安裝檢查通過不代表每個原生派工行為或 sandbox 都已驗證；平台證據與未確認項見下方驗收文件。

## 更多說明

- [安裝、更新與移除](docs/setup.md)
- [交接、搜尋歷史與封存](docs/handoff.md)
- [來源基準與驗證紀錄](skills/handoff/references/snapshots.md)
- [分工規則](templates/AGENTS.md)
- [開發與驗收](docs/development.md)
- [交接工具驗收紀錄](docs/handoff-tool-validation.md)
- [接續可靠性驗證與限制](docs/resume-reliability-validation.md)
- [平台與原生能力限制](docs/native-compatibility.md)
