# codex-feather

讓 Codex 依工作性質分工，並用精簡交接檔把進度留給下一個 session。

Feather 提供兩項可獨立選用的能力：

- **任務分工**：主 Agent 協調四種角色，處理查找、分析、重複修改與工程實作。
- **工作交接**：記錄目前進度、新 session 接續、完成歸檔，以及搜尋、封存或清除交接歷史。

搭配 `feather-setup` 安裝器，可選擇安裝到個別專案或使用者範圍，也可獨立決定是否加入入口指引。

## 快速開始

先安裝好 Codex，再取得對應平台的 **完整發行包**：

| 平台 | 檔案 |
| --- | --- |
| Windows x64 | `feather-setup-0.1.0-windows-x64.zip` |
| Linux x64 | `feather-setup-0.1.0-linux-x64.tar.gz` |

最新本機重建包位於 `dist/2026-09-09/`，版本沿用 0.1.0，包含交接／歷史與環境健檢補強；`dist/` 根目錄保留較早版本。公開下載位置尚未發布。從原始碼取得專案後，可依下方「從來源建置」產生發行包。GitHub 原始碼 ZIP 不包含已建置的安裝器。

核對壓縮包旁的 `.sha256` 後完整解壓，保留執行檔、`_internal/`、`assets/` 和 `bundle.json` 在一起。安裝器本身不需另裝 Python；交接檔案工具需要 Python 3.11+，缺少時先詢問是否協助安裝。安裝器不代裝 Codex，也不處理登入。

**互動安裝**：Windows 執行 `feather-setup.exe`，Linux 執行 `./feather-setup`，依引導選擇目標專案、元件、範圍和入口。

**命令安裝**：在解壓資料夾執行，將路徑換成已存在的目標專案。

```powershell
# Windows：先預覽，再安裝整套能力與專案入口
./feather-setup.exe install --project 'D:/work/my-project' --components all --scope project --entrance project --dry-run
./feather-setup.exe install --project 'D:/work/my-project' --components all --scope project --entrance project
```

```bash
# Linux
./feather-setup install --project /path/to/my-project --components all --scope project --entrance project
```

安裝後，在目標專案開啟 **新 session** 載入角色與 skill。若從下載資料夾啟動，務必明確選擇目標專案；預設目標是目前工作目錄。

## 選擇安裝內容

| 選項 | 可用值 | 用途 |
| --- | --- | --- |
| `--components` | `delegation`、`handoff`、`all` | 分工、交接或整套；預設 `all` |
| `--scope` | `project`、`user` | 元件安裝範圍；預設 `project` |
| `--entrance` | `none`、`project`、`user` | 入口指引位置；新安裝預設 `none` |
| `--dry-run` | 無額外值 | 只顯示變更，不套用 |

例如只在目前專案啟用交接：

```powershell
./feather-setup.exe install --project 'D:/work/my-project' --components handoff --scope project --entrance project
```

元件範圍與入口位置可分別選擇。入口會加入同目錄既有 `AGENTS.override.md`，沒有該檔時使用 `AGENTS.md`，保留其他指引。使用者範圍入口包含能力可用條件，適用於目前環境有安裝該能力時。

完整路徑規則、自訂 home、同名衝突及 Windows／WSL 差異見 [安裝器說明](docs/setup.md)。

## 任務分工

主 Agent 負責理解需求、決定是否分工、整合結果與驗證。小任務及依賴全局資訊的工作可直接完成。

| 角色 | 工作範圍 | Feather 預設模型／reasoning |
| --- | --- | --- |
| `scout` | 查找位置、擷取有引用的事實；純唯讀 | `gpt-5.6-luna`／`low` |
| `analyst` | 原始碼、因果與文件矛盾分析；保護來源，可寫指定分析成果 | `gpt-5.6-sol`／`medium` |
| `mech-executor` | 規格完整的重複修改 | `gpt-5.6-luna`／`medium` |
| `executor` | 需要局部工程判斷的實作 | `gpt-5.6-sol`／`medium` |

