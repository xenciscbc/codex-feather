# 01: 隔離環境與 scout 查找流程

**What to build:** 在隔離 Codex 環境，從使用者提出查找任務，到主 Agent 委派 scout、收回有引用的結果並簡短回報，完成第一條可驗證的分工流程。

**Blocked by:** None (can start immediately).

**Status:** ready-for-human

- [x] 查證當前原生角色格式、生效指令優先順序、角色載入方式及可取得的模型／reasoning 執行證據；記錄適用版本與來源。
- [x] 建立可重用的隔離試用入口，載入候選分工規則與 scout 模板，不修改真實 Codex home、既有角色或 hook。
- [x] scout 預期使用 gpt-5.6-luna／low，保持唯讀；不覆蓋使用者主模型、reasoning 或並行數。
- [ ] 使用有已知答案的查找素材，驗證正確位置、引用與無修改副作用；主 Agent 收回結果並扼要回報。
- [x] 派工包含目標、背景、範圍、限制、產出及完成條件；建立後續角色可沿用的最小派工與回報方式。
- [x] 區分預期、設定值與實際執行證據；缺失時標記未確認，不能聲稱模型綁定已驗證。
- [x] 靜態檢查與使用模型用量的真實測試分開，後者需明確啟用；提供可重現的執行及結果檢查說明。
- [ ] 若原生能力不符契約，記錄阻礙並交回主 Agent，不靜默降級或替換角色模型。

## Comments

2026-09-07：完成候選指令、scout TOML、Python 隔離入口、已知答案素材及四項自動檢查。原生 CLI 0.153.4 的 prompt-input 探測成功載入隔離指令；配置及 workspace 雜湊檢查通過。已勾選項目代表候選實作完成，不代表模型行為驗收。

尚缺明確啟用真實 smoke test、使用者選定的主模型／reasoning，以及隔離登入。實際角色載入與 scout 模型綁定未確認。Thread schema 的 model/reasoningEffort 是配置 metadata，不是執行 telemetry；見 `docs/native-compatibility.md`。本票尚未 resolved，後續依賴票保持原狀。

目前專案沒有 `.git`。無法完成 implement 要求的 current-branch commit，也無法提供 code-review 技能要求的非空 Git diff；已人工核對候選實作與規格並修正隔離專案根目錄問題，不能視為該技能審查通過。

2026-09-07 全部實作：本票所需模板、規則、素材、入口與驗收準則已交付，對照 docs/validation.md。使用者明確要求全部實作，故完成所有可建置交付物，保留真實模型驗收依賴。已勾選項目表示實作層完成；未勾選的實際派工、模型、權限及整合行為尚待明確啟用 smoke test，不能宣稱已驗收或 resolved。
