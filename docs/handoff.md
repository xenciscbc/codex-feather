# Feather 交接

`feather-handoff` 讓同一專案的新 session 從精簡 Markdown 接續工作。產品位於 `skills/feather-handoff/`；手動把整個目錄放入你使用的技能目錄，再於新 session 呼叫。這次交付不安裝到個人設定，也不插入專案 AGENTS.md 入口；入口設定留給另行設計的 `feather-setup`。

例如：

> 用 feather-handoff 交接 config-audit。已核對 port，還沒跑測試，下一步核對 readiness。

第一次明確要求才建立 `.feather/handoffs/<工作名稱>.md`。同一項工作更新同一份檔案，在重要進展或受阻時記下目標、具體進度與驗證結果、下一步及必要限制。不需要保留整段對話。

交接資料預設被 Git 忽略；若你指定要追蹤，或原本就已追蹤，skill 會尊重這個選擇，不自行暫存或提交。非 Git 專案也可使用。新 session 要使用同一份專案目錄，跨 worktree 的檔案同步由使用者處理。

## 在新 session 接續

> 用 feather-handoff 讀取 config-audit 的交接，上次做到哪？

這會只回報狀態。若要繼續執行，說：

> 用 feather-handoff 接續上次工作。

只有一項未完成工作時直接選取；多項且無法辨識時會列出名稱詢問。接續前先核對相關檔案，修正過時資訊，再執行下一步。一般查閱不改寫檔案，接續也不會自動讀共同歷史。

## 從 Claude memory 查找交接

> 用 feather-handoff 從 Claude memory 目錄 `C:/Users/me/.claude/projects/my-project/memory` 找出交接記錄，只讀取並摘要。

也可以指定專案，讓 Agent 定位來源：

> 用 feather-handoff 從專案 `D:/work/my-service` 的 Claude memory 找出交接記錄。

定位會核對實際設定、自訂記憶位置與 Git repository／worktree 關係；非 Git 專案也可使用。有效設定有正常優先序時直接採用，不把低優先序的舊值當成另一個搜尋來源。若仍有多個合理候選，先列出路徑與依據讓你選；找不到時回報檢查範圍，你也能直接提供 memory 目錄。目錄名稱編碼與設定行為會隨 Claude 版本核對，不只靠字元替換猜路徑。

這個入口需明確指定 Claude memory；一般「讀取交接」仍查 Feather 的交接檔，沒有待辦也不會自動改查其他來源。指定目錄後會搜尋其中的 Markdown，包含索引未列出的筆記，依內容區分明確交接、疑似交接與一般記憶。

結果會列出所有符合項目的工作名稱、判斷理由、未完成／已完成／不明狀態、可定位原文的來源，以及已記載的目標、進度、下一步與限制。缺少的內容如實標示，矛盾記錄保留各自來源，不依時間替你選定工作。找不到目錄、沒有符合內容與搜尋不完整會分別回報。

若同時提供明確 memory 目錄與專案根目錄，或由專案定位取得 memory，會讀取 memory 明確連結、且解析後實際位於該專案內的 Markdown 交接檔。例如：

> 用 feather-handoff 從 memory 目錄 `D:/work/my-service-memory` 找交接，專案範圍是 `D:/work/my-service`；同專案交接連結也納入摘要。

相對路徑會連同符號連結或 reparse point 的父目錄一起解析後才判斷範圍。同一目標被重複引用只讀取並回報一次；交接檔連回 memory 時不會循環，也不會繼續跟隨交接檔裡的其他連結或遍歷專案。跨專案檔案與網頁只列出來源。失效、不可讀或內容並非交接的連結會分別說明，不妨礙回報其他可讀項目；讀取失敗造成範圍未完整時會明確標示。

只提供 memory 而無法確認專案關聯時，仍完整搜尋 memory，但目錄外連結只列出並說明缺少專案範圍。查找全程唯讀，不匯入 Feather、不修改來源，也不執行記錄中的下一步或來源要求擴大範圍的指令。

## 完成與歷史

整項工作完成時，最後交接內容會追加到共同的 `.feather/handoffs/history.md`，以工作名稱與完成時間分隔。確認完整保存後才移除原交接檔。若中途失敗，會留下可恢復資料並回報；重試沿用同一次完成時間，已保存的內容不再追加。

共同歷史持續保留。歷史位置有既有目錄或無法讀寫時，skill 會保留原交接檔並回報阻礙；不會替換既有資料來強行完成。

> 用 feather-handoff 查閱 config-audit 的歷史。

> 用 feather-handoff 只清除 config-audit 在指定完成時間的那筆歷史，其餘保留。

