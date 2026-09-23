# Feather 獨立安裝器

原生 plugin 使用者請先看 [plugin 設定流程](plugin.md)：plugin 提供五個 skills，其中 `setup` 使用相同安裝器分別管理交接維護入口、外部角色與分工入口。以下是獨立離線包的完整操作說明；獨立包的 handoff 會部署 skill，plugin setup 的 handoff 則使用 plugin skill，只部署維護入口。

獨立 `feather-setup` 以完整離線包安裝、檢查、更新、移除或遷移 Feather。可選 `delegation`（五角色）及 `handoff`（交接 skill），`all` 表示整套。安裝器不安裝 Codex、不登入帳號，也不在安裝途中下載元件。

## 取得與啟動

使用對應平台的完整壓縮包：

- Windows x64：`feather-setup-0.1.0-windows-x64.zip`
- Linux x64：`feather-setup-0.1.0-linux-x64.tar.gz`

核對同批發行的 `.sha256` 後完整解壓；保留執行檔、`_internal/`、`assets/` 與 `bundle.json` 在同一資料夾。這些是可直接執行的包，不要求另裝 Python。發行包仍需由維護者上傳至發行位置；最新本機重建包在 `dist/2026-09-09/`，版本沿用 0.1.0，`dist/` 根目錄保留較早包。該舊包只有四角色與舊版設定功能；五角色與審查模式需使用含新版素材的安裝器。不能把原始碼 ZIP 當作二進位發行包。

Windows 直接執行 `feather-setup.exe`；Linux 在解壓資料夾執行 `./feather-setup`。新版來源工具不帶操作名稱時進入互動引導：先確認專案路徑，列出專案與使用者範圍的安裝狀態，再選操作、元件、元件範圍與適用的入口選項。檢查預覽後輸入 `yes` 才套用。預設確認是 `no`；取消、輸入結束或只預覽均不套用。上述舊版二進位包仍使用原有互動順序，需重新建置才有此流程。

下載／解壓位置不決定安裝目標。專案預設為目前工作目錄；從下載資料夾啟動時，請在引導中選正確專案，或明確使用 `--project`。專案必須已存在。

## 命令使用

以下以 PowerShell 為例；Linux 將 `./feather-setup.exe` 改成 `./feather-setup`，路徑改為 Linux 路徑。完整命令直接执行，不另行確認。省略 `--components` 時選整套；省略 `--scope` 時選專案；新安裝省略 `--entrance` 時不新增入口。

選項使用完整名稱，例如 `--components`；安裝器與 plugin 入口均拒絕 `--comp` 等縮寫，避免包裝層與執行層對操作範圍的解讀不同。

```powershell
# 整套專案安裝，先預覽，再套用
./feather-setup.exe install --project 'D:/work/my-project' --components all --scope project --entrance project --dry-run
./feather-setup.exe install --project 'D:/work/my-project' --components all --scope project --entrance project

# 只裝交接，不加入指引
./feather-setup.exe install --project 'D:/work/my-project' --components handoff --entrance none

# 共用角色；使用者入口僅在目前環境具備能力時適用
./feather-setup.exe install --project 'D:/work/my-project' --components delegation --scope user --entrance user

# 元件與入口範圍可分別選擇
./feather-setup.exe install --project 'D:/work/my-project' --components all --scope project --entrance user

# 狀態及可供程式處理的 UTF-8 JSON
./feather-setup.exe check --project 'D:/work/my-project' --components all --scope project --json
```

`--interactive` 可用於已有部分參數的命令；引導只詢問尚未指定的選項。`--json` 的結果在標準輸出，互動提示與預覽在標準錯誤。一般錯誤與衝突也提供 JSON 錯誤內容及下一步。成功退出為 0，錯誤／衝突／檢查需要處理為 1，參數錯誤為 2；取消為 0 並顯示 `cancelled`。選擇保留衝突內容以 1 結束，不會標記成已更新。

`check` 分開呈現元件／入口的檔案狀態與 `runtime` 環境健檢：檢查原生 Codex 版本、目前專案可見的 `agents.enabled` 設定及來源，以及角色必要欄位、身份衝突和鎖定模型／reasoning 的舊配置。使用者範圍角色也會核對指定專案的設定。未宣告 `enabled` 只表示未明確停用，不推定原生預設。找不到 Codex 時仍保留檔案檢查結果，並以需要處理的狀態結束。

