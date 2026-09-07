# 原生相容性查證

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