查閱只回報；清除必須由你明確要求，範圍不清楚時會先詢問。清除全部共同歷史也不會移除未完成工作的交接檔。已清楚指定範圍時直接處理，不再重複確認。

## 驗收

沿用現有隔離入口，素材、候選 skill 與驗收結果各自保存。以下只準備素材與檢查，不送出模型任務：

```powershell
python scripts/trial.py prepare .scratch/feather-handoff/runs/my-create --scenario handoff-create
python scripts/trial.py check .scratch/feather-handoff/runs/my-create
```

候選 skill 複製到隔離 home，fixture 的專案指令維持原樣。执行該目錄的 `prompt.txt` 後，以相同入口驗證：

```powershell
python scripts/trial.py verify .scratch/feather-handoff/runs/my-create
python -m unittest discover -s tests -p test_handoff_trial.py
```

新情境延伸同一個使用者指令 → 實際操作 → 回覆與產物的驗收邊界。`artifacts: pass` 只代表已知資料与寫入範圍通過，不能證明 skill 正確觸發、沒有讀歷史、執行前核對過現況或保存後才移除；這些需查閱原生操作證據。

若使用原生 CLI 的 `smoke`，沿用 README 的隔離登入及明確啟用方式，同時提供 `--enable-live`、`--main-model`、`--main-reasoning`。準備全新目錄重試，保留原始證據，不把靜態檢查或手填驗收欄位當成模型行為已通過。

`handoff-archive-remove-failure` 是故障注入情境：在 Windows 另一個測試程序以 .NET `File.Open`、唯讀存取及 `FileShare.Read` 持有 fixture 原交接檔，於測試完成後釋放。預期歷史保存成功、移除原檔被系統拒絕，兩份可恢復內容都保留。未設定這個外部故障時，不應用該情境宣稱測過移除失敗。`handoff-archive-failure` 則直接以歷史位置的既有目錄驗證阻礙處理。

`handoff-clear-failure` 用相同方式持有共同歷史檔，驗證清除失敗後回報原狀。Git 情境另外保存 index 內容及其他 Git metadata 的基準，容許唯讀查詢更新 index 的 stat 快取，但不允許改變暫存內容或其他 Git 設定。缺少新版 metadata 基準的舊試用需重新 prepare。

Claude memory 情境也使用同一入口：基本搜尋包含 `claude-memory-direct`、`claude-memory-mixed`、`claude-memory-empty`、`claude-memory-missing`、`claude-memory-no-request` 與 `claude-memory-partial`；連結範圍包含 `claude-memory-links`、`claude-memory-links-unknown`、`claude-memory-links-alias` 與定位後接續連結的 `claude-memory-project-links`。離線核對器測試為 `python -m unittest discover -s tests -p test_claude_memory_trial.py` 及 `python -m unittest discover -s tests -p test_claude_memory_links.py`。每次先 prepare 新目錄，執行其中 prompt 後保存原生最終回覆為 `answer.md`，再 verify；沒有回覆會拒絕驗收。

這些情境要求每項工作一個 Markdown 標題並附來源連結，讓核對器可檢查已知工作、具体值與來源是否遺漏。這是隔離試用的回覆要求，不是產品輸出格式；判斷理由、狀態語意、是否完整搜尋及實際讀取範圍仍須核對原生操作與回覆。`artifacts: pass` 不會把 `actual: unconfirmed` 改成已確認。

`claude-memory-partial` 需在原生試跑期間對隔離 `memory/locked.md` 施加真實讀取拒絕；Windows 可用另一程序以 `FileShare.None` 持有唯讀串流，驗收檔案雜湊前先釋放。沒有施加並觀察到該故障時，只能稱為核對器測試，不算讀取失敗的行為驗證。

`claude-memory-links-alias` 會建立指向專案外的目錄連結，並另外保存連結身份；因此即使替換後的目標檔案位元完全相同，`check` 也會拒絕。平台不允許建立該 symlink／reparse fixture 時，prepare 會明確回報情境未建立，測試也應標示跳過，不能宣稱通過別名越界行為。

`claude-memory-project-non-git` 必須在 Git repository 外的暫存目錄 prepare，否則素材實際上會成為外層 repository 的子目錄，入口會拒絕。專案定位的其他情境名稱與原生回覆驗收準則可從 prepare 的 `--help` 及產生的 `review.json` 查閱。Claude memory 的實際結果見 [外部交接驗收紀錄](claude-memory-validation.md)；既有 Feather 行為見 [交接驗收紀錄](handoff-validation.md)。
