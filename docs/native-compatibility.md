# 原生相容性查證

## 2026-09-08：scout 唯讀與 analyst 來源保護

使用者澄清 analyst 並非全面禁止寫檔：來源文件不可變，明確指定時可另外產出分析成果。現行 analyst.toml 因此使用 workspace-write；具體限制是只写分配的成果路徑、來源及其它檔案不變。沒有指定成果時仍只回傳分析。scout 維持純唯讀行為與 read-only sandbox 預設。第四輪對 analyst 的 read-only 期待屬於這次澄清前的歷史測試。

第五輪於新 session `01a07e81-2e73-70c0-83ff-6b8a117e640f` 實測：正式 scout 查找未寫檔；沒有成果路徑的 analyst 直接回傳分析；有指定路徑的 analyst 親自寫入 round5/outputs/analysis.md，來源雜湊不變。

為區分工作規則與 sandbox，測試另建臨時 scout-permission-probe 角色：sandbox 同為 read-only，唯獨指令明確授權一次寫入拋棄式 canary。主 Agent 的同目錄正向對照成功，診斷子代理也以原有權限成功寫入 canary；原生 context 顯示 workspace-write。這證明本輪環境沒有強制採用該角色的唯讀預設，不能把正式 scout 自願不寫檔當成強制隔離通過。診斷角色不是產品 scout，測試例外不加入產品模板，完成後移除臨時角色並保留模板副本與清理紀錄。

