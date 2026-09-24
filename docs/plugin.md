# Feather 原生 plugin

Feather 的原生 plugin 包含 `handoff`、`setup`、`model`、`auto-on` 與 `auto-off`。Plugin 管理這些 skills 的取得與載入；setup skill 呼叫既有安裝器，分別管理 handoff 自動維護入口，以及五角色 TOML、delegation 執行時 skill 與精簡分工入口；model skill 引導修改角色模型與推理強度。沒有自動安裝 hook，也不會在安裝 plugin 時修改全域指引。

## 安裝與首次設定

下列遠端命令需在包含 marketplace 與 plugin manifest 的版本推送後使用；舊版 `v1.0.1` 不含 plugin。

```powershell
codex plugin marketplace add xenciscbc/codex-feather
codex plugin add codex-feather@codex-feather
```

開新 session，確認五個 skills 列出，再說：「使用 setup」。LLM 先列出目前專案與使用者範圍的兩項元件狀態，包括來源、規則入口與衝突，再詢問要執行的操作、元件與範圍。只要求查詢時不會安裝。也可直接說「只在目前專案安裝 handoff 自動維護規則」、「全域安裝分派規則與 agent」或「在目前專案安裝兩者」；已指定的選擇不會重複詢問。

`handoff` 管理交接自動維護入口，使用 plugin 已提供的 skill；已有工作交接時，依其規則在重要進展、受阻與完成時更新。`delegation` 同時管理五角色檔案、執行時 skill 與分派入口；`all` 表示兩者。兩項可使用不同範圍，安裝、更新、遷移與移除互不綁定。套用前列出所選範圍的預覽，套用後核對結果；確認角色、skill 與指引載入仍需新 session。

Setup 的來源執行需要 Python 3.11+ 與 PyYAML；相依清單為 plugin 根目錄的 `requirements-setup.txt`。LLM 先沿用合適的 Python 環境；缺少套件時先取得安裝授權。這條路徑不要求 PyInstaller 或 mypy；既有獨立二進位安裝方式仍可使用。

### 分別管理元件

以下 `<setup.py>` 代表 plugin 內 `skills/setup/scripts/setup.py` 的絕對路徑。修改操作必須明確選擇 `--components handoff`、`delegation` 或 `all`；`check` 未指定時檢查兩者。新安裝未指定 `--entrance` 時，規則入口跟隨 `--scope`；更新保留原入口。Delegation 可明確用 `--entrance none` 只裝角色；plugin handoff 本身已可使用，選用 setup 的 handoff 元件則是要安裝維護入口。

```powershell
# 先檢查兩個範圍
python '<setup.py>' check --project 'D:/work/my-project' --scope project --json
python '<setup.py>' check --project 'D:/work/my-project' --scope user --json

# 單獨安裝 handoff 規則；將 --dry-run 移除後套用
python '<setup.py>' install --project 'D:/work/my-project' --scope project --components handoff --dry-run --json

# 同時安裝兩者
python '<setup.py>' install --project 'D:/work/my-project' --scope project --components all --dry-run --json

# 單獨更新 agent 與分派規則
python '<setup.py>' update --project 'D:/work/my-project' --scope project --components delegation --dry-run --json

# 只移除 handoff 維護規則，保留分派設定與交接資料
python '<setup.py>' remove --project 'D:/work/my-project' --scope project --components handoff --dry-run --json
```

新安裝兩者同範圍時是一筆交易；若分別選擇專案 handoff 與全域 delegation，則各自預覽與執行。Plugin handoff 的檢查會區分 skill 來源、已受管理入口及尚未確認的 session 載入；不以 plugin 檔案存在推定入口已安裝。

## 自動計畫審查

封裝預設為 off。使用 `$auto-on` 或 `$auto-off`，不帶參數或選 `session` 只影響這段對話，不寫檔；選 `project` 或 `user` 才保存到已有所有權紀錄的安裝。持久設定由 `scripts/feather_review.py` 的 show、preview、apply 管理，apply 要帶預覽的 `--expected-plan`。更新保留設定。沒有已擁有的安裝時先執行 setup，不會因切換模式而自動安裝。詳細規則見 [審查模式](../skills/setup/references/auto-review.md)。

Auto 只對重大安全邊界變更、資料遷移、不可逆操作及複雜跨模組工作觸發；同一邏輯計畫最多兩次自動審查，包含失敗呼叫。明確要求的計畫審查不受 off 模式阻止。此流程靠 Agent 指引，不是 hook 強制。

