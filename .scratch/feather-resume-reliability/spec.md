# Feather 下一版：接續變更比對與子任務回傳約定

Status: ready-for-agent

2026-09-12。使用者已依本規劃指示「開始實作」。本文件定義行為契約，完成狀態與驗證證據見 [map.md](map.md)，不以規格存在代表功能已驗收。

## 目標

1. 新 session 能辨認交接保存後相關來源的變動，避免沿用過時結論。
2. 主 Agent 能驗收子任務，並在阻塞或重派時沿用已有證據。
3. 保持 Feather 輕量：使用既有 Markdown、Python 標準函式庫與原生派工工具。

使用者可直接說「接續登入功能」；Agent 先回報必要差異，再執行目前已授權的工作。分工過程的格式主要供父子 Agent 使用，對使用者仍以結果與必要限制為主。

## 現況與設計依據

- [交接 skill](../../skills/feather-handoff/SKILL.md) 已有環境、驗證、決策欄位與接續核對規則；本版將部分核對工具化。
- [寫入工具](../../skills/feather-handoff/scripts/feather_handoff/writing.py) 已有 create/update、版本檢查、人工內容保留與完成歸檔；新資料沿用這条寫入路徑。
- [分工入口](../../templates/AGENTS.md) 已有角色、所有權、驗收、受阻及重派原則；本版補上可觀察的回傳與收回條件。
- 符合 [ADR 0001](../../docs/adr/0001-handoff-file-tool.md)：交接仍是單份 Markdown，沒有持久索引或跨 session 鎖定，工具不取代 Agent 的語意判斷。實作若改成 sidecar、資料庫或鎖定系統，須先重新決策。

## 本版範圍

- 選填的結構化檔案基準、唯讀擷取與比對。
- 基準隨既有建立、更新、完成歸檔及封存保存。
- 輕量子任務回傳約定、主 Agent 驗收與有界重派。
- 舊格式相容、完整安裝包部署、離線及原生行為驗收。

延後：常駐指令全面拆分、跨 worktree 同步、多 session 鎖定、背景監控、doctor、進行中搜尋、Claude memory 匯入、成本儀表板及新角色。沒有新的常驻程序、自動模型升級或主模型／並行數設定。

## A. 接續變更比對

### 責任與操作流程

1. Agent 選出支撐目前工作結論的具體來源路徑；可含已追蹤、未追蹤與預期不存在的檔案。使用專案相對路徑，不接受目錄或 glob，不掃描整個 repository。
2. 唯讀 `snapshot` 取得各路徑的 SHA-256 或缺失／未知狀態，以及擷取時間和可取得的 Git HEAD、分支。工具只回傳 JSON，不保存交接。
3. Agent 整理進度，再以既有 create/update 傳入 snapshot；更新仍帶完整交接的 version。顯式提供新 snapshot 時，工具在保存前重新核對其中 present/missing 與 Git 已知觀察；過時或變動中的基準拒絕寫入，Agent 重讀後重新整理，不默默換成新的基準。unknown 保留為未驗證，不因保存而變成已確認。只更新進度而未提供新 snapshot 時保留舊基準，不以來源已變阻擋進度更新。
4. 接續先讀完整交接，再執行唯讀 `compare --work <work>.md`。沒有基準的舊交接照現有流程核對，不要求轉換才能接續。
5. Agent 解讀差異、確認必要來源及驗證，才繼續授權工作。一般 list/read 不執行 compare、不修改基準、不觸發工作。

基準是「在某時間觀察到的檔案內容」，不是測試通過證明。只在保存交接後取得基準，不能倒推該內容曾被先前測試驗證。若要主張測試涵蓋這份內容，需另有測試前後相關來源未變的觀察及命令、工作目錄、時間與結果；這仍不證明未列入的依賴或外部環境一致。

### 資料與相容性

同一交接檔加一個選填、唯一的 `## 檔案基準` 區段，內容為單一 fenced JSON；不新增 sidecar。v1 形狀如下，這是設計示例，不是實測資料：

```json
{
  "schema_version": 1,
  "captured_at": "2026-09-12T14:00:00+08:00",
  "git": {"state": "available", "head": "<observed commit>", "branch": "main"},
  "files": [
    {"path": "src/auth.py", "state": "present", "sha256": "<64 lowercase hex digits>"},
    {"path": "config/local.json", "state": "missing"},
    {"path": "data/input.bin", "state": "unknown", "reason": "unreadable"}
  ]
}
```

