# feather-setup 驗證紀錄

## 重建發行包（2026-09-09）

新版輸出至 `dist/2026-09-09/`，版本沿用 0.1.0，以日期目錄區分本次重建。`dist/` 根目錄的舊包保留，仍符合原有 SHA-256。本次使用目前工作目錄來源，包含新版交接搜尋／封存規則與環境健檢；每包 `bundle.json` 記錄 6 份素材與 16 份安裝器／建置來源雜湊，兩平台的素材及來源雜湊完全一致。

| 驗收 | 結果 |
| --- | --- |
| Windows 原生建置 | Python 3.11.9、PyInstaller 6.16.0，完整 ZIP 含內附 runtime |
| Linux 原生建置 | Ubuntu／WSL2 x86_64、Python 3.12.3、PyInstaller 6.16.0、glibc 2.39，完整 tar.gz |
| Windows ZIP 解壓驗收 | 59 項：45 通過、14 條件略過，61.854 秒 |
| Linux tar.gz 解壓驗收 | 59 項：46 通過、13 條件略過，196.014 秒 |
| 兩平台真實舊包升級 | 舊包安裝 → 解壓後新包 update → check，均通過；部署素材與新版 manifest 一致，使用者檔案保留 |
| 包內容與校驗 | 壓縮包 SHA-256、解壓內容、素材與來源雜湊核對通過；Linux 可執行權限保留 |

兩平台均包含無 Python PATH 的獨立執行檔驗收。13 個略過為來源 OS 呼叫適配測試，已由來源回歸執行；Windows 另略過需要明確 OS profile 的使用者 skill 探測，本次未另行執行，不能算成通過。WSL 啟動時回報 Mirrored 網路模式失敗並回退，但原生建置、本地端點探測與整套驗收均完成。

驗收後只更新包內 `docs/setup.md` 與本紀錄，重新封裝並產生 `.sha256`；執行檔、runtime、manifest 與素材逐檔比對解壓驗收版本，保留已測試內容。原始日誌、解壓內容、升級結果及核對腳本在 `.scratch/feather-setup/build/rebuild-20260909/`。

本次沒有發布至外部下載站、更新使用者既有安裝或重跑真實模型跨 session 測試；Linux 相容性仍限上述已測環境。

## 環境健檢補強（2026-09-09）

目前 Windows 來源完整回歸 98 項：96 通過、2 條件略過；略過項為獨立發行包入口與需要明確測試 profile 的 Windows 使用者技能探測。完整回歸發現既有 trial 測試讀取器的編碼例外，修正為 UTF-8 後相關 16 項重新通過。mypy 1.18.2 的 16 個安裝器／建置來源檔通過，skill quick_validate 通過，prepare-only 素材包建置通過。

`check` 新增環境輸出，已透過公開 CLI 驗證：使用者角色搭配專案停用設定、由專案沿用使用者角色、較深設定覆寫、非法 enabled 類型、Codex 執行檔不存在、沿用角色鎖定派工模型及異名角色身份衝突。對設定與元件檔案做前後內容比對，健檢保持唯讀；找不到 Codex 仍回報既有元件的檔案證據。完整集合可用時維持正常退出，需要處理時退出 1。

本階段為來源及隔離素材驗證，沒有以 `session: unconfirmed` 假定載入成功、驗證帳號模型資格或 sandbox 強制生效。其後已完成同日重建，詳見上方紀錄；較早 Windows／Linux 包與下列舊版紀錄維持原樣。

後續真實使用驗收：最終 Windows 包已安裝至另一個 Codex 專案，四個全新 app session 的交接／歷史流程通過，詳見 [跨專案新 session 實測](handoff-live-validation.md)。此補驗未修改已交付壓縮包。

對應規格：[Feather 獨立安裝器](../.scratch/feather-setup/spec.md)，實作票券 01–08。驗收由公開 CLI／互動输入出發，比對退出結果、摘要、原始檔案與設定，不以內部函式名稱作為正確性證據。

## 實測環境

