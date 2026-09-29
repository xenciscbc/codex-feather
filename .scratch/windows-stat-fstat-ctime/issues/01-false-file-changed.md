# Windows / Python 3.12：stat 與 fstat 的 ctime 差異造成交接讀取誤判

Status: resolved
Type: task
Reported: 2026-09-29
Audience: codex-feather 維護者

## 問題

codex-feather 1.6.0 在 Windows、Python 3.12 環境讀取未修改的交接檔時，錯誤回報 `File changed during read`。請維護者修正原始碼、補上回歸測試並發布更新。

## 操作與結果

```text
handoff.py ... read --work franchise-promo.md
```

實際結果：`File changed during read`。
預期：未在讀取期間變動的交接檔應可正常讀取。

## 使用者提供的證據

同一檔案的 `stat()` 與 `fstat()` 結果中，大小、修改時間及檔案識別值一致，但 `st_ctime_ns` 不同。使用者確認這是插件工具的誤判，並非交接檔真的在讀取時被修改。

本回報未附原始數值或該交接檔；上述環境與現象來自使用者提供的證據，尚未在本工作區重現原始案例。

## 原始碼核對

- `skills/handoff/scripts/feather_handoff/storage.py:113`：`read_file()` 的 signature 包含 `st_ctime_ns`；後續直接比較路徑 `stat()` 與控制代碼 `fstat()` 的 signature，差異會於第 115 行觸發錯誤。
- `skills/handoff/scripts/feather_handoff/observations.py:13-15`：`signature()` 也包含 `st_ctime_ns`；`observe()` 開檔與讀取完成時均跨 `stat()` / `fstat()` 比較，具有同類誤判風險，可能將來源標記為 `unknown / changed`。

依目前程式邏輯，即使其餘欄位一致，單獨的 `st_ctime_ns` 差異仍足以觸發此錯誤。Windows / Python 3.12 中兩種 API 回傳該欄位差異的底層原因，留待實作時確認。

## 修正與發布要求

1. 修正兩處比較，使用在目標平台可跨 API 比較的欄位，或分開處理同來源狀態檢查；避免單憑此 ctime 差異判定檔案遭修改。
2. 保留真實檔案替換、大小或修改時間變動，以及既有路徑安全檢查的偵測能力。
3. 新增回歸測試：模擬身份、大小與修改時間一致，只有 `stat()` / `fstat()` 的 `st_ctime_ns` 不同；確認讀取成功且來源觀察正常。
4. 驗證實際變動仍被拒絕，並於 Windows / Python 3.12 驗收。
5. 發布修正版插件，於更新說明列出此修正及可升級版本。

## Comments

2026-09-29：依專案 Local Markdown issue tracker 建立回報；已核對兩處原始碼比較邏輯。修正與發布尚待維護者處理。


## Implementation — 2026-09-29

- 共用 signature 比較：Windows 跨 stat/fstat 忽略 ctime；同 API 前後仍比較 ctime，POSIX 跨 API 也保留 ctime。
- storage 與 observations 都比較開啟時的 fstat 和讀完後的 fstat，另比較讀取前後的 stat。
- Windows Python 3.12.11 實機重現（建立檔案後改寫，再進行讀取）：
  - stat：size=5，mtime_ns=1790670118218144700，ctime_ns=1790670118197519200。
  - fstat：size=5，mtime_ns=1790670118218144700，ctime_ns=1790670118218144700。
  - st_dev=2633115009780282114、st_ino=21392098230087114，兩 API 一致。
  - 原始 read_file 拋出 File changed during read；修正後回傳精確內容 b'after'。
- 新增兩邊界的跨 API 差異、descriptor 變動、path ctime 變動、POSIX 拒絕案例；先確認兩個正向回歸在修正前失敗，再逐一修正。
- storage 型別檢查通過。observations 原有 18 個 mypy 錯誤與基準 511f423 完全相同（忽略行號），未引入新錯誤。
- CPython 上游同類問題：https://github.com/python/cpython/issues/157671 。
- 1.6.1 manifest 與更新說明已準備。


## Review

- Standards：無文件規範違反；測試 metadata 模擬有重複的非阻擋建議。維持測試邊界各自完整，以避免此小修正引入額外測試抽象。
- Spec：初審要求真實讀取中改寫的證據；補上 read_file 與 capture 的實際磁碟改寫測試後，複審確認缺口關閉，無實質阻擋。
- 兩項新增真實改寫測試與其他邊界測試在 Windows Python 3.12.11 共 23 項通過。
- 審查由兩個獨立 analyst（gpt-6-sol / high，依專案預設配置）唯讀完成；父 Agent 確認實作檔案 hash 未變。


## Answer

修正已完成，版本為 1.6.1；由主 Agent 實作並整合雙軸審查，發布方式為將本次提交推送到 marketplace 使用的 master 分支。

### 完整測試限制

- 工作區 Windows Python 3.11.9：290 項，282 通過、5 失敗、3 略過。5 項失敗都在 test_handoff_environment 的既有不完整 bundle fixture，錯誤為 entrance template is required。
- 僅基準 511f423 + 本修正的乾淨副本，Windows Python 3.12.11：285 項，214 通過、65 失敗、3 錯誤、3 略過。涵蓋既有安裝器對 CRLF delegation skill 的拒絕、上述 fixture 問題，以及為沿用已安裝 PyYAML 設置 PYTHONPATH 後影響一項「缺少依賴」測試。
- 工作區原有 scripts/setup_installer/bundle.py、entrances.py、tests/test_setup.py、docs/setup.md 變更均未納入本修正。bundle.py 原有未提交修改正是 CRLF 驗證修補。
- 這些結果不代表全套通過；本版本只處理交接讀取誤判，不聲稱修復上述安裝器／驗收環境問題。
- 完整測試後新增的兩項真實磁碟改寫測試另以 Windows Python 3.12.11 執行，相關邊界共 23 項通過。

- 最終乾淨副本 Windows Python 3.12.11：所有 test_handoff*.py（不含獨立 installer runtime 的 test_handoff_environment）共 107 項，106 通過、1 項 symlink 平台條件略過；包含最後新增的真實改寫測試。
