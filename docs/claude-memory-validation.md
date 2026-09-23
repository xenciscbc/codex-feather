# Claude memory 外部交接驗收

## 01：明確 memory 目錄（2026-09-10）

新增唯讀讀取分支及按需載入的參考文件。沿用既有 prepare／check／verify 入口，新增 Claude memory 隔離素材與回覆核對；產品仍是 Agent 技能，沒有另外建立 memory 執行器。

TDD 經過情境不存在、缺少回覆、漏報工作、捏造或錯置來源、遺失具體值、遺失矛盾來源、重複工作及遺漏讀取失敗範圍的失敗案例後補強。此階段新增核對器測試 5 項、既有 handoff 測試 23 項通過；新驗收模組 mypy 通過，compileall 語法檢查通過。完整套件在全部工作完成後執行。

四個無前文繼承的原生子 Agent 僅讀候選技能、各自 prompt 與隔離素材；主 Agent 由對應原生日誌擷取工具事件與最終回覆，核對操作後執行公開 verify。來源、技能副本與相關設定均保持不變。

| 隔離情境 | 原生行為與核對結果 |
| --- | --- |
| native-direct-v1 | 正確回報 cache-rollout、7319、未測試、readiness 與 timeout；一般偏好未列為工作。 |
| native-mixed-v1 | 找到索引未列出的記錄，保留 7319／8443 衝突，分別回報已完成 asset-cleanup 與狀態不明的疑似交接 queue-check。 |
| native-no-request-v1 | 一般 Feather 讀取僅查目錄並回報無待接續工作；未讀取存在的 Claude memory 內容。 |
| native-partial-v1 | Windows 另一程序以 FileShare.None 鎖住隔離 locked.md；原生工具兩次實際讀取失敗，Agent 回報不完整範圍，未改權限或繞過鎖。釋放後來源驗收通過。 |
| native-empty-v1 | 規格審查後補跑：完整盤點並讀取唯一 preferences.md，依具體內容排除一般偏好，清楚回報完整搜尋但沒有交接；來源不變。 |
| native-missing-v1 | 規格審查後補跑：只檢查指定 memory 的 metadata 並確認不存在，回報未能搜尋，沒有建立目錄或改查替代來源；來源不變。 |

實際證據在 `.scratch/claude-memory-handoff/runs/<情境>/` 的 `native-tool-events.json`、`answer.md` 與 `verification.json`。只擷取公開工具事件與最終回覆，不匯出其他對話內容。CLI 的 `actual` 仍是 `unconfirmed`；手動核對記載於此，不以手填欄位或檔案雜湊推定沒有越界讀取。

設定與證據分開解讀：direct、mixed、partial 使用 analyst，原生派工設定為 gpt-5.6-sol／medium；一般 Feather 查找使用 scout，設定為 gpt-5.6-luna／low。這些值來自專案角色預設及實際 spawn 參數；取得了工具執行與回覆證據，沒有取得每回合模型執行 telemetry，因此實際模型／推理用量未確認。角色 sandbox 宣告不等於逐檔權限保證，唯讀結果另由工具操作與來源比較核對。

## 02：專案來源定位（2026-09-10）

定位依據與官方文件連結集中在 [定位參考](../skills/handoff/references/claude-memory-location.md)。核對現行官方頁面後，使用 project/local 設定受 workspace trust 影響的規則；沒有沿用舊搜尋摘要中「僅 user/managed 可設定」的限制。普通設定優先序與真正的信任狀態歧義分開處理。

新增定位素材涵蓋自訂位置、預設位置、Git worktree／子目錄、非 Git、已確認的啟動命名、信任狀態歧義、有效設定指向缺失目錄及不合法相對位置。累計 11 項 memory 核對器測試通過，包含錯誤來源、設定與 Git metadata 修改的拒絕案例；mypy 通過。非 Git 素材另拒絕位於既有 repository 內的準備位置。這些是素材與核對器測試，不等於所有情境皆有原生實跑。

| 隔離情境 | 原生行為與核對結果 |
| --- | --- |
| native-project-custom-v1 | 依可信 project-local 的 autoMemoryDirectory 選定 memory，正確摘要 cache-rollout；未讀 shared-memory 或 user-memory 的筆記。設定讀取指令曾有語法錯誤，修正後成功，輸出僅包含定位鍵。 |
| native-project-worktree-v1 | 從 checkout/subdir 找到 main worktree 與共用 Git 關聯，讀取唯一的預設 memory；三份 Markdown 全數讀取。Git status 有全域 ignore 不可讀警告，但前後 Git metadata 與來源比對無變化。 |
| native-project-ambiguous-v1 | 信任狀態不明時列出 memory 與 user-memory，等待指定；工具事件只讀設定與目錄 metadata，沒有開啟任一候選的內容。 |
| native-project-ambiguous-selection-v1 | 同一原生 Agent 收到明確選定 memory 的後續指令後，只讀該候選三份 Markdown 並完整摘要 cache-rollout；未讀另一候選。此階段另存公開事件與回覆，以原試用的 check 核對來源不變，沒有改寫先前的歧義回覆。 |
| feather-memory-native-non-git-20260910-v1 | 在 repository 外的系統暫存目錄執行；Git 確認不是 repository 後，依指定 root 與設定找到唯一預設 memory，完整摘要且來源不變。證據保存在該暫存試用目錄。 |