- `captured_at` 必須帶時區。Git 狀態為 available、not-repository 或 unknown；detached HEAD 的 branch 為 null，尚無 commit 的 head 為 null，與命令失敗分開回報。
- 路徑使用 `/`；拒絕絕對路徑、`..`、NUL、空值、大小寫規則下的重複路徑。每項只保存路徑、狀態與摘要，不保存來源正文。SHA-256 對原始 bytes 計算，不正規化來源編碼或換行；輸出 files 依正規化路徑排序。
- 只辨識 fenced code block 外的精確二級標題 `## 檔案基準`；區段結束於下一個一級／二級標題或 EOF。內文僅允許空白及一個 json fence，拒絕 JSON 重複 key 或多個物件。詳細紀錄的程式碼範例或相似標題不能被誤判為受管理區段。
- create/update 增加選填 `snapshot` 物件，未提供即保留既有基準；更新進度不能自動刷新舊基準。明確傳入新物件才替換。`snapshot: null` 拒絕，第一版不提供單獨移除基準功能。
- 新資料由工具解析與驗證；snapshot 值不可被視為來源可信或執行授權。缺欄、未知版本、重複區段或壞 JSON 要回報，不能當成「無基準」。
- `## 詳細紀錄` 與 `## 檔案基準` 為平行區段，局部更新保留彼此及所有可辨識人工內容，含 BOM／換行慣例。完整 replacement 仍須驗證基準格式；與 snapshot 參數互斥。
- 未知版本的交接可讀完整原文；比對回報 unknown，正常更新保留資料並停止不明結構的改寫。明確且語意清楚的人工修復沿用現行 reviewed replacement 流程。
- list 僅多提供 `snapshot_state: absent / available / invalid`，不在列清單時計算來源雜湊。歸檔與封存保存完整區段及原完成身份；重試不重算基準。
- 傳入的 snapshot 與 captured_at 是 caller 提供的資料；保存時重驗只支持「當下已知項相符」，不能證明擷取來源、過去時間或測試經過。重新核對失败、非法 snapshot、未知結構或 version conflict 均在寫入前停止，不修改交接或 Git ignore。保存後 tracking／歸檔失敗沿用既有 partial 回傳與 saved_version，重試不重新建立交接。

### 唯讀介面

以下 `<tool>` 為安裝中的 handoff.py；snapshot 的路徑透過 UTF-8 JSON stdin 提供。

```text
python -B <tool> --project <project> snapshot
stdin: {"paths": ["src/auth.py", "config/local.json"]}

python -B <tool> --project <project> compare --work <work>.md
```

- snapshot 回傳 `status`、`complete`、`snapshot`、`issues`；部分來源失敗仍回傳可用觀察，未知項逐一列出。create/update 可保存合法的 unknown 項，不能宣稱完整基準。
- compare 回傳 `status`、`complete`、`work_version`、`baseline_state`、`files`、`git`、`issues`；baseline_state 為 available、absent 或 invalid。files 每項保留 path、baseline_observation、current_observation 與 comparison，Git 另保留前後觀察與差異。absent 時 complete=false，status=ok，退出 0。指定原交接不存在（含完成後已移入歷史）時回報 status=missing、complete=false、退出 2，不自動搜尋歷史或選同名工作；完成待歸檔且原檔仍存在時可正常比對。本版不提供歷史條目的 compare 入口。
- 檔案結果：present→同摘要為 unchanged；present→不同摘要為 changed；present→missing 為 missing；missing→present 為 created；missing→missing 為 unchanged 並附前後狀態。任一端 unknown 為 unknown。
- 沒有基準與空清單都不表示工作完全未變；snapshot 的 paths 必須非空。工具只對選定範圍作結論，不偵測該範圍外新增來源。
- 成功取得完整差異時退出 0，包含確定的 changed/missing/created；讀取、格式、部分失敗或不穩定時退出 2，status=partial/error。差異與操作失敗分開。
- Git HEAD 與分支分別比對，Git 不可用不阻止普通檔案比對；metadata unknown 時 complete=false。相同 HEAD 不能掩蓋未提交來源差異。

### 路徑、穩定性與上限

- 僅讀解析後仍位於目前專案內的普通檔案。拒絕路徑任一段的 symlink/reparse point、硬連結檔案、特殊檔案及 `.git`、`.feather/handoffs` 內的路徑；避免別名、自我引用及 Git 管理內容。
- 確認合法父路徑後才把不存在判為 missing；permission denied 或無法檢查父路徑一律 unknown。
- v1 最多 256 個路徑，每檔最多 16 MiB，總讀取最多 64 MiB／次；超限明確回報，保留已取得結果，不靜默省略。不得把截斷內容的摘要當完整檔案摘要。
- 擷取時核對讀取前後檔案身份與 metadata；觀察到變動最多重試一次。批次前後再核對清單及 Git metadata 的穩定性；仍變動標 partial/unknown。
- 比對結束前重新核對 work_version，交接在讀取間變動時回報 partial，不對新版本交接套用舊結論。
- 這些檢查不提供全專案原子快照或防惡意競態的隔離。保存基準前的檢查仍遵守既有單一寫入者協調，不宣称跨 session 安全。
- Git 命令設逾時，使用不更新 index 的唯讀查詢；不自動更改 safe.directory、分支、設定、Git ignore 或專案信任。非 Git 專案可完整比對檔案。

### 驗收案例

