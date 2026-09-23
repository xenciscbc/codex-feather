# Feather 原生 plugin

Feather 的原生 plugin 包含 `feather-handoff` 與 `feather-setup`。Plugin 管理 skills 的取得與載入；setup skill 呼叫既有安裝器，管理 plugin 外部的四角色 TOML 與分工入口。沒有自動安裝 hook，也不會在安裝 plugin 時修改全域指引。

## 安裝與首次設定

下列遠端命令需在包含 marketplace 與 plugin manifest 的版本推送後使用；舊版 `v1.0.1` 不含 plugin。

```powershell
codex plugin marketplace add xenciscbc/codex-feather
codex plugin add codex-feather@codex-feather
```

開新 session，確認 `feather-handoff` 與 `feather-setup` 列出，再說：「使用 feather-setup，將 Feather 設定為全域使用」或「只設定目前專案」。LLM 會檢查既有部署，預覽並套用指定範圍的角色與入口，再執行健檢。確認角色載入仍需新 session。

Setup 的來源執行需要 Python 3.11+ 與 PyYAML；相依清單為 plugin 根目錄的 `requirements-setup.txt`。LLM 先沿用合適的 Python 環境；缺少套件時先取得安裝授權。這條路徑不要求 PyInstaller 或 mypy；既有獨立二進位安裝方式仍可使用。

## 更新

```powershell
codex plugin marketplace upgrade codex-feather
```

Marketplace 追蹤 Git 來源；重新載入後確認實際安裝的 plugin 版本與技能路徑。需要時從原生 plugin 管理介面重新安裝，再開新 session。不要只由 marketplace 更新成功便推定快取內容或外部設定已更新。

接著說：「使用 feather-setup，同步全域的新版角色與分工規則」。Skill 使用新 plugin 內的模板執行 `update --dry-run`，處理差異後套用；原有安裝器會更新所有權紀錄及備份。其他專案的獨立部署須在其原始專案範圍分別更新。

## 既有安裝與移除

- 原本的四角色可由 setup 在原有擁有者範圍更新，不需要先刪除。
- Plugin 已提供交接 skill，因此 setup 預設只處理 `delegation`。`handoff` 的 install/update/migrate 在 plugin 入口會被拒絕，避免再裝一份。
- 既有獨立交接 skill 保持原樣；切換至 plugin 時先確認 plugin skill 能載入，再依原安裝紀錄清理獨立副本。自訂或來源不明的檔案會保留並回報。移除共用副本會影響其他專案，需要納入使用者的切換範圍。
- Plugin 發現交接 skill 取代舊交接入口的提示作用；delegation setup 不會另建立 handoff 的 `AGENTS.md` 區塊。
- 移除 Feather 時，先讓 setup 清理授權範圍內的外部角色與入口，再移除 plugin。停用或移除 plugin 本身不會執行清理工具。`.feather/handoffs/` 與歷史資料保留。

## 封裝與維護

Repository 根目錄就是完整 plugin：`.codex-plugin/plugin.json` 指向 `skills/`，setup entry 位於 `skills/feather-setup/scripts/setup.py`，從所在位置定位根目錄的 `scripts/`、`templates/` 與 `docs/`。發行時保留完整樹；不可只複製 setup 的 `SKILL.md`。根目錄 `.agents/plugins/marketplace.json` 使用 Git URL 指向同一 repository 的 `master`，供原生 marketplace 發布。

Setup 將來源素材組成暫存離線 bundle，再呼叫同一個 `setup_installer`。暫存內容的 checksum 只驗證複製的一致性，不是獨立的發布簽章。版本取自 plugin manifest；安裝器程式本身仍有獨立版本。入口不在 plugin cache 寫入 bytecode、安裝紀錄或 build 目錄。

這是 Codex 本機 CLI/app 的 Git marketplace 發布方式，不等於已提交 OpenAI 公開 plugin directory，也不宣稱支援所有 ChatGPT 執行環境。

原生規格參考：[Plugin 封裝與 marketplace](https://developers.openai.com/plugins/build/plugins)、[自訂角色](https://learn.chatgpt.com/docs/agent-configuration/subagents)。完整外部設定的範圍、衝突與復原規則見 [安裝器指南](setup.md)。

已測流程、環境及未驗證項目見 [plugin 驗證紀錄](plugin-validation.md)。
