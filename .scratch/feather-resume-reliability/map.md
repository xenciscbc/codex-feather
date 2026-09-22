# Feather 接續可靠性工作索引

## Notes

- 使用者於 2026-09-12 要求規劃下一版。主規格：[spec.md](spec.md)。
- 使用者已指示「開始實作」及最後 review 並修正。01–05 已完成；06 自動回歸、部署與原生試用成果已核對，完整原生事件驗收仍未關閉。
- 每票的原始碼範圍是後續實作所有權建議；實際委派前仍核對工作區及其它 owner。

## Decisions-so-far

- 優先交付接續變更比對與子任務回傳約定，沿用 ADR 0001。
- 保留單檔 Markdown 與既有 create/update；擷取與比對均唯讀。
- 保存基準與測試證據分開；子 Agent 完成與主 Agent 驗收分開。
- [01 基準格式](issues/01-snapshot-format.md) → [02 擷取及保存](issues/02-snapshot-capture.md) → [03 接續比對](issues/03-snapshot-compare.md)。
- [04 回傳與收回](issues/04-delegation-return.md) 可與 01–03 獨立規劃實作。
- [05 文件與部署](issues/05-integration.md) 等 03、04；[06 整體驗收](issues/06-acceptance.md) 等 05。
- 01 已完成 baseline 格式與 fenced Markdown 解析（4 項格式測試）；02–03 已完成 CLI 擷取、保存、比對、失敗保留與版本再核對。新增行為測試 Windows 18 項（1 symlink skip）、Ubuntu WSL 18 項全部通過。
- 04 已完成五項回傳與主 Agent 驗收、同原因第二次收回、停止後移交；兩個新情境有精確成果與負向驗證，test_trial 19 項通過。snapshot 審查後另補未知來源讀取額度、details 互斥與精確標題保留案例。

## Fog

- 最後審查問題與平台測試詳見 [接續可靠性驗證](../../docs/resume-reliability-validation.md)。Windows 190 項全套與新增 payload 檢查通過，Linux 94 項交接及 2 項部署通過；skip 明列。06 保持 claimed，因目前產物不能獨立證明全部原生事件時序。

- schema、命令與讀取上限為本次設計選擇，需以 01–03 的回歸案例驗證可行性；語意變更回寫 spec，不建立第二份衝突規格。
- Windows／Linux 對讀取中變動、reparse、硬連結與 Git metadata 的實際支援須保留平台證據。
- 原生派工事件能取得哪些停止確認／用量／模型證據依當次環境判斷；缺失項保持未確認。
