# Feather MVP

## Notes

- 2026-09-07 使用者明確要求全部實作，已交付 [01](issues/01-isolated-scout-flow.md) 至 [06](issues/06-integrated-delegation-acceptance.md) 的四角色、共用指令、九情境與驗收入口。
- 票據 ready-for-human 表示實作完成、真實模型驗收待啟用；不是驗收通過或 resolved。
- 交付及驗證界線見 docs/validation.md。專案已建立本地 Git 審查基準，後續提交不涉及遠端發布。

## Decisions-so-far

- 角色配置仍依 spec.md；沒有新增固定角色或改變主模型偏好。
- 實作可先完成，真實模型驗收依賴保留，避免把缺失執行證據當成成功。

## Fog

- 真實 smoke test 需明確啟用、使用者選定的主模型／reasoning 及隔離登入。
- 四角色實際綁定、通用繼承、混合權限與原生調度行為尚待執行證據。
