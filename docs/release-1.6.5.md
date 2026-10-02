# v1.6.5

Python handoff 工具與維護規則對齊 cc-feather v0.10.1，包含 CLI JSON 錯誤、root 選項位置、完成保存與歸檔復原、詳細紀錄章節保護、清除／封存前的 pending 與衝突檢查、Git 追蹤選擇及 Windows 路徑處理。保留 Codex 的明確呼叫、計畫審查紀錄與較完整的 ctime 變動偵測。

Setup 的 handoff 安裝、更新及移除接受純 LF／CRLF 轉換，沿用文件換行並保留區塊外內容。完整入口已消失時，移除可解除所有權；更新須明確 replace 才補回，缺單邊標記仍拒絕操作。入口模板同步主 Agent 統一寫入及實作期間等待使用者前更新的規則，delegation bundle 格式驗證也接受 CRLF。

更新 plugin 後，對要同步新版維護入口的已安裝範圍執行 setup `update --components handoff`。Plugin-backed handoff 只管理入口；更新與移除保留 provider、其他元件及交接工作、歷史與封存。

驗證：handoff 回歸 184 項（174 通過、10 條件略過）；setup、plugin setup 與相關回歸共 152 項（150 通過、2 條件略過）。Python 語法檢查及 diff 檢查通過。未重建獨立發行包或執行新的模型行為測試。詳細證據見 [handoff 驗證](handoff-validation.md)、[setup 驗證](setup-validation.md) 與 [來源清單](cc-feather-handoff-manifest.json)。
