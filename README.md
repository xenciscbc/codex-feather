# codex-feather

輕量 Codex 分工規則、四個原生角色模板及隔離驗收入口。六張待辦的實作內容已交付；真實模型派工／綁定仍需明確啟用測試，不能以靜態檢查取代。

## 正式安裝

`feather-setup` 提供 Windows x64／Linux x64 的完整離線發行包，不要求使用者另裝 Python。可選任務分工、交接或整套，支援專案／使用者範圍，以及獨立選擇的入口宣告。直接啟動會提供引導；命令模式支援檢查、預覽、安裝、更新、移除與明確遷移。

操作、衝突及復原方式見 [安裝器說明](docs/setup.md)，平台與原生 Codex 載入證據見 [安裝器驗證紀錄](docs/setup-validation.md)。本機二進位建置輸出在 `dist/`；發布位置需由維護者另行提供。

## 角色與規則

| 工作 | 角色 | 預期模型 / reasoning |
| --- | --- | --- |
| 查找位置、擷取引用事實 | scout | gpt-5.6-luna / low |
| 原始碼推理、因果與文件矛盾分析，唯讀 | analyst | gpt-5.6-sol / medium |
| 完整規格的重複修改 | mech-executor | gpt-5.6-luna / medium |
| 需要局部工程判斷的實作 | executor | gpt-5.6-sol / medium |

小任務與持續整合全局資訊的推理由主 Agent 直接完成。其他值得獨立處理的工作可使用原生通用子 Agent，預期繼承主模型與 reasoning；有效預設或原生能力不符時明確回報。

產品指令在 `templates/AGENTS.md`，原生模型綁定在四份 TOML。根目錄 `AGENTS.md` 僅供本專案開發使用。brief、所有權、依賴、收回、整合及簡短回報規則集中於產品指令，不引入固定審查鏈。

## 靜態檢查

需要 Python 3.11+。試用工具使用標準函式庫；包含安裝器的完整驗收需先安裝 `requirements-setup-dev.txt`。Windows 原生探測需要 Codex CLI；本次版本為 0.153.4。

```powershell
python -m pip install -r requirements-setup-dev.txt
python -m unittest discover -s tests
python -m compileall -q scripts tests
python scripts/trial.py prepare .scratch/feather-mvp/runs/my-scout --scenario scout
python scripts/trial.py check .scratch/feather-mvp/runs/my-scout
```

每個情境都使用新的目錄；既有目錄拒絕覆寫。入口建立獨立 `home`、四份角色、最小 config、workspace、基準雜湊與 `review.json`，不複製真實設定、憑證或 hook。舊 format=1 的試用目錄請重新準備。

## 同一入口的九種情境

`--scenario` 僅在 prepare 選擇，後續指令依 manifest 使用原情境。

| 情境 | 素材與預期結果 |
| --- | --- |
| scout | 現行設定 7319、/ready、4；排除歷史設定 8080 |
| analyst-code | OR 授權判斷錯放行兩類帳戶；分析並建議，不修改 |
| analyst-doc | 7 天刪除與 30 天完整備份留存衝突；交回主 Agent |
| mech | 僅兩份現行配置的 timeout 1000 → 2500；保留 archive |
| executor | 實作有輸入驗證且不溢位的 capped exponential retry |
| direct-small | 主 Agent 直接計算 17 + 25 = 42 |
| direct-global | 主 Agent 綜合時間與預算限制選 A |
| generic | 通用子 Agent 創作三個雙字名稱，主 Agent 提供選擇理由 |
| coordination | 獨立查找／分析、依賴與共享檔案依序寫入、缺規格阻塞、重新分工、矛盾整合 |

每個試用的 `review.json` 含具體人工验收準則。素材及規格位於 `tests/fixtures/`；已知答案和工程行為檢查位於 workspace 外的 `scripts/scenarios.py`。

## 原生指令載入探測

以本機原生執行檔取代下列路徑；Windows 使用 `codex.exe`，不能傳入 `.ps1` / `.cmd` shim。

```powershell
$featherCodex = 'C:/path/to/codex.exe'
python scripts/trial.py probe .scratch/feather-mvp/runs/my-scout --codex $featherCodex
```

探測不送出模型任務。核對 `probe.stdout` 的 Feather 指令來源、隔離技能根目錄，以及 `probe.stderr` 的載入錯誤。成功僅表示指令載入；不能證明自訂角色、模型或 reasoning 已執行。版本與來源詳見 [原生相容性](docs/native-compatibility.md)。

