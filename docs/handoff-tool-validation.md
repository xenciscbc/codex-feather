# 交接檔案工具驗收

## 2026-10-21：cc-feather v0.30.0 同步

來源固定為 cc-feather `03c9c24be6a9a60fca4037c9ccd3d0e77d0d85bd`，已透過遠端 HEAD 核對；前次基準為 v0.16.0 的 `da4948c53f72e0c198dcdc00dd8e48ef3a43c16d`。38 個上游來源檔的 SHA-256 與移植差異記錄於 [同步清單](cc-feather-handoff-manifest.json)。共享 runtime 保留既有 ctime／讀取前後一致性檢查，另補上 mypy 所需的型別標註與明確空值分支。

| 環境 | 命令／範圍 | 結果 |
| --- | --- | --- |
| Windows，Python 3.11.9 | `python -B -m unittest discover -s tests -p 'test_handoff_*.py'` | 型別修正後重跑 260 項，18 項略過，其餘通過；237.503 秒 |
| 同上 | `python -B -m unittest discover -s tests -p test_plugin_setup.py` | 28 項通過；73.083 秒 |
| 同上 | `python -B -m unittest discover -s tests -p test_snapshot_deployment.py -v` | 型別修正後重跑 2 項通過；5.034 秒 |
| 同上 | `python -B -m unittest discover -s tests -p test_handoff_encoding.py -v` | 1 項通過，含 cp950／cp1252 子案例；0.306 秒 |
| 同上 | 上游來源雜湊、Python AST、skill 相對連結及 `handoff-tidy` 明確呼叫 policy | 通過 |
| 同上 | `git diff --check` | 通過 |
| 同上，mypy 1.18.2 | `python -B -m mypy --check-untyped-defs skills/handoff/scripts scripts/setup_installer` | 30 個來源檔通過；使用專案既有 `.scratch/feather-improvements/dev-deps`，未另裝依賴 |

新增的上游回歸測試涵蓋 Git helper、完整 PATH 解析、promisor／lazy-fetch 防護、Git 無法啟動或逾時的 partial 復原、LF／CRLF／BOM 與 fenced ATX 標頭邊界，以及整理交接時先寫目標、連續更新目標、保留驗收限制與來源歸檔的公開 CLI 流程。既有 Codex ctime 回歸測試保留。原始記錄位於 `.scratch/cc-handoff-sync-v030-tests.log` 及 `.scratch/cc-handoff-sync-v030-plugin-tests.log`。

