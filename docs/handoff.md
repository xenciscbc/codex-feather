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

各情境名稱與原生回覆验收準則可從 prepare 的 `--help` 及產生的 `review.json` 查閱。實際驗收結果見 [交接驗收紀錄](handoff-validation.md)。