例如：

> 找出登入權限判斷的位置，分析可能錯誤放行的條件，再由主 Agent 決定修改方式。

分工只允許一層，子 Agent 不再派工。`scout` 不寫成果檔；`analyst` 未指定成果路徑時直接回傳分析，指定時只能寫該成果，不能覆蓋來源。來源保護仍需核對實際差異，不宣稱 sandbox 提供逐檔保護。

使用者對子任務指定的模型與 reasoning 優先於角色預設，兩個欄位分別判定；只指定主 Agent 設定不會覆蓋子角色預設。四份角色 TOML 不鎖定模型，由主 Agent 透過原生派工參數套用。原生環境不支援時須回報，不自行替換。其他適合獨立處理的工作可使用原生通用子 Agent，未指定時預期繼承主設定；不符時回報。

這些是 Feather 的配置規則，實際權限與執行證據見 [原生相容性紀錄](docs/native-compatibility.md)。

## 交接與歷史

第一次明確要求交接才建立紀錄，之後同一工作在重要進展、受阻或完成時更新。

**留下進度：**

> 用 feather-handoff 交接 config-audit。已核對 port，還沒核對 readiness，下一步完成配置檢查並寫出報告。

**在同一專案目錄的新 session 接續：**

> 用 feather-handoff 接續 config-audit。

新 session 會讀取交接並核對實際檔案，更新過時資訊後再執行已授權工作。若只想知道進度：

> 用 feather-handoff 讀取 config-audit 的交接，上次做到哪？

查閱只回報，不執行下一步。多項未完成工作且無法辨識時，會詢問要接續哪一項。

**完成與查閱歷史：**

整項工作完成後，skill 會保存完成版，確認已完整歸入共同歷史，再移除原交接檔。

> 用 feather-handoff 查閱 config-audit 的歷史。

> 用 feather-handoff 只清除 config-audit 在 2026-09-08T15:53:57+08:00 完成的那筆歷史，其餘保留。

```text
<project>/
└── .feather/
    └── handoffs/
        ├── config-audit.md   # 未完成工作，一項一份
        ├── history.md        # 已完成工作的共同歷史
        └── archive/          # 明確要求才建立的歷史封存
```

交接資料預設被 Git 忽略，尊重使用者明確選擇及既有追蹤狀態。歷史不自動清除；清除歷史不影響未完成工作。不同 worktree 或專案之間的資料同步需另行處理。詳細規則與失敗處理見 [交接說明](docs/handoff.md)。

交接可選填分支／commit、驗證命令與結果、關鍵決策及原因，舊格式仍可接續。多項工作可各自維護，但共同歷史的歸檔、清除與封存須由單一寫入者依序操作；這是協調規則，不提供跨 session 鎖定。

> 用 feather-handoff 搜尋共同歷史，找 2026 年 9 月完成且提到 readiness 的紀錄，日期以 Asia/Taipei 為準。

> 用 feather-handoff 將共同歷史中 2026 年 8 月完成的紀錄封存到 archive/2026-08.md，其餘保留。

封存保留完整內容與完成時間。歷史操作預設只處理共同歷史；搜尋或清除封存檔時需明確包含它們。

## 更新、移除與遷移

更新時使用新版完整包執行；以下命令以 Windows 為例：

```powershell
./feather-setup.exe check --project 'D:/work/my-project' --components all
./feather-setup.exe update --project 'D:/work/my-project' --components all --dry-run
./feather-setup.exe update --project 'D:/work/my-project' --components all

# 只移除受管理的交接元件及其入口；交接資料與歷史保留
./feather-setup.exe remove --project 'D:/work/my-project' --components handoff

# 預覽從專案範圍移到使用者範圍；確認後移除 --dry-run 執行
./feather-setup.exe migrate --project 'D:/work/my-project' --components all --from project --to user --dry-run
```