| 項目 | Windows | Linux |
| --- | --- | --- |
| 原生環境 | Windows x64，build 26100 | Ubuntu x86_64／WSL2，kernel 6.6.114.1 |
| 建置 Python | 3.11.9 | 3.12.3 |
| 打包工具 | PyInstaller 6.16.0 | PyInstaller 6.16.0 |
| libc | 不適用 | glibc 2.39 |
| Codex 原生版本 | codex-cli 0.153.4 | codex-cli 0.153.4 |

Linux 發行包使用上述原生 Linux Python 與共享函式庫建置，實際在 WSL2 的 Linux 執行。未驗證其他發行版、較舊 glibc、musl 或非 WSL 主機，不將本次結果當作 Linux 最低系統版本保證。尚未推定 Codex 最低支援版本。macOS、ARM64 不屬第一版範圍。

## 檔案操作與原生載入是兩類證據

`tests/test_setup.py` 透過隔離專案、user-home、Codex home 與本地素材測試安裝器，成功與失敗路徑包括：

- 任務分工／交接／整套，專案／使用者範圍，以及 12 種元件與入口的範圍組合。
- 無入口、一般 AGENTS、override、BOM／CRLF 保留、重跑、混合範圍、共用入口參照、後續新增 override 的遮蔽回報。
- 自訂模型／reasoning／並行設定保持原樣；明確停用 agents 時不改設定；repo 祖先同名元件及角色宣告名稱衝突。
- 新版更新、未選元件保留、移除過時素材、手動修改差異、保留／替換與原始內容備份。
- 選擇性移除、交接檔與歷史保留、額外檔案及後來新增的非受管理內容保留。
- 雙向遷移、來源版本保留、目的同名衝突、入口保持原範圍或明確移動。
- 元件、入口、來源移除與紀錄寫入失敗，以及復原再次失敗時的剩餘檔案與備份回報。
- 互動預覽、取消、更新衝突、沿用或明確遷移、完整命令不多問；預覽後手改停止套用；兩個重疊安裝程序不互相覆寫紀錄。
- 不完整／校驗碼錯誤／越界／大小寫別名的素材包在部署前停止。

故障注入只替換測試子程序的外部 OS 檔案呼叫，再執行公開來源 CLI；正式安裝器沒有測試後門。這些測試在發行包模式有明確 skip，來源模式則實際執行。獨立發行包另在 `PATH` 無 Python 且 `PYTHONHOME` 指向不存在位置的情況啟動，使用內附 runtime。

原生證據由 `tests/setup_native.py` 及 Codex `debug prompt-input` 取得：

- 專案 handoff 的 skill-root 別名對應到實際部署的 `SKILL.md`，並載入專案 override 入口。
- 受信任隔離專案四角色進入 Codex 原生工具註冊。
- 使用者角色與 skill、使用者入口搭配專案元件，以及沒有元件的另一專案中仍帶有能力條件的入口。
- 更新後的使用者角色描述及專案入口新增內容。
- 兩個方向遷移後的角色註冊、skill 真實位置與入口。

角色探測將 Codex 導向本機 HTTP 測試端點，捕捉實際組成的工具註冊請求後立即回覆測試錯誤；不呼叫真實模型、不登入、不複製真實憑證。這能證明原生角色／skill／指引的發現與註冊，不能證明模型實際遵守分工、角色模型綁定或 reasoning 執行。這些屬既有的 [分工原生驗證](native-compatibility.md) 範圍。

專案角色需符合 Codex 信任條件。只有測試自己建立的隔離 Codex home 會加入隔離專案的 trust 設定；安裝器本身不改信任。文件大小、深層覆寫和其他有效設定仍可能影響載入，不能把檔案狀態 `installed` 當成原生啟用保證。

Windows 原生使用者 skill 探測不能靠 `HOME`／`USERPROFILE` 覆寫隔離。一般測試明確略過該項；另以實際 OS profile、隔離 Codex home 及臨時 `feather-handoff` skill 執行。僅在同名 skill 原本不存在時開始，完成後比對原始內容再刪除剛建立的 skill，既有使用者資料保持原樣。Linux 可直接使用隔離 home 驗證。

## 重現方式

來源 CLI：

