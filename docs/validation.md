# MVP 實作與驗證紀錄

2026-09-07。對照 `.scratch/feather-mvp/spec.md` 及待辦 01–06。

## 已實作

| 待辦 | 交付內容 |
| --- | --- |
| 01 | scout、隔離 home／workspace、native probe、live gate、已知答案與證據分層 |
| 02 | analyst 唯讀模板、原始碼與文件矛盾素材、修改決定回交主 Agent |
| 03 | mech-executor、明確所有權、批次成果與範圍驗證 |
| 04 | executor、局部工程決策素材、實際函式行為與邊界驗證 |
| 05 | 主 Agent 直接處理兩情境、通用子 Agent 創作 brief、繼承契約與來源說明 |
| 06 | 共用四角色指令、九情境入口、依賴／衝突／阻塞／重派／矛盾整合素材與人工準則 |

使用者本輪明確要求「全部實作」，因此完成所有可獨立建置的交付物，不再以第一票的真實模型驗收未完成為由擱置後續程式與模板。票據仍保留未驗收項目，不把實作完成等同 resolved。

## 驗證方式與限制

- 標準函式庫 unittest 經公開 CLI 驗證準備、配置、啟用界線、唯讀副作用、修改結果與範圍；工程情境執行函式案例，含巨大 attempt、浮點邊界、無效輸入。
- Python compileall 作語法檢查；未配置型別檢查器。
- 原生 CLI 0.153.4 的 prompt-input 探測及四角色靜態配置檢查通過；候選 AGENTS 指令載入隔離 workspace。
- 真實 smoke test 未啟用，沒有以模型生成成果完成九情境的紀錄。單元測試中的已知正確成果僅用於驗證驗收器，不能算 Agent 行為驗收。
- 實際角色、每回合 model/reasoning、通用繼承、調度次序與唯讀權限均未確認。Thread 配置 metadata 不能當成實際執行證據。
- 真實 Codex home、既有角色、hook、主模型、reasoning 及並行數未修改。

完整命令與人工驗收步驟見 README；模型測試須加 `--enable-live` 並使用使用者選定的主模型／reasoning 和隔離登入。

## 最終離線結果

`python -m unittest discover -s tests -v`：11 項測試通過（6.818 秒，測試 runner 的牆鐘紀錄，非模型耗時）。`python -m compileall -q scripts tests` 通過。四角色 native 指令載入探測成功，但負向測試證明該 debug 入口不驗證角色 TOML。

code-review 的規範與規格兩軸已分別完成。發現一項版本證據覆寫問題，已修正並以先失敗後通過的回歸測試驗證；詳見 [審查紀錄](review.md)。
