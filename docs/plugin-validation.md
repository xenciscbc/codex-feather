# 原生 plugin 與 setup 驗證

## Setup 元件獨立管理（2026-09-23）

新版來源的 plugin setup 支援分別選擇 `handoff`、`delegation` 或 `all`。Handoff 管理 plugin skill 的自動維護入口與來源紀錄；delegation 管理五角色及分派入口。所有測試在隔離專案與 home 執行，沒有更新實際全域安裝。

| 驗證 | 結果 |
| --- | --- |
| `python -B -m unittest discover -s tests` | 258 項：255 通過、3 略過；本機紀錄 `dist/setup-components-validation/regression.log` |
| 補充兩個 plugin 案例 | 同時安裝遇角色衝突時零變更、單獨更新 handoff 保留 delegation 檔案／紀錄／入口，均通過 |
| mypy：安裝器、建置入口及 plugin setup | 20 個來源檔案通過；沿用既有非 strict 設定 |
| setup skill validator、`git diff --check` | 通過 |

此次驗收涵蓋 260 個測試案例，257 通過、3 略過。覆蓋單選／全選、部分移除、無重複 skill、零角色的 handoff 安裝、停用 agents 時仍可安裝 handoff、舊版來源衝突、入口位置保留、plugin 來源更新、交接資料保全及無元件檔案的 handoff 規則遷移。互動測試核對先選專案與顯示兩個範圍的狀態，再詢問操作，並保留已指定的選擇。

主 Agent 完成操作指引、互動流程與整合驗收；executor 實作元件管理，analyst 唯讀檢查七種請求的操作路徑。主 Agent 核對變更範圍及 analyst 來源的完整 SHA-256，並補上一般更新保留既有 standalone 來源的指引。派工設定為 executor `gpt-6-sol/medium`、analyst `gpt-6-sol/high`，工具接受設定；服務端逐回應模型證據未取得。未重建獨立二進位包，也未驗證新指引在真實新 session 自動維護交接的行為。

同日審查後另重現並修正三項問題：plugin handoff 遷移漏查來源範圍的未受管理獨立 skill；異常 handoff 路徑使查詢中止、遺失正常 delegation 結果；受管理 standalone handoff 被 plugin 查詢誤報為衝突，且未呈現其入口。三個新增測試均先確認失敗，再驗證修正成功。安裝與遷移共用本地 handoff 路徑及所有權檢查，並將讀取納入交易基準；既有 standalone 的查詢沿用其安裝紀錄與入口。

Standards 審查的詞彙缺口已補入 `CONTEXT.md`，重複衝突邏輯已集中；入口預設參數的簡化建議暫不採用，保留既有呼叫介面，以重複安裝與明確 `none` 測試核對行為。Spec 審查指出的 standalone 狀態錯誤已修正。兩名 analyst 皆唯讀，主 Agent 已核對來源 SHA-256、重現與修正；實際服務端模型仍未確認。

修正後重跑 `test_plugin_setup`、`test_setup`、`test_setup_interactive`、`test_upgrade_short_names`：99 項中 97 通過、2 略過，本機紀錄為 `dist/setup-components-validation/review-regression.log`。20 個來源檔案的 mypy 與差異格式檢查通過。

### 跨範圍來源與預檢隔離修正

後續審查重現兩項問題並修正：可見範圍已有零檔案的 plugin handoff 紀錄時，獨立安裝器仍新增副本；互動預檢遇到另一範圍損壞的紀錄時，連不相關的正常操作也被中止。

獨立 handoff 的安裝、更新與遷移現在核對使用者及可見專案／祖先的 provider 紀錄；有效的 plugin 所有權仍需明確處理，不能因沒有獨立 skill 檔案就視為未安裝。紀錄讀取集中於 `setup_installer/state.py`，拒絕損壞的格式、元件或 provider 結構。互動預檢逐範圍顯示錯誤及正常結果；實際操作仍做原有檢查，選中損壞範圍時不寫入。專案路徑與素材包錯誤仍提前停止。

`test_provider_scope`、`test_plugin_setup`、`test_setup`、`test_setup_interactive`、`test_upgrade_short_names`、`test_review_settings` 合計 114 項中 112 通過、2 略過；本機紀錄為 `dist/setup-components-validation/scope-fixes-regression.log`。之後補充一項損壞 provider 結構的案例，再跑四項 provider scope 測試均通過。21 個來源檔案的 mypy 通過。測試涵蓋全域／專案雙向及祖先衝突、CLI 零變更拒絕、保留損壞的未選紀錄，以及選中損壞紀錄時停止寫入。主 Agent 完成來源檢查與整合，executor 負責預檢隔離；均使用隔離目錄，未更新實際全域安裝。

以下保留先前版本的驗證紀錄。

日期：2026-09-23。環境：Windows、Python 3.11、Codex CLI `0.155.0-alpha.16`。這次新增 plugin manifest、Git marketplace、`feather-setup` skill 與既有安裝器的來源入口；沒有修改使用者的全域安裝，也尚未發布遠端版本。

## 自動驗證

在 repository 根目錄執行：