```powershell
python -m unittest discover -s tests -p test_setup.py
python -m mypy --check-untyped-defs scripts/setup_installer scripts/feather_setup.py scripts/build_setup.py
```

Windows 發行包：

```powershell
$env:FEATHER_TEST_INSTALLER = (Resolve-Path 'dist/feather-setup-0.1.0-windows-x64/feather-setup.exe').Path
$env:FEATHER_TEST_CODEX = 'C:/path/to/native/codex.exe'
python -m unittest discover -s tests -p test_setup.py
```

Linux 發行包：

```bash
FEATHER_TEST_INSTALLER="$PWD/dist/feather-setup-0.1.0-linux-x64/feather-setup" \
FEATHER_TEST_CODEX="$HOME/.local/bin/codex" \
python3 -m unittest discover -s tests -p test_setup.py
```

Windows OS profile 的獨立探測：在乾淨測試使用者環境，明確設定 `FEATHER_TEST_WINDOWS_PROFILE` 為該 OS profile 後，只執行 `-k native_codex_discovers_user`。若原本已有同名 skill，测试跳過並保留；跳過不能記為原生通過。

完整專案回歸使用 `python -m unittest discover -s tests`。安裝器程式碼另執行 mypy；既有試用工具的 compileall 僅屬語法檢查。

## 審查前验收結果

| 驗收 | 結果 |
| --- | --- |
| Windows 完整專案來源回歸 | 88 項，通過；2 項條件略過 |
| Windows 安裝器來源情境 | 51 項，通過；2 項條件略過；後增無參數啟動已含在完整回歸 |
| Linux 安裝器來源情境 | 51 項，通過；1 項獨立執行檔限定略過 |
| Windows 發行候選包 | 52 項，通過；12 項略過（11 項來源 OS 呼叫適配、1 項 OS profile 獨立探測） |
| Linux 發行候選包 | 52 項，通過；11 項來源 OS 呼叫適配略過 |
| Windows 發行候選包 OS profile 原生探測 | 1 項通過，含整套雙向遷移；測後確認臨時 skill 不存在 |
| 安裝器 mypy | 15 個來源檔通過 |

這些結果不把 skip 當作通過。來源 OS 故障情境已由來源回歸實際執行；一般 Windows 測試略過的使用者 skill 項目另行實測。各票券 Answer 保存較早階段的驗收結果。

## 最終交付驗收（2026-09-08）

安裝器來源為 `e8e8606`。Standards 與 Spec 獨立審查均無剩餘發現；已修正規劃期間的手動編輯保護，以及不同目錄宣告同名 skill 和遷移來源別名的碰撞檢查。

| 驗收 | 結果 |
| --- | --- |
| Windows 完整來源回歸 | 92 項：90 通過、2 條件略過，123.926 秒 |
| Linux 安裝器來源 | 審查修正後 55 項：54 通過、1 略過；最後新增遷移別名回歸另 1 項通過 |
| Windows 最終 ZIP 解壓驗收 | 56 項：42 通過、14 略過，89.160 秒 |
| Linux 最終 tar.gz 解壓驗收 | 56 項：43 通過、13 略過，248.150 秒 |
| Windows 最終包 OS profile 原生探測 | 1 項通過，9.558 秒；含整套雙向遷移，測後臨時 skill 已清除 |
| mypy | 15 個安裝器來源檔通過 |

發行包模式的 13 項略過為來源程序 OS 呼叫適配測試，來源回歸已實際執行；Windows 另略過的 OS profile 探測已獨立通過。兩平台皆驗證無 Python PATH 的啟動。原生 Codex 載入證據與平台限制同前述。

交付檔位於 `dist/`，每個壓縮包旁附 SHA-256。壓縮包內文件於驗收後補入本紀錄；執行檔與素材保持已驗收位元組。`bundle.json` 的 `build.source_hashes` 對應安裝器來源，兩平台素材雜湊相同。建置使用現有工作目錄素材（包含先前未提交的模板修改），因此 `tracked_worktree_changes` 為 true；這些既有修改未納入安裝器提交。重建同一素材需以 manifest 雜湊核對工作目錄，不能只憑 commit 假設素材相同。
