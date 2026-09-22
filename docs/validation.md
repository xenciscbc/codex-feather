# MVP 實作與驗證紀錄

## 2026-09-08 analyst 成果與權限探針

依使用者澄清，analyst 保護來源但可寫明確指定的分析成果；scout 純唯讀。已更新 domain 詞彙、產品指令、analyst sandbox 與情境資料，新增 analyst-report 驗收。

- 16 項 unittest 通過（11.835 秒）；compileall 與 diff --check 通過。新增檢查涵蓋指定成果必須存在且非空、來源／其它路徑改動失敗，以及硬連結來源不能冒充獨立成果。成果語義與作者身分仍須以真實回合核對。
- 第五輪新 session 的正式 scout 與未指定成果的 analyst 沒有寫檔；指定成果的 analyst 寫入分析報告且來源保持不變，主 Agent 沒有代寫。
- 臨時診斷角色的 read-only 預設在本輪未形成強制隔離：原有權限下實際寫入探針成功，同目錄正向對照也成功。正式 scout 的唯讀行為通過，sandbox 強制唯讀不通過；兩者分開記錄。
- 第五輪基準在 session 啟動前建立，143 個基準檔只變更兩個授權 canary。分析成果在指定路徑新增，其餘來源與前四輪結果保持不變。臨時角色於回合結束後移除並另記錄。

詳細事件與環境限制見 [原生相容性](native-compatibility.md)。以下保留各輪歷史判定；第四輪的 analyst 唯讀 sandbox 期待已由本次來源保護規則取代。

## 2026-09-08 規則修正回歸

移除角色 TOML 的固定模型／強度，由主 Agent 依產品 AGENTS.md 的角色預設和使用者指定值解析兩欄，再透過原生參數派工。單層限制保留，補上直屬父 Agent 回報規則。

- 14 項 unittest 全數通過，含四角色各自禁止重新加入 model 或 model_reasoning_effort、三個覆寫情境及唯讀素材保全、舊格式拒絕驗收。compileall 與 diff --check 通過。
- `test_gpt` 第四輪新 session 實跑四項：baseline、model-only、effort-only、both。原生具名角色呼叫均接受、結果正確、own turn_context 的模型與強度吻合；三個覆寫案例已解除第三輪的 blocked 狀態。
- 原生父子 metadata 與四個完成回合的工具事件未見孫代理、再次委派或跨 task 回報。100 個舊檔只有五份允許的啟動前模板更新，其餘 95 檔保持不變；模板與產品來源一致。
- 限制：服務端逐回應模型 telemetry 未取得。四個子 context 的 workspace-write 與模板 read-only 不符，雖未發生子代理寫入，仍不能宣稱強制唯讀通過。第四輪新增素材的 session 快照晚於派發，保全結論另以舊 manifest 與工具事件補核。

詳見 [原生相容性](native-compatibility.md)。以下保留初始 MVP 的歷史驗證紀錄。

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