- 舊交接、同 HEAD 下未提交檔變動、未追蹤檔、刪除及重新建立、非 Git、detached/unborn HEAD。
- 超出範圍的新檔不造成「專案完全未变」聲明；可觀察差異與語意影響分開。
- 不可讀、上限、連結、目錄別名、硬連結、跨根目錄、大小寫重複及讀取間變動都有明確結果。
- 基準過時保存、更新進度但保留基準、壞 JSON／未知版本、重複區段、BOM、CRLF、額外段落及 details 更新。
- 首次完成、歸檔失敗重試、封存後原始基準完整保留；完成身份不變。
- snapshot/compare 前後來源、交接、Git index/config/ignore 內容不變；测试不以 canary 未寫入冒充 sandbox 強制保護。
- 原生 Agent 面對 changed 時核對來源，不直接沿用舊測試結果；unknown 不猜測；普通 read 不執行下一步。

## B. 子任務回傳與收回

### 回傳約定

使用短 Markdown，無強制 JSON、固定語言或新持久日誌。每次回傳包含以下資訊；不適用可用一行「無／未執行」，小任務可合併呈現：

| 資訊 | 要回答的問題 |
| --- | --- |
| outcome | completed、partial 或 blocked？只描述子任務狀態。 |
| 結果與證據 | 得到了什麼，來源位置或成果在哪，哪些是推論？ |
| 變更 | 實際新增／修改／刪除哪些路徑，或無寫入？ |
| 驗證 | 執行了什麼、在哪執行、结果及未驗證項目？ |
| 阻礙與下一步 | 已尝試什麼、缺什麼，以及可接手的最小下一步？ |

scout 保持純唯讀引用事實；analyst 保護來源且僅寫明確指定成果；兩種 executor 回報實際改動與行為驗證。通用子 Agent 使用同樣資訊，仍遵守單層委派。回傳內容不是實際模型、reasoning 或 sandbox 的執行證明。

### 主 Agent 驗收

1. 對照原 brief 的範圍與完成條件，檢查引用、成果及缺漏。
2. 寫入任務依派工前基準核對實際變更集合，區分原有未提交修改及其它合法工作；analyst 的來源雜湊也須比對。發現越界先保留现场與報告，不覆蓋或盲目復原他人修改。
3. 只執行必要的驗證；可信且仍適用的測試結果可沿用，不因回傳格式而重跑所有測試。
4. 子任務 completed 經主 Agent 驗收後才納入整體完成。缺證據可要求補齊，partial/blocked 保留已有成果。

### 有界重派

- brief 已有範圍、所有權及完成條件；複雜任務按需補上一個明確檢查點，不為每個小任務建立流程表。
- 第一次阻塞時主 Agent 先辨認：暫時故障、規格不足、職責不符或跨範圍依賴。只有具體可恢復的暫時故障可原樣重試一次。
- 同一原因再次發生時收回，由主 Agent 縮小問題、補充證據、改派合適角色或自行處理；不再原樣重派。缺少必要授權或不可推定資訊時保留阻礙，其他獨立工作繼續。
- 「同一原因」由主 Agent 以失敗操作、目標與根本阻礙判定，保留一行穩定原因描述；改寫錯誤措辭、換子 Agent 或換模型不重置。原阻礙有新證據證明已解除，或工作範圍／方法實質改變時才重新評估；這不是對同一失敗無限續次的許可。
- 收回時保留已知事實、嘗試與錯誤、實際修改、驗證及最小下一步，讓下一位從此處接手。
- 重新分配寫入所有權前，確認前一子 Agent 已停止操作或完成。不能只因逾時就讓兩位同時寫同一範圍。
- 重派仍逐欄解析模型／reasoning，遵守使用者偏好與單層規則。回傳品質不足不構成自動升級模型或擴大授權。

### 驗收案例

- 子 Agent 自稱 completed 但漏了必需成果／驗證，主 Agent 不宣稱整体完成。
- 主 Agent 驗收須先於保存整體交接為「完成」，避免子任務自述提前觸發歸檔。
- 子 Agent 已留下部分合法修改後 blocked，主 Agent 正確保留並接手。
- 同原因第二次失敗不再原樣重派；新 brief 含既有證據，不重複查找。
- 缺少規格時不猜值，獨立工作仍完成；停止確認之前不移交同一路徑。
- 四角色及通用子 Agent 都遵守回傳資訊與各自權限；小任務不要求產生額外成果檔。

## 交付與完成條件

工作票規劃順序為 01→02→03；04 可獨立進行；05 等待 03、04；06 等待 05。並行僅用於無共享寫入的實作範圍。

離線回歸通過、Windows／Linux 部署與基本操作證據齊備，並完成隔離原生行為案例後才可標示本版驗收完成。原生測試依現有明確啟用與主模型設定流程；無法執行的情境列未驗證，不以離線測試替代。預期／配置模型與實際執行證據分開記錄。

本規劃沒有日曆工期承諾。第一個可用增量是 01–03 的 snapshot 保存與唯讀 compare；第二個是 04 的回傳約定；部署、文件與原生驗收由 05–06 收尾。