`handoff-tidy` 已改為 Codex 的 `agents/openai.yaml` 明確呼叫入口，沿用上游提案、核對、確認、版本比對與寫入次序，並保留 Codex 計畫審查記錄。原生 executor 與 analyst 已補完候選 skill 的操作演練：模式選擇、Proposal、Full check 的讀取確認邊界、Selected check、版本衝突後重新提案、確認寫回、部分保存與復原歸檔均通過主 Agent 驗收；來源、無關記錄及 Git metadata 不變。具體 session、產物及 CLI 環境限制見 [原生演練](handoff-live-validation.md#2026-10-21handoff-tidy-候選-skill-原生演練)。沒有更改已安裝的 plugin cache、發布版本或建立 tag。

## 2026-09-11：初版驗收

日期：2026-09-11。規格：[Feather 交接工具](../.scratch/feather-handoff-tool/spec.md)。

## 程式驗收

| 環境 | 命令／範圍 | 結果 |
| --- | --- | --- |
| Windows | `python -B -m unittest discover -s tests -q` | 145 項，通過，2 項略過 |
| Ubuntu / WSL，Python 3.12.3，x86_64 | 新增五個 `tests.test_handoff_*` 測試模組 | 31 項，通過，3 項 Windows 專用分享限制測試略過 |
| Windows | `mypy --check-untyped-defs skills/handoff/scripts scripts/setup_installer` | 25 個來源檔案通過 |

測試由公開 CLI 在隔離目錄實際執行，涵蓋建立、即時清單、舊格式與不完整讀取、人工內容保留、過時版本拒絕、完成後自動歸檔、相同身份重試／正文衝突、歷史篩選、指定清除及封存。完整 payload 經公開建置、安裝、更新、執行與移除；移除後原交接資料保留。Python 缺少、過舊、可用與 Windows launcher 參數以隔離 PATH 程序驗證，不修改使用者環境。

Windows 故障測試以外部程序持有真實檔案，阻止歷史替換或完成原檔刪除，確認可恢復副本及重試不重複追加。封存測試也實際阻止來源替換：目的檔已保存，來源保留；釋放限制後重用相同目的及身份。另驗證完成原檔尚在時首次封存及重試都延後，歸檔收尾後才封存。

檔案產物與這些外部故障能支持相應的保存／移除順序；未逐次攔截所有系統呼叫，不宣稱為所有故障位置的完整事件追蹤。沒有鎖定或未協調跨 session 並行安全保證。

## 實際 Agent 操作

獨立 executor 在 `.scratch/feather-handoff-tool/live-smoke/` 建立隔離 Git 專案，讀取本次 skill，透過工具建立摘要、查閱原檔、核對設定來源、更新、驗證過時版本拒絕、完成後自動歸檔、查詢並封存明確選定身份。保留九份原始 JSON、報告及唯讀前後 SHA-256 記錄。

摘要保留 `port=7319`、`readiness_path=/ready`、`timeout=UNDECIDED`，沒有把設定核對寫成 runtime 測試成功。完成狀態只表示隔離交接演練完成。另一份明確建立的損壞 fixture 讓清單回報 partial；Agent 未據此自動選取唯一工作，未修復或執行 `DO_NOT_EXECUTE`。所有有效受管理交接寫入使用 CLI；fixture 與驗收報告的直接寫入另行限定。

這是本次原生子 Agent 的操作證據，不是離線測試產物推定。dispatch 配置為 executor / gpt-5.6-sol / medium；未提供每回合 backend telemetry，實際執行模型保持未確認。未另外進行真實缺少 Python 時與使用者互動同意／拒絕安裝的演練；此部分只有環境診斷測試及 skill 指引證據。沒有建置或發布新的二進位發行包。

## 兩軸審查

Standards 與 Spec 由獨立 analyst 檢查；主 Agent 整合修正並保留來源。Standards 發現自由文字翻譯指引未排除固定狀態值，以及 `py` 探測未使用文件的 `-3`；已修正並驗證實際 launcher 參數。

Spec 發現標題內分隔文字會阻擋歸檔、標題前內容未標示問題、清除失敗缺少恢復狀態、空封存目錄誤判不存在；四項均先加入會失敗的公開測試再修正。後續重跑受影響的 28 項工具測試與 6 項環境測試通過，型別檢查維持 25 檔通過；全套 145 項數字是修正前完整回歸的紀錄，沒有拿新增測試數量冒充重跑全套。Standards 與 Spec 複查後各為 0 項未解決。

最後另外匯出實際暫存提交內容，在沒有其他未提交修改的副本驗證：28 項工具測試及 6 項安裝環境測試通過。安裝驗收使用 Windows 專案磁碟的隔離目錄；RAM 暫存磁碟不支援既有安裝器的路徑查核，未列為支援平台。

## d516c9d 後續審查修正

修正四項重現問題：詳細紀錄更新誤刪同前綴的獨立區段、CRLF 更新產生重複回車、歸檔重試錯把額外換行視為相同正文，以及 Git 追蹤設定失敗未回報已保存的交接。

管理區段現在以後續 H1/H2 為邊界，重複的精確管理標題要求明確整理；連續兩次 LF/CRLF 更新都保留人工補充。歸檔與封存共用正文比較，只在原正文缺少結尾 LF 且確有後續歷史條目時允許分隔換行。Git 追蹤失敗回傳 partial、交接位置、保存版本、目前可讀版本、觀察到的狀態與恢復指引。

新增六項公開回歸測試。Windows 完整測試 `python -B -m unittest discover -s tests -q`：154 項通過（略過 2）；WSL/Ubuntu 相關 27 項測試通過（略過 3 項 Windows 專用分享限制測試），mypy 25 個來源檔案通過。Standards 與 Spec 對這四項修正複查，各為 0 項未解決。
