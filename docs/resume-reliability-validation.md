# 接續可靠性實作與驗證（2026-09-12）

來源基準、唯讀比對、五項子任務回傳及有界收回已實作；最後兩輪審查找到的程式問題均已修正。完整原生驗收仍保留未確認項，不能把下列成果測試等同全部派工行為通過。

## 自動化結果

| 平台／範圍 | 命令 | 結果 |
| --- | --- | --- |
| Windows，Python 3.11.9，全套 | `python -B -m unittest discover -s tests` | 190 tests，OK，3 skipped；158.296 秒 |
| Windows，最終部署測試 | `python -B -m unittest discover -s tests -p test_snapshot_deployment.py` | 2 tests，OK；4.734 秒 |
| Ubuntu WSL，Python 3.12.3，交接回歸 | `FEATHER_TEST_CODEX=/home/cbc/.local/bin/codex python3 -B -m unittest discover -s tests -p 'test_handoff*.py'` | 94 tests，OK，3 skipped；124.511 秒 |
| Ubuntu WSL，部署 | `FEATHER_TEST_CODEX=/home/cbc/.local/bin/codex python3 -B -m unittest discover -s tests -p test_snapshot_deployment.py` | 2 tests，OK；34.687 秒 |

全套啟動後新增一項不依賴 Codex 的 payload 測試，因此最終 discovery 是 191 項；該新增項已包含在後續 Windows 與 Linux 的兩項部署測試。沒有把兩次測試數字相加冒稱全套重跑。

部署測試實際建立 bundle，核對候選來源，安裝、保存基準、修改來源、更新、比對、check、移除，再確認交接原始 bytes 保留。Windows 與 Linux 均使用原生 Codex 0.153.4；初次沿用 Windows PATH shim 的 Linux 環境測試失敗後，改用 `FEATHER_TEST_CODEX` 指向 Linux 原生執行檔，最終回歸通過。部署結果是隔離專案實測，不代表已更新使用者的安裝。

平台限定 skip 保留；Windows symlink 能力與原生 profile/standalone release 等條件測試不能由 suite 的 OK 推論通過。Linux 的 snapshot symlink 案例另有實測，不能取代 Windows reparse 實際環境驗證。

## 原生子任務與成果核對

本輪使用目前主 session 的原生子 Agent，並在 `.scratch/feather-resume-reliability/native/` 的隔離素材上執行。不是新 session 自動探索技能的 smoke run。

| 情境 | 主 Agent 獨立成果驗證 | 行為／證據限制 |
| --- | --- | --- |
| `read-final` | `trial.py verify` pass，workspace 無改檔 | 子任務回報只用 list/read，沒有 compare 或執行下一步 |
| `resume-final` | pass，只改 readiness.txt 與交接檔，現在值 `/ready`、保留有效基準與 pending timeout | 子任務回報 read → compare changed → 讀現行設定 → update；沒有把歷史測試聲明當成現行結果 |
| `partial-final` | pass，保留 evidence.bin 未知限制、有效基準與 pending timeout | compare partial，未知基準仍 unknown；獨立 readiness 工作完成 |
| `returns` | pass，只改兩份 READY 與 retry.py，工程函式行為通過 | 四角色與 generic 回傳、缺理由 completed 拒收與補正有當次觀察及 answer 摘要；未保存可獨立重播的完整事件輸出 |
| `reclaim-ready` | pass，只改 attempts.txt=2 與 PARTIAL | 當次觀察兩次相同依賴失敗後收回；目前持久產物不能單獨證明停止時序及所有權移交 |

兩個分工情境的 `review.json` 保持 `behavior: unconfirmed`，避免由手填摘要或檔案值推論原生行為。後續完整驗收需使用明確啟用的 smoke 流程保存原生事件，逐項核對回傳、拒收、重試與停止後移交，才能關閉工作票 06。新 session 的技能自動載入、每回應實際模型／reasoning 與強制 sandbox 隔離均未由本輪證明。

請求設定依 AGENTS 預設：scout luna/low、analyst sol/medium、mech-executor luna/medium、executor sol/medium；generic 不傳覆寫並繼承完整上下文。這些是派工設定，不是後端實際執行模型的 telemetry。

原生 Windows 寫入遇到預設 token 的 PermissionError。舊 trial 揭露暫存檔建立重試過久，已終止其指定程序後修復並使用新 trial；失敗目錄保留，不計成功。最終 trial 確認預設寫入立即回報錯誤，精確授權提升後更新成功並讀回；沒有修改 ACL 或 sandbox 配置。因此可確認錯誤不再卡住，但不能宣稱預設 sandbox 寫入能力已通過。

## 審查修正

主 Agent 整合與修復，兩個 analyst 分別審查來源邏輯及模板／驗收契約；選用 analyst 是因為需要獨立因果與契約分析。最終來源審查為 APPROVE，沒有其餘可重現的 P0/P1/P2 程式問題。

| 問題 | 修正及證據 |
| --- | --- |
| Git ownership 檢查與 snapshot 觀察不一致 | 僅單次 Git 命令設定明確專案 safe.directory，不修改全域配置 |
| unknown 來源消耗保存重驗額度 | 僅重驗已知 present/missing，unknown 保留；回歸測試覆蓋 |
| details 更新可能覆寫基準、相似標題遭誤判 | 基準與 details 互斥驗證、精確標題與相鄰文字保留；回歸覆蓋 |
| PermissionError 觸發 Windows tempfile 超長重試 | 獨占建立暫存檔、碰撞上限 3 次、權限錯誤立即返回；4 項 storage 測試含碰撞與 Git 路由 |
| 繼承的 GIT_DIR/GIT_WORK_TREE 導向另一專案 | 共用 Git 環境清理，套用 root discovery、snapshot、tracking；雙 repo 回歸 |
| 不合法 backtick opener 隱藏基準 | fence parser 遵守 backtick info string 限制，測試確認真區塊可讀且重複拒絕 |
| 無 Codex 時連 payload 檢查都 skip | 拆出永不因缺 Codex 而 skip 的來源完整性測試，兩平台通過 |
| 原生證據不足卻可能標整體完成 | 將產物通過與原生行為未確認分開，06 維持未完成 |

`git diff --check` 通過。工作開始時已有其他未提交修改，未回退或把那些修改列成本輪成果；未提交 commit，也未更新使用者的全域安裝。
