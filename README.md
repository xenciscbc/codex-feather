# codex-feather

讓 Codex 自動分工，並把工作進度留給下一個 session。

- **分工**：依任務需要安排查找、分析與實作，最後整合結果。
- **交接**：保存進度、查看目前工作，或在新 session 繼續處理。

## 安裝

先準備好 Codex；交接功能另需 Python 3.11+。安裝器本身不需要 Python。

1. 依 [安裝說明](docs/setup.md) 取得或建置對應平台的完整安裝包。
2. Windows 開啟 `feather-setup.exe`；Linux 執行 `./feather-setup`。依引導選擇目標專案、功能並啟用入口指引。
3. 在目標專案開啟新的 Codex session，即可使用。

目前尚未提供公開的二進位下載；來源建置方式也在安裝說明中。

## 使用

安裝後，直接對 Codex 說你要做什麼：

| 想做的事 | 可以這樣說 |
| --- | --- |
| 分工處理任務 | 幫我分工檢查登入功能，找出問題並修正。 |
| 保存目前進度 | 用 feather-handoff 交接目前工作。 |
| 查看工作清單 | 用 feather-handoff 列出目前的交接。 |
| 接續工作 | 用 feather-handoff 接續登入功能的工作。 |
| 只看進度 | 用 feather-handoff 讀取登入功能的交接。 |

交接後，Agent 會在重要進展時更新紀錄，工作完成後自動歸檔。接續時使用同一份專案目錄；若有多項工作，說出工作名稱即可。

只查看進度不會執行下一步。歷史紀錄會保留，直到你明確要求清除。

## 更多說明

- [安裝、更新與移除](docs/setup.md)
- [交接、搜尋歷史與封存](docs/handoff.md)
- [分工規則](templates/AGENTS.md)
- [開發與驗收](docs/development.md)
- [交接工具驗收紀錄](docs/handoff-tool-validation.md)
- [平台與原生能力限制](docs/native-compatibility.md)