重跑相同安裝不重複加入內容。遇到手動修改或未受管理的同名檔案時，預設停止並保留現況。明確選擇替換受管理內容時先備份；寫入失敗會嘗試復原，未能完整復原則回報剩餘差異與備份位置。

`check` 會分別顯示檔案狀態與環境健檢，包括 Codex、目前專案的分工啟用設定及角色配置衝突。檢查不會啟動模型任務；`session: unconfirmed` 提醒更新後在新 session 確認載入，靜態檢查正常不代表能力已實際載入。

使用者範圍元件可能供多個專案使用，遷移或移除會影響它們。衝突處理、備份與復原步驟見 [安裝器說明](docs/setup.md)。

## 已驗證範圍

2026-09-09 來源補強：完整回歸 98 項（96 通過、2 條件略過）、安裝器型別檢查 16 個來源檔通過，另有 5 個獨立 Agent 交接／封存操作驗證通過。已另行重建 Windows／Linux 二進位包至 `dist/2026-09-09/`；本輪內容、發行包驗收與限制見 [交接驗收](docs/handoff-validation.md) 及 [安裝器驗證](docs/setup-validation.md)。

截至 2026-09-08：

| 驗收 | 結果 |
| --- | --- |
| Windows 完整來源回歸 | 92 項：90 通過、2 條件略過 |
| Windows 完整發行包解壓驗收 | 56 項：42 通過、14 條件略過 |
| Linux 完整發行包解壓驗收 | 56 項：43 通過、13 條件略過 |
| 安裝器型別檢查 | mypy 15 個來源檔通過 |
| Windows 原生使用者範圍探測 | 另行通過 skill、角色、入口及雙向遷移驗證 |
| Windows Codex app 真實跨 session | 另一專案的 4 個全新 session 通過建立、接續、更正過時資訊、歸檔、查閱及指定清除 |

發行包略過的來源 OS 呼叫適配情境已由來源回歸執行；Windows 使用者 profile 探測另行實測，沒有把略過算成通過。查閱歷史前後，測試專案 169 個檔案的雜湊完全一致。

Linux 實測為 Ubuntu／WSL2 x86_64、glibc 2.39，尚未驗證相同的真實模型跨 session 流程，也未宣稱其他 Linux 發行版、較舊 glibc、macOS 或 ARM64 相容。

## 從來源建置

維護者需要 Python 3.11+；請在對應平台使用原生 Python 建置。

```powershell
python -m pip install -r requirements-setup-dev.txt
python scripts/build_setup.py
```

輸出到 `dist/`，包含完整目錄、壓縮包與 SHA-256。既有輸出目錄不會被覆寫，可用 `--output` 指定新位置。

```powershell
python -m unittest discover -s tests
python -m mypy --check-untyped-defs scripts/setup_installer scripts/feather_setup.py scripts/build_setup.py
```

原生驗收需可用的 Codex；隔離試用、模型測試與人工證據核對見 [開發與驗收指南](docs/development.md)。

## 文件

- [安裝、更新、移除、遷移與復原](docs/setup.md)
- [交接使用方式](docs/handoff.md)
- [安裝器驗證紀錄](docs/setup-validation.md)
- [真實跨專案、新 session 交接實測](docs/handoff-live-validation.md)
- [交接情境驗收](docs/handoff-validation.md)
- [分工驗證與原生相容性](docs/native-compatibility.md)
- [開發與隔離驗收](docs/development.md)

產品分工規則位於 `templates/AGENTS.md`，角色模板位於 `templates/*.toml`，交接 skill 位於 `skills/feather-handoff/`。根目錄的 `AGENTS.md` 是本專案開發指引。

交接檔案工具需要 Python 3.11+（僅標準函式庫）；安裝器本身仍不需 Python。缺少時 Agent 先詢問是否協助安裝，可唯讀查閱但不繞過工具寫入。操作與驗收見 [交接工具說明](skills/feather-handoff/references/tool.md) 與 [驗收記錄](docs/handoff-tool-validation.md)。