健檢不修改配置、不登入，也不啟動模型任務。`session: unconfirmed` 提醒安裝、更新或遷移後需開新 session 確認能力已列出；`status: ok` 表示這些靜態檢查未發現問題，不證明技能已載入、帳號可使用指定模型、專案已信任或 sandbox 強制生效。

## 元件與入口位置

| 內容 | 專案範圍 | 使用者範圍 |
| --- | --- | --- |
| 五角色 | `<project>/.codex/agents/` | `<codex-home>/agents/` |
| handoff | `<project>/.agents/skills/handoff/` | `<user-home>/.agents/skills/handoff/` |
| 入口指引 | `<project>/AGENTS.override.md` 或 `AGENTS.md` | `<codex-home>/AGENTS.override.md` 或 `AGENTS.md` |
| 元件安裝紀錄 | `<project>/.feather/setup/state.json` | `<codex-home>/feather-setup/state.json` |
| 入口所有權紀錄 | `<project>/.feather/setup/entrances.json` | `<codex-home>/feather-setup/entrances.json` |

`user-home` 預設為執行安裝器的使用者 home；`codex-home` 預設採 `CODEX_HOME`，未設定時為 `<user-home>/.codex`。可用 `--user-home`、`--codex-home` 明確指定。兩個 home 不等同：修改 Codex home 不會改變使用者 skills 的位置。已存在的紀錄不能藉由換 home 參數改指另一個環境。

Windows 原生 Codex 使用 OS 使用者 profile 發現使用者 skills；覆寫 `HOME`／`USERPROFILE` 或傳入 `--user-home`，不會把該次原生 Codex 切換到另一個 OS profile。`--user-home` 可準備指定目錄，實際使用仍須以對應的 OS 使用者執行。Windows 與 WSL 是不同環境；WSL 應使用 Linux 發行包、Linux Codex 與 Linux home。

入口優先加入同目錄既有 `AGENTS.override.md`，否則用 `AGENTS.md`。安裝器只管理 `<!-- feather-setup:<component>:begin -->` 與 `end` 標記及紀錄中的相應區塊，保留其他文字、BOM 與換行。不加入口時不修改 Agent 指引。既有入口若需要改範圍，先移除該選用元件及其入口，再以新選項安裝；元件遷移也可明確指定入口範圍。

入口包含能力可用條件：使用者入口搭配專案元件時，不會要求其他沒有該元件的專案使用不存在的角色或 skill。多個安裝共用相同使用者入口時，移除單一安裝只解除自己的參照，最後一個參照解除後才移除區塊。

## 沿用與遷移

安裝會檢查目前專案、可見 repo 祖先及使用者範圍。新版 handoff 安裝在 `skills/handoff/`；舊版 `skills/feather-handoff/` 仍可辨識，遷移與清理依原所有權紀錄處理。發現完整的既有同名能力時沿用，摘要列出實際來源，不建立另一份。部份角色集合、異名檔案宣告相同角色，或多個可見同名集合會回報衝突。沿用表示找到了既有檔案，並不取得其所有權，也不證明 Codex 已載入。更新應指定真正擁有該元件的安裝範圍。

明確遷移範例：

```powershell
./feather-setup.exe migrate --project 'D:/work/my-project' --components all --from project --to user --dry-run
./feather-setup.exe migrate --project 'D:/work/my-project' --components all --from project --to user

# 回到專案元件，並明確將入口放在使用者範圍
./feather-setup.exe migrate --project 'D:/work/my-project' --components all --from user --to project --entrance user
```

來源、目的範圍必須不同。遷移保留來源元件版本與內容，使用較新的發行包也不順便更新；目的部署核對成功後才移除來源。未指定新入口時保留既有入口位置。從使用者範圍移出會改變其他專案可見的能力，摘要會列出這項影響。

遷移只接受已受管理且未手改的來源，目的同名内容也會阻止遷移。請先處理自訂內容與衝突；遷移不接受 `--on-conflict replace`。若使用者安裝曾管理另一個專案的入口，操作需以該原始專案路徑執行，避免暗中改寫其他專案。

Plugin 的自動計畫審查模式由 `$auto-on` 和 `$auto-off` 切換；session 不寫檔，project 或 user 才保存到既有安裝的狀態及受管理入口。預設 off；工具指令及兩次自動審查上限見 [審查模式](../skills/setup/references/auto-review.md)。舊版安裝器不具備此欄位的保留能力，更新前應使用支援的版本。

## 更新、衝突與移除