此現象與 [官方 Subagents 權限說明](https://learn.chatgpt.com/docs/agent-configuration/subagents#approvals-and-sandbox-controls) 所述「父回合即時權限會重新套用到子代理並可覆蓋角色預設」一致。Feather 不修改主 session 權限以追求表面一致；強制唯讀有需求時，必須使用另行驗證的執行環境。analyst 的 workspace-write 也不提供逐檔來源隔離。

第五輪有啟動前完整基準，核對 143 個檔案只改變兩個授權探針，其餘來源、舊成果與設定保持不變。詳見 [第五輪報告](D:/work_data/project/other/test_gpt/REPORT_ROUND5.md) 與 [證據明細](D:/work_data/project/other/test_gpt/ROUND5_EVIDENCE.md)；基準核對描述的是完成回合，後續臨時角色移除另有清理紀錄。

## 2026-09-08：派工時選擇模型與強度

第三輪新 session 實测中，含 model / model_reasoning_effort 的 scout、analyst 角色被工具標示為不可變更，三個使用者覆寫案例在派工前 blocked。[官方 Subagents 文件](https://learn.chatgpt.com/docs/agent-configuration/subagents) 確認角色檔設定優先於 spawn 值；省略角色欄位時，原生先取顯式 spawn 值，再取 agents 預設及父設定。

新版四角色 TOML 移除這兩欄，保留職責、sandbox 與單層委派限制。Feather 預設移到產品 AGENTS.md；主 Agent 逐欄解析使用者指定值後，對具名角色明確傳入兩欄，避免只指定模型時採用該模型的原生預設強度。使用與覆寫相容的上下文模式；工具若要求有限繼承，brief 必須補足必要資訊。

靜態驗收改用 manifest format=3，拒絕殘留模型鎖定；新增 scout-model、scout-effort、analyst-override 三個真實派工情境。更新模板後須開新 session。

第四輪已於另一 project 的新 session `01a07e6c-4124-7972-be15-872e2fc64255` 完成：四次具名角色派工都明示兩欄及 fork_turns=none，原生接受且各自完成真實工作。baseline 為 scout luna/low；只改模型為 scout sol/low；只改強度為 scout luna/high；雙欄覆寫為 analyst luna/low。own turn_context 與各次請求一致，可讀原生代理樹只有四個 depth=1 子代理，沒有孫代理或跨 task 回報。底層逐回應模型 telemetry 仍未提供；不能以設定 metadata 代替。

本輪另確認權限差異：scout、analyst 模板保留 read-only，但四個原生 context 的 sandbox_policy.type 都是 workspace-write。實際子代理沒有改檔；強制唯讀 sandbox 尚未成立，原因未診斷，不宣稱整體權限驗收通過。來源與詳細事件在測試 project 的 [第四輪報告](D:/work_data/project/other/test_gpt/REPORT_ROUND4.md) 與 [證據明細](D:/work_data/project/other/test_gpt/ROUND4_EVIDENCE.md)。

下列為 2026-09-07 舊版固定模型模板的歷史紀錄，不代表目前模板內容。

查證日期：2026-09-07。本機 `codex --version`：`codex-cli 0.153.4`。
這是目前試用版本記錄，並非最低支援版本或四角色驗收通過聲明。

## 來源與採用方式

- [官方 Subagents 文件](https://learn.chatgpt.com/docs/agent-configuration/subagents)：自訂角色採獨立 TOML，放在 Codex home 的 `agents/` 或專案 `.codex/agents/`。本版使用前者；必要欄位為 `name`、`description`、`developer_instructions`。模型及 reasoning 放在角色檔。
- [官方設定參考](https://learn.chatgpt.com/docs/config-file/config-reference)：使用 `agents.enabled`；候選配置不設定主模型、reasoning 或並行數，也不使用替換內建指令的 `model_instructions_file`。
- [官方 AGENTS.md 文件](https://learn.chatgpt.com/docs/agent-configuration/agents-md)：先讀 Codex home，再讀專案指令；同一層優先 `AGENTS.override.md`，較深層指令優先。本試用使用獨立 home 和 workspace，避免繼承真實 home 的指令。
- 本機 `codex exec --help`：提供 `--json`、`--output-last-message`、`--strict-config`、`--skip-git-repo-check`。`codex debug prompt-input` 可在不呼叫模型下檢查提示輸入，但 **不支援 `--strict-config`**（本機已實測）。
- 本機 `codex app-server generate-json-schema --experimental --out <directory>`：`v2/ThreadStartResponse.json` 的 Thread 定義包含 `agentRole`、`model`、`reasoningEffort`；欄位可為 null。後兩者的欄位說明明確指出它們是目前或最近保存的配置，**不是每回合執行 telemetry**，不能用它們證明實際模型。可信的每回合實際模型／reasoning 來源仍未找到。

## 本次結果

`scripts/trial.py probe` 成功，輸入中含試用 workspace 的 Feather 指令，系統技能根目錄指向隔離 home。這確認指令載入及隔離 home 路徑；尚未確認角色載入、scout 派工或模型綁定。

隔離 config 使用官方 `project_root_markers` 指向 workspace 的 `.feather-root`，讓後續即使外層加入 Git repository，也有明確的試用專案根目錄。

另以隔離負向素材把 scout.toml 改成無效 TOML，再直接執行 native debug prompt-input，仍正常退出且沒有錯誤。因此此 debug 入口不能驗證角色 TOML 載入；四角色的靜態格式檢查由 Python tomllib 負責，原生角色生效仍需 smoke 驗收。

預期 scout = `gpt-5.6-luna / low`；TOML 設定相同；實際值 **未確認**。
尚未啟用會消耗模型用量的 smoke test。原生角色與實際模型須在該測試中確認；無法使用時保留錯誤，不替換模型。

官方文件描述角色檔的模型設定優先於派工設定；也提醒即時權限覆寫可能蓋過角色 sandbox。本 scout 試用讓主 Agent 與子 Agent 都在 read-only 下執行，並核對 workspace 雜湊。這不等於已驗證日後可寫主 Agent 下的唯讀角色隔離。

## 四角色與通用子 Agent

四份模板與九種隔離情境均已實作。四角色使用獨立 TOML 的 model / model_reasoning_effort；未配置任何全域 default_subagent_model、default_subagent_reasoning_effort 或主模型預設。

官方 Subagents 文件列出原生 `default` 通用角色：未提供派工模型／reasoning 時，先取 agents 的有效預設，再取父 Agent 值；角色檔中的設定可再覆寫。因此「省略模型欄位」只有在有效預設未改變模型時才能表達預期繼承。試用 home 沒有通用角色檔或覆寫這些預設。

本次開發環境的 `collaboration.spawn_agent` 工具文件另明示 `fork_turns=all` 繼承父模型與 reasoning，且不接受模型覆寫；這是該介面的契約證據，不代表其他 Codex 執行入口使用相同 schema。產品指令要求依實際原生介面選用通用子 Agent，不硬寫未確認的參數到 TOML。固定角色不能只靠 prompt 中的角色名稱假裝載入。

`generic` 情境提供完整 brief、父 Agent 可獨立進行的命名評選工作及成果準則。實際派工、通用繼承、四角色模型、混合權限與並行行為仍須明確啟用 smoke test 後檢閱原生事件；目前全數標記未確認。
