# 短名稱、計畫審查與安全實作角色驗證

日期：2026-09-23。此次只移植來源、文件與測試，未修改使用者的已安裝設定，未 commit、tag 或 push。既有 v1.2.1 的共用入口升級修正保留。cc-feather 僅作唯讀參考。

## 實作

- 技能改為 `handoff`、`setup`、`model`，另新增 `auto-on`、`auto-off`。Codex 原生介面可加上 `codex-feather:` plugin 命名空間；原生角色名稱不加此前綴。
- 新增 `security-executor`（workspace-write；預設 gpt-6-sol/high），其餘模型／推理預設保持原值。安全分析與計畫審查仍由 analyst 處理。
- 自動審查預設 off；session 開關只存於對話。明確 project/user 開關以既有 setup 紀錄及同範圍入口進行預覽、plan ID 核對、交易寫入和讀回。已保存 review_mode 隨更新與遷移保留。僅沿用全域角色但擁有專案入口的 setup 可保存獨立專案政策。
- 指引要求實質風險觸發 fresh-context analyst、每邏輯計畫至多兩次自動呼叫（包括協定失敗），保存阻礙與輪數；換 session、模式、模型或名稱不重置。READY 接續既有授權，第二次仍有阻礙時停止依賴該計畫的實作。這是指引式流程，沒有 hook 計數器。
- 獨立舊版 handoff 更新會在同一交易內搬到短名稱位置並更新管理入口；自訂內容衝突保留，明確替換才覆寫並備份。舊名稱移除／遷移與四角色升級均有回歸測試。管理 state、marker 命名空間保持相容。
- `.feather/handoffs`、歷史、封存與基準格式不變；交接核心 11 個 Python 模組與移植前 HEAD 逐位元相同。

## 驗證

| 檢查 | 結果 |
| --- | --- |
| Windows `python -B -m unittest discover -s tests` | 245 項完成，242 通過、3 略過 |
| mypy：setup_installer、setup/review/build 入口與兩個 skill script | 22 個來源檔案通過；既有未標註函式仍不是 strict 檢查 |
| 五個 skills 的 quick_validate（Python UTF-8 模式） | 全數通過 |
| Ubuntu WSL `test_review_settings.py` | 6/6 通過 |
| Windows 與 Ubuntu WSL `test_transaction_modes.py` | 各 2/2 通過 |
| 離線 payload 建立、checksum 與 Bundle.read | 24 個 assets、五角色、短名稱 handoff 通過 |
| 原生 CLI 隔離 local marketplace 安裝與 `debug prompt-input` | 五個技能均載入；沒有送出模型工作 |
| `git diff --check` | 通過 |

完整回歸日誌位於本機忽略目錄 `dist/port-validation-20260923/final-regression.log`。該目錄的 `native-*` 子目錄保留隔離 plugin 安裝、prompt 與 verification.json 證據。完整套件包含既有交接／基準／歷史測試，以及原生五角色註冊檢查。

測試曾找出兩個問題並修正：舊版偵測不再為了檢查存在而提早讀入內容，保持編輯器競態測試的驗證時點；模型表格解析與寫回支援 CRLF 並保留原換行。新增 CRLF 回歸後重跑完整測試通過。

Codex 的原子寫入原本即先 chmod 暫存檔再 replace，回滾也使用原 mode；因此保留實作，新增 chmod 失敗不發布及回滾 mode 的 Windows／Linux 測試。

## 指引試讀與限制

獨立 fresh-context analyst 試讀 session typo fix、兩次未解／協定失敗、新 session、任務與 session 模型優先序、project 沿用 user 角色、安全分析／實作區別及 READY 後繼續等七種請求。結果符合預期；專案沿用角色但自有入口的政策範圍已補明，先前輪數未知時明確要求重建證據而非假定歸零。

兩位 executor 分別處理安裝相容性與技能／文件（原生請求 gpt-6-sol/medium），analyst 進行指引試讀（gpt-6-sol/high）；主 Agent 驗收變更、整合工具並執行回歸。這些是設定與工具呼叫證據，沒有服務端逐回應模型 telemetry。

未重建獨立二進位發行包、未發布 plugin 或修改真實全域安裝，亦未驗證真實模型執行 security-executor。技能載入、角色註冊及離線試讀不等於對所有未來 Agent 行為的強制保證。永久政策要求可驗證、同範圍、單一擁有者的管理入口；共享或跨範圍入口先透過 setup 解決。