以上均由 analyst 執行，原生參數為 gpt-5.6-sol／medium，來源驗收通過；實際模型 telemetry 仍未確認。啟動命名及無效設定目前由離線素材／核對器覆蓋，不宣稱已有原生行為證據。

## 03：同專案交接連結（2026-09-10）

executor 負責連結規則、四個隔離情境及公開 CLI 測試，主 Agent 整合並核對原生結果。4 項新增測試通過，涵蓋同專案連結、未知專案、實際目標越界與專案定位後的連結閱讀；也核對重複／循環引用、外部與網頁來源、遺失／目錄／無法解碼的目標及來源保護。Windows 無 symlink 權限時使用實際 junction，另保存連結身份與 target file ID，避免只靠相同內容的雜湊忽略連結替換。

| 隔離情境 | 原生行為與核對結果 |
| --- | --- |
| native-links-v1 | 早期素材已正確讀取同專案交接並保留 7319／8443 衝突，未讀外部、網頁與下一層文件。此素材早於新增無效／不可讀目標，最終核對器不再接受；保留原始證據，不算最終 artifacts pass。 |
| native-links-alias-v1 | 實際識別 junction 越界，未讀外部內容；回覆將路徑拆成片段，未通過完整引用核對。依此補明完整原始連結的回報規則。 |
| native-links-alias-v2 | 使用新技能副本重跑；完整列出原始路徑、指出 junction 的外部目標並停止讀取，允許的 handoff 正確摘要。工具事件及連結／來源完整性核對通過。 |
| native-links-unknown-v1 | 完整搜尋 memory 並回報狀態不明的疑似交接 memory-audit；未知專案的連結僅列出，工具事件未讀取該目標。來源與回覆驗收通過。 |
| native-project-links-v1 | 由可信 project-local 設定定位 memory，再讀其同專案交接；保留 7319／8443 衝突，未讀其他候選、外部、網頁、下一層文件或逐字稿。對 unreadable.md 持有 FileShare.None 唯讀鎖，原生讀取確實失敗，回覆保留可讀結果並標示不完整、缺失及目錄型目標；釋放鎖後來源、設定與 Git metadata 驗收通過。 |

後續情境重用已完成的 analyst 原生 thread，每次讀取新試用的技能、prompt 及素材，不把先前 fixture 當作來源。公開工具事件依最後完成回合分開擷取，先前的答案與失敗證據保留。這些實跑不是互相隔離的盲測，且實際模型 telemetry 仍未確認。

## 整體檢查

完整來源測試套件共 113 項：111 通過、2 跳過（standalone 發行程式測試及需指定 Windows 測試 profile 的原生探索）；Claude memory 新增 15 項全部通過。整合實跑另暴露核對器對 Windows 路徑分隔符及設定證據表達方式的誤拒；以 TDD 補上等價路徑與設定檔引用案例，4 項連結測試及該模組 mypy 再次通過。兩個新 Python 模組 mypy、compileall 及技能 quick_validate 通過。quick_validate 在此 Windows 預設 cp950 讀取 UTF-8 文件會失敗，使用 Python 的 `-X utf8` 後完成驗證。

Standards 審查指出地圖未同步，以及情境分派／答案核對的兩處重複。同步地圖、採用單一 family registry 與共用 verify_works 後，複查沒有剩餘發現；15 項 memory、23 項 handoff、16 項一般 trial 回歸及 mypy 通過。Spec 審查指出 empty／missing 缺原生證據，已補上表列實跑，複查沒有剩餘發現；沒有發現錯誤功能或範圍擴張。

提交前另外將本次修改套到乾淨 HEAD 副本，排除原先工作區的其他變更。該副本的 15 項 memory、20 項 handoff 與 11 項一般 trial 測試全部通過；兩套基準的既有測試數不同，不能混算成同一套測試總數。原始基準 94 個已追蹤檔案中，非本次所有權範圍的內容均保持不變。

## 範圍與限制

各成功案例表示這些隔離輸入的觀察結果，不保證所有自然語言記憶皆能精確分類。核對器只驗證已知工作、來源與具體值等可檢查內容，狀態、理由與讀取範圍仍需原生證據。01 未執行使用者個人目錄安裝或發行包重建；原生試跑使用隔離的候選技能副本。