## 更新

角色模型與推理強度使用 `model` 調整：先列出現況，再選擇欄位，最後選擇 session 或永久。Session 只影響後續派工；永久設定寫入角色擁有者的安裝紀錄與受管理指引，隨 setup 更新與遷移保留。全域角色的永久變更會影響共用安裝的專案；工具先預覽實際範圍，遇到所有權或入口衝突則停止，不改寫角色 TOML 的模型欄位。詳見 [README 的模型設定流程](../README.zh-TW.md#修改角色模型)。

目前永久修改要求角色有可驗證的安裝紀錄，且分工入口與角色在同一範圍、只有一個擁有者。缺少入口、跨範圍入口、共享入口或其他可見分工入口時，先依診斷處理原安裝；工具不會自行遷移或接管檔案。沒有入口時，查詢列出的值會標示為封裝預設，不能視為正在生效的派工設定。

```powershell
codex plugin marketplace upgrade codex-feather
```

Marketplace 追蹤 Git 來源；重新載入後確認實際安裝的 plugin 版本與技能路徑。需要時從原生 plugin 管理介面重新安裝，再開新 session。不要只由 marketplace 更新成功便推定快取內容或外部設定已更新。

接著說：「使用 setup，同步全域的新版角色與分工規則」，或明確要求同時更新 handoff 維護規則。Skill 使用新 plugin 內的模板，對所選元件執行 `update --dry-run`，處理差異後套用；原有安裝器會更新所有權紀錄及備份。兩項元件可分別更新；其他專案的獨立部署須在其原始專案範圍分別更新。

共用分工入口可由已登記的角色擁有者升級封裝預設值，影響所有共用該入口的專案；預覽會列出共用入口路徑，並保留其擁有者清單。新加入或僅沿用角色的安裝不能改寫共用入口的模型表格。這與 `model` 的永久自訂不同：永久自訂仍要求單一入口擁有者，手動修改過的入口仍依衝突流程處理。

## 既有安裝與移除

- 原本的四角色可由新版 setup 在原有擁有者範圍更新為五角色，不需要先刪除。
- Plugin 已提供交接 skill；setup 的 `handoff` 安裝、更新與遷移管理其自動維護入口，不部署另一份 skill。修改時必須明確選擇元件。
- 既有獨立交接 skill 保持原樣；切換至 plugin 時先確認 plugin skill 能載入，再依原安裝紀錄清理獨立副本。自訂或來源不明的檔案會保留並回報。移除共用副本會影響其他專案，需要納入使用者的切換範圍。
- 切換來源後，可選擇安裝 plugin handoff 的 `AGENTS.md` 維護區塊。Delegation 單獨安裝不會建立 handoff 區塊；單獨移除 handoff 維護規則也不會移除 plugin skill。
- 移除 Feather 時，先讓 setup 清理授權範圍內的外部角色與入口，再移除 plugin。停用或移除 plugin 本身不會執行清理工具。`.feather/handoffs/` 與歷史資料保留。

## 封裝與維護

Repository 根目錄就是完整 plugin：`.codex-plugin/plugin.json` 指向 `skills/`，setup entry 位於 `skills/setup/scripts/setup.py`，從所在位置定位根目錄的 `scripts/`、`templates/` 與 `docs/`。發行時保留完整樹；不可只複製 setup 的 `SKILL.md`。根目錄 `.agents/plugins/marketplace.json` 使用 Git URL 指向同一 repository 的 `master`，供原生 marketplace 發布。

Setup 將來源素材組成暫存離線 bundle，再呼叫同一個 `setup_installer`。暫存內容的 checksum 只驗證複製的一致性，不是獨立的發布簽章。版本取自 plugin manifest；安裝器程式本身仍有獨立版本。入口不在 plugin cache 寫入 bytecode、安裝紀錄或 build 目錄。

這是 Codex 本機 CLI/app 的 Git marketplace 發布方式，不等於已提交 OpenAI 公開 plugin directory，也不宣稱支援所有 ChatGPT 執行環境。

原生規格參考：[Plugin 封裝與 marketplace](https://developers.openai.com/plugins/build/plugins)、[自訂角色](https://learn.chatgpt.com/docs/agent-configuration/subagents)。完整外部設定的範圍、衝突與復原規則見 [安裝器指南](setup.md)。

已測流程、環境及未驗證項目見 [plugin 驗證紀錄](plugin-validation.md)。