| 命令 | 結果 |
| --- | --- |
| `python -m unittest discover -s tests -p test_plugin_setup.py -v` | 12 項通過（含參數解析與 Git 快取保全回歸測試） |
| `python -m unittest discover -s tests -p test_setup.py` | 59 項完成，57 通過、2 略過 |
| `python -m unittest discover -s tests -p test_trial.py` | 19 項通過 |
| Plugin creator 的 `validate_plugin.py .` | 通過 |
| Skill creator 的 `quick_validate.py skills/setup` | 通過 |
| Plugin creator 的 `read_marketplace_name.py --marketplace-path .agents/plugins/marketplace.json` | `codex-feather` |
| `python -m mypy --cache-dir dist/plugin-mypy-cache scripts/setup_installer scripts/feather_setup.py scripts/build_setup.py skills/setup/scripts/setup.py` | 18 個來源檔案通過 |
| `git diff --check` | 通過 |

安裝器測試透過 `FEATHER_TEST_CODEX` 指定上述原生執行檔；略過項目為獨立二進位的無 Python 路徑驗證，以及 Windows 使用者 skill 的另行 profile 測試。mypy 使用既有 `.scratch/feather-improvements/dev-deps`，沒有安裝新套件。mypy 提醒既有未標註函式的內文未檢查，不能將結果視為完整 strict 型別驗證。

新測試從不含 Git 資料的隔離 plugin 副本與無關 cwd 執行 setup，覆蓋：dry-run 不修改目標、專案與使用者範圍、更新採新 plugin 模板、移除與範圍遷移、既有 handoff 保全、顯式舊版 handoff 清理、來源不明角色衝突、禁止重複安裝 handoff、缺少 PyYAML 時停止，以及 plugin 快取不產生 bytecode 或被改寫。測試沒有以環境變數禁止 bytecode 來掩蓋快取保護行為。

Review 發現兩層 parser 對縮寫的解讀不同：`remove --comp handoff` 會被補上的預設值改成移除 delegation；混用完整與縮寫選項也能繞過 handoff 安裝限制。修正後底層安裝器同樣關閉選項縮寫，未知選項在執行操作前以參數錯誤退出。新增回歸測試覆蓋混合選項的兩種順序、`--comp=all` 與 `--comp=handoff`，以實際非 dry-run 呼叫及目標檔案前後比較確認沒有寫入或刪除；完整的 `--components handoff` 仍能正常執行。

後續從 GitHub 安裝已發布的 `e444ae9` 時，marketplace、plugin 安裝與技能載入均成功，但發現原生 Git cache 保留 `.git`；setup 共用的 build metadata 探測會因 `git status` 更新 `.git/index`。已在 Git 命令停用 optional locks。新增測試建立真實 Git index，再改動已追蹤模板的時間戳，確認 `check` 與 install `--dry-run` 都保持整份快取及目標檔案內容不變；最後以一般 `git status` 確認同一 fixture 確實會刷新 index，避免假陽性。修正前測試會失敗，修正後 12 項 plugin 測試、18 個檔案的 mypy 與來源離線 bundle 建置通過。此項修正尚未包含在上述已發布提交內。

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

## feather-model（plugin 1.2.0）

同日新增模型設定 skill、JSON 查詢／預覽／套用工具，並更新中英文 README。永久設定存入 delegation 安裝紀錄，更新受管理表格；role TOML 維持可由原生 spawn 參數覆寫。此段是本機來源驗證，不表示已發布或更新使用者的全域安裝。

| 驗證 | 結果 |
| --- | --- |
| `python -m unittest tests.test_model -v` | 11 項通過 |
| `python -m unittest discover -s tests -p test_setup.py` | 59 項完成，57 通過、2 略過 |
| `python -m unittest discover -s tests -p test_plugin_setup.py` | 12 項通過 |
| mypy：既有來源範圍加 `skills/model/scripts/model.py` | 20 個來源檔案通過；既有未標註函式仍非 strict 檢查 |
| Plugin validator、兩個 setup/model skill validator | 通過 |
| `build_setup.py --prepare-only` 與 payload SHA-256 | 通過，包含新增 runtime 的來源摘要 |

模型測試覆蓋單欄修改、預覽無寫入、plan 不符拒絕套用、重裝與更新保留設定、project → user 遷移、沿用使用者安裝、共享入口不覆寫模型值、異名角色與原生模型鎖定衝突、缺少入口／所有權、缺少相依套件的 JSON 錯誤，以及查詢／預覽不修改隔離 plugin cache 或產生 bytecode。

獨立 executor 依新 skill 在 `dist/model-skill-trial/` 執行「scout 推理強度改成 medium，永久保存」，驗證預覽、套用、再次查詢及 setup 更新後仍保留 `gpt-6-luna / medium`。接著評估「executor 改成 high，只限這次 session」，未執行寫入或派工。主 Agent 已核對報告、實際安裝表格及 14 個檔案的 SHA-256；session 前後清單相同。工具接受模型 ID 不代表 provider 支援，skill 仍須核對原生可用組合；未驗證真實子 Agent 的模型 telemetry。

主 Agent 完成 skill、文件與整合，executor 負責設定工具與獨立試用；兩次委派均顯式要求 `gpt-6-sol / medium`，符合角色預設。已核對回傳範圍與成果，沒有取得逐回應服務端模型證據。
