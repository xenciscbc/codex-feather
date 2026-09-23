# 原生 plugin 與 setup 驗證

日期：2026-09-23。環境：Windows、Python 3.11、Codex CLI `0.155.0-alpha.16`。這次新增 plugin manifest、Git marketplace、`feather-setup` skill 與既有安裝器的來源入口；沒有修改使用者的全域安裝，也尚未發布遠端版本。

## 自動驗證

在 repository 根目錄執行：

| 命令 | 結果 |
| --- | --- |
| `python -m unittest discover -s tests -p test_plugin_setup.py -v` | 9 項通過 |
| `python -m unittest discover -s tests -p test_setup.py` | 59 項完成，57 通過、2 略過 |
| `python -m unittest discover -s tests -p test_trial.py` | 19 項通過 |
| Plugin creator 的 `validate_plugin.py .` | 通過 |
| Skill creator 的 `quick_validate.py skills/feather-setup` | 通過 |
| Plugin creator 的 `read_marketplace_name.py --marketplace-path .agents/plugins/marketplace.json` | `codex-feather` |
| `python -m mypy --cache-dir dist/plugin-mypy-cache scripts/setup_installer scripts/feather_setup.py scripts/build_setup.py skills/feather-setup/scripts/setup.py` | 18 個來源檔案通過 |
| `git diff --check` | 通過 |

安裝器測試透過 `FEATHER_TEST_CODEX` 指定上述原生執行檔；略過項目為獨立二進位的無 Python 路徑驗證，以及 Windows 使用者 skill 的另行 profile 測試。mypy 使用既有 `.scratch/feather-improvements/dev-deps`，沒有安裝新套件。mypy 提醒既有未標註函式的內文未檢查，不能將結果視為完整 strict 型別驗證。

新測試從不含 Git 資料的隔離 plugin 副本與無關 cwd 執行 setup，覆蓋：dry-run 不修改目標、專案與使用者範圍、更新採新 plugin 模板、移除與範圍遷移、既有 handoff 保全、顯式舊版 handoff 清理、來源不明角色衝突、禁止重複安裝 handoff、缺少 PyYAML 時停止，以及 plugin 快取不產生 bytecode 或被改寫。測試沒有以環境變數禁止 bytecode 來掩蓋快取保護行為。

## 原生 CLI 路徑

在忽略目錄 `dist/plugin-native-20260923/` 下建立獨立 Codex home、專案與本機 marketplace。未複製帳戶憑證，也未送出真實模型工作。

1. `plugin marketplace add` 註冊本機 fixture marketplace，`plugin add codex-feather@feather-native-trial` 成功安裝 `1.1.0` 至隔離 plugin cache。
2. `debug prompt-input` 顯示 `feather-handoff` 與 `feather-setup`，路徑指向 cache 的 `skills/`。
3. 直接執行 cache 裡的 setup，成功部署隔離專案的四角色與分工入口。
4. 未設定信任的第一次工具註冊未包含角色；加入隔離專案的信任設定與根目錄標記後，透過本機 HTTP 測試端點捕捉的原生工具註冊包含四角色。端點立即回覆測試錯誤，不執行模型。產品 setup 沒有修改專案信任。
5. 加入舊式專案 handoff skill 後，prompt input 同時列出兩個 handoff 來源。這支持 skill 的「先辨識來源、明確切換」流程，不宣稱同名情境會自動選到正確副本。
6. 僅將 fixture plugin 版本改為 `1.1.1`，再次 `plugin add` 成功建立新版 cache。這是本機來源重新安裝驗證，不代表 Git marketplace 遠端更新或所有相同版本快取策略均已驗證。
7. Repository 新增的 Git URL marketplace catalog 也由原生 `plugin marketplace add` 成功解析及註冊；尚未從 GitHub 安裝本次未發布內容。

`dist/` 中保留此次 stdout、stderr 與本機註冊請求，供本機查核；它們不是發行包。Linux、公開 plugin directory 上架、真實模型派工與逐回應模型 telemetry 未驗證。

## 分工證據

主 Agent 完成產品實作與整合；analyst 檢查既有安裝、重複技能與入口所有權，executor 負責隔離測試。原生派工設定為 analyst `gpt-6-sol/high`、executor `gpt-6-sol/medium`，來自目前角色預設；子 Agent 回傳與測試結果已由主 Agent 檢閱。首次誤用舊模型的 analyst 派工已中止，未採用其成果。工具接受的設定不等於服務端逐回應 telemetry，實際執行模型仍未確認。

另由獨立 executor 只取得 skill、隔離路徑與「專案安裝後移除角色，保留個人指引和交接資料」請求，完成 skill 前向試用。`dist/setup-skill-trial/` 的安裝／移除預覽及安裝後健檢成功；移除後健檢如預期回報角色缺少，沒有誤報仍已安裝。原指引與 handoff marker 的雜湊未變。主 Agent 核對最終檔案、空的元件所有權紀錄與備份；本輪沒有真實模型工作或全域部署。