## 明確啟用真實模型測試

以下會消耗模型用量。先在另一個 shell 將 `CODEX_HOME` 設為試用目錄的 `home`，用原生 CLI `login` 完成隔離登入，然後關閉該 shell。不要複製或搬移真實 home 的憑證／設定。若環境採用其他登入方式，依該環境規範辦理。

```powershell
python scripts/trial.py smoke .scratch/feather-mvp/runs/my-scout --codex $featherCodex --enable-live --main-model '<使用者選定的主模型>' --main-reasoning '<使用者選定的 reasoning>'
```

未同時提供啟用旗標、主模型及 reasoning 時不啟動原生程序。參數只作用於這次隔離執行，不寫入主模型配置或改變並行數。入口清除繼承的 CODEX_* 路由環境值，再設定子程序的隔離 home；原 shell 不受影響。

唯讀情境採 read-only；修改情境採 workspace-write，再由角色模板與 brief 限定所有權。沒有額外放寬 sandbox 的參數。600 秒逾時保留錯誤；Windows 會終止該次原生程序樹。每次重試準備新目錄。

## 成果與證據驗收

```powershell
python scripts/trial.py verify .scratch/feather-mvp/runs/my-scout
```

`check` 檢查四角色配置及原始素材未變；`verify` 容許情境指定的寫入，檢查範圍外的新增／刪除／修改，並驗證批次結果、工程函式行為、協調檔案內容。executor 的 verify 會在子 Python 程序中執行生成的 retry.py；這是程式測試，不是模型呼叫。Python 編譯檢查是語法檢查，並非型別檢查；安裝器另外執行 mypy，既有試用工具的驗收方式維持不變。

所有唯讀／創作／分析答案及派工行為仍由 `review.json` 準則檢閱原生事件與最終回覆。`artifacts: pass` 只表示檔案成果通過，不能證明選角正確、從未寫入後還原、工作是否並行或模型綁定。

人工核對必須包含：

1. 原生 spawn、完整 brief、父子關係、收回與完成紀錄。不能只相信最後答案自述。
2. 情境的已知答案、引用與副作用；coordination 特別核對 A/B 可並行、C 等 A、D 等 C、E 不猜值且其他工作繼續、F 查找失敗後改為分析而非原樣重試。
3. 預期模型、角色模板／請求設定、每回合原生執行證據分層。Thread 的 model / reasoningEffort metadata 不是每回合 telemetry；取得不到時保留未確認。
4. 通用子 Agent 的呼叫方式、有效預設與繼承設定；實際繼承證據不足不能宣稱通過。主 Agent 處理矛盾與缺漏，最終先交付結論，再簡述分工原因、成果及證據狀態。

記錄保存在試用目錄的 stdout、stderr、answer.md、verification.json、review.json 與隔離 home。補上人工結果與原生事件定位；入口不根據手填 review.json 自動宣稱整體通過。日誌可能含任務及帳戶內容，整個 runs 目錄均忽略提交。耗時僅採原生程序牆鐘值，用量引用原生來源，缺失記為未知，不設節省門檻。

## 最小手動配置

僅在新的隔離 home 試用：把四份 `templates/*.toml` 放入 `home/agents/`，把候選 `templates/AGENTS.md` 放入 workspace，在 home config 設定 `agents.enabled = true`。建議使用 prepare 產生含 `.feather-root` 根目錄標記的相同配置。

檢查同名角色、同層 `AGENTS.override.md`、專案 `.codex/agents/` 與生效指令優先順序；發現衝突使用新隔離目錄，不覆寫既有配置。角色檔的 model/reasoning 是原生綁定，指令中的模型文字不能替代它。即時權限覆寫可能覆蓋角色 sandbox，混合可寫／唯讀情境須檢阅實際權限和副作用。

安裝與遷移使用 [feather-setup](docs/setup.md)；不提供 hook 或持久工作流引擎。分工實作與尚待真實模型測試的項目見 [驗證紀錄](docs/validation.md)。

## 工作交接

獨立的 [feather-handoff skill](skills/feather-handoff/SKILL.md) 以精簡 Markdown 保存同專案的工作進度，支援讀取、接續、完成歸入共同歷史，以及按明確要求清除歷史。交接資料預設 Git 忽略，尊重使用者的追蹤選擇。

可由 feather-setup 選擇是否加入入口，以及入口的專案／使用者範圍。交接使用方式與隔離驗收見 [交接說明](docs/handoff.md)。