角色模型與推理強度由 plugin 的 `model` skill 引導修改：先列出現況，再選擇要改的欄位，最後決定 session 或永久。永久值記錄在角色擁有者的安裝狀態與受管理入口；此版安裝器在更新及遷移時保留設定。請使用含此功能的新版工具，舊版安裝器沒有保留這些設定的能力。模型設定不寫入角色 TOML，也不修改主 Agent 的模型。完整流程見 [README](../README.zh-TW.md#修改角色模型)。

下載並解壓新版完整包，再從新版包執行：

```powershell
./feather-setup.exe update --project 'D:/work/my-project' --components all --scope project --dry-run
./feather-setup.exe update --project 'D:/work/my-project' --components all --scope project

# 檢視衝突後，明確選擇以受管理元件的新內容替換；先備份
./feather-setup.exe update --project 'D:/work/my-project' --components delegation --on-conflict replace

# 保留衝突；整次操作不套用，退出非成功
./feather-setup.exe update --project 'D:/work/my-project' --components delegation --on-conflict keep

# 移除指定範圍內受管理的元件及其入口
./feather-setup.exe remove --project 'D:/work/my-project' --components handoff --scope project --dry-run
./feather-setup.exe remove --project 'D:/work/my-project' --components handoff --scope project
```

更新與移除先比對上次安裝內容；預設衝突即停止，列出目前修改與 proposed diff。`replace` 只允許處理有所有權紀錄的內容，不能強制接管來源不明的同名檔案。移除也支援明確的 `--on-conflict replace`，先備份再刪除手改的受管理內容。入口標記缺少、重複或範圍不明時，即使選 replace 也不任意刪除整份指引；須先整理標記或還原原區塊，再預覽操作。

不遞迴刪除元件目錄。額外檔案、未選元件、既有 Codex 設定、`.feather/handoffs/` 與交接歷史保持完整。空目錄、安裝紀錄和備份可能保留，供後續核對；不將「資料夾仍存在」視為元件仍可用。

## 復原與環境限制

寫入前會完成整體計畫與備份；多元件、入口及紀錄屬於同一次操作。備份放在此次操作的安裝紀錄旁 `backups/<id>/`。`journal.json` 對應每個原路徑與 `NNNN.bin` 原始內容；`before: null` 表示操作前不存在。不要把單一 `.bin` 的編號當成固定元件名稱。

一般寫入錯誤或操作中斷會嘗試還原。`recovery: rolled_back` 表示本次已套用的檔案變更已還原；`incomplete` 會列出 `remaining` 與備份位置。先停止其他寫入，逐項比對 journal、現況及備份，再恢復對應的原內容；不要覆寫操作後他人新增的修改。強制終止程序或斷電可能留下需要人工檢查的 journal，安裝器不宣稱這些情況已自動復原。備份建立本身失敗時不開始部署。

同一 OS 使用者同時執行重疊的安裝操作會被鎖定；等待先前程序結束後重試。互動預覽後若檔案變動，也需重新預覽，不能沿用先前確認。

找不到可用 Codex 時停止安裝；若 Codex 不在 PATH，可傳 `--codex` 指向原生執行檔。Windows 會另檢查 Codex app 的常見 `bin` 位置，不把 `.cmd`／`.ps1` shim 當成原生 `codex.exe`。不處理帳號或憑證。

安裝器不改主模型、reasoning、並行數或專案信任。未宣告 `agents.enabled` 時不為補預設值而改設定；偵測到明確 false 時回報，請先自行確認停用意圖。檔案安裝成功不等於所有 session 都會載入：專案信任、較深層指引、文件大小與設定優先序仍可能影響結果。重開 session 以載入新角色與 skills；實際驗證的版本、平台及限制見 [安裝器驗證紀錄](setup-validation.md)。

## 從來源建置

安裝器本身不需要 Python；執行交接 skill 的檔案工具需要 Python 3.11+（僅標準函式庫）。缺少或版本不符時，Agent 先詢問是否協助安裝；拒絕後仍可唯讀查閱，但不繞過工具寫入。`check` 會分別回報 Python 與 Codex 環境。維護者建置需要各平台原生 Python 3.11+ 與依賴。

```powershell
python -m pip install -r requirements-setup-dev.txt
python scripts/build_setup.py
```

在 Windows 建 Windows 包，在 Linux 建 Linux 包，不做跨平台假打包。輸出目錄必須尚不存在，可用 `--output` 指定新目錄。`--prepare-only` 只產生素材，供 `python scripts/feather_setup.py ... --bundle <素材目錄>` 開發用，不能當作無 Python 的發行包。`--bundle` 是進階素材來源選項；一般使用預設的執行檔所在完整包。
