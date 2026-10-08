# v1.6.6

Python handoff 工具對齊 cc-feather v0.16.0。詳細紀錄與檔案基準的更新會保留以縮排、Tab 或空 ATX 標題分隔的後續章節；空白工作標題回報格式問題；Git 追蹤設定保留帶前導空白的使用者規則，並正確辨識行尾空格與追蹤 marker。

Handoff 技能補齊歷史標題選取，以及清除／封存遇到待歸檔、不明狀態或部分失敗時的復原指引。保留 Codex 的計畫審查紀錄與 Windows stat/fstat 相容修正。

驗證：handoff 套件 190 項，結果 OK（10 項條件略過）；新增基準保留案例後，基準測試 7 項全數通過；plugin setup 28 項全數通過。Codex 與 cc-feather 的雙向讀寫、歸檔及封存相容測試通過。來源雜湊、Python 語法與文件連結檢查通過；未重建獨立執行檔或執行新的模型行為測試。詳見 [handoff 驗收紀錄](handoff-validation.md) 與 [來源清單](cc-feather-handoff-manifest.json)。
