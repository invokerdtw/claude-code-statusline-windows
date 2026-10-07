# claude-code-statusline-windows

**繁體中文** | [English](README.en.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6.svg)](#安裝)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-3776AB.svg)](https://www.python.org/)

以 Windows 為優先的 [Claude Code](https://code.claude.com/docs) 狀態列：兩行就能看到上下文用量、5 小時與 7 天額度、模型、git 分支和 prompt cache 到期時間。只用 Python 標準函式庫，不需要 jq，也不需要 bash。

網路上分享的 statusline 多半是 macOS 上用 bash＋jq 寫的，搬到 Windows 總有一兩個地方對不上：中文路徑變亂碼、黑色視窗一直閃、放在雲端硬碟的專案讓 git 卡死。這個版本是我在 Windows 上每天使用、把這些坑一個一個踩過之後整理出來的。

## 預覽

**正常**：上下文與額度都還寬裕，整條都是綠色。

![正常](docs/images/normal.svg)

**接近上限**：任一條用量到 65% 以上轉黃，提醒你開始留意。

![接近上限](docs/images/warning.svg)

**快爆了**：到 85% 以上轉紅。

![快爆了](docs/images/danger.svg)

**session 剛開始**：Claude Code 還沒送來額度資料時顯示 `--`；之前用過的話，會先顯示上次記下的數值。

![session 剛開始](docs/images/startup.svg)

純文字的樣子（實際畫面有顏色）：

```text
CTX ████░░░░░░ 420k/1.0M 42%  │  5h ███░░░░░ 34% 4h23m  │  7d █░░░░░░░ 12% 5d12h
🤖 Opus 5.5  high  main  +128/-37  my-project  cache→00:43  46m
```

## 功能

| 功能 | 說明 |
|------|------|
| **CTX／5h／7d 三條用量條** | 第一行依序是上下文視窗、5 小時額度、7 天額度。每一格依它代表的百分比上色：未滿 65% 綠、65% 起黃、85% 起紅，所以條子越滿、尾端顏色越暖。只用基本 ANSI 色碼，不需要 24-bit 全彩終端機。門檻可以調整。 |
| **額度重設倒數** | 百分比後面接著顯示離重設還有多久：1 小時內顯示 `42m`，1 天內顯示 `4h25m`，1 天以上顯示 `5d21h`（7 天額度大多是這種格式）。 |
| **上下文 token 數** | `185k/1.0M`：目前上下文中的 token 數／上下文視窗大小。 |
| **模型名稱** | 依模型家族上色（Opus 洋紅、Sonnet 青、Haiku 黃）。用 `/model` 切換後，程式會讀對話紀錄（transcript）中最後一則回覆實際使用的模型 ID，不會停在舊名稱。名稱由模型 ID 直接推出（`claude-opus-5-5` → `Opus 5.5`），新模型推出時不必更新對照表。 |
| **effort／fast 徽章** | 開啟 extended thinking 時顯示目前的 effort 等級（例如 `high`）；開啟 fast mode 時改顯示 `fast`。 |
| **agent／worktree 指示** | 以 `--agent` 執行時顯示 `agent:名稱`；在 worktree session 中顯示 `worktree:名稱`。 |
| **git 分支＋未提交標記** | 分支名稱直接讀 `.git/HEAD`；已追蹤的檔案有未提交變更時加上 `*`（未追蹤的檔案不算）。`*` 的判斷結果每個 repo 快取 5 秒。detached HEAD 時顯示短 SHA。 |
| **本 session 增刪行數** | `+67/-17`，兩者都是 0 時不顯示。 |
| **專案資料夾名稱** | 啟動 Claude Code 時所在的資料夾名稱。 |
| **prompt cache 到期時間** | `cache→14:32` 顯示快取到期的「時鐘時間」：綠色表示還有 5 分鐘以上，黃色表示不到 5 分鐘（以最後一次更新時計算），已過期則顯示 `cache cold`。不用倒數的原因：狀態列不會每秒重畫，只有收到回覆、`/compact` 完成這類事件才會更新，倒數數字停在畫面上很快就是錯的，時鐘時間則一直正確。這個欄位需要 Claude Code v2.1.251 以上。 |
| **session 經過時間** | `28m`、`1h05m` 這類格式。 |
| **burn rate（選配）** | 在 5h 那段後面顯示 `12k/min`（每分鐘 token 數），讓你在額度百分比還沒跳動時也看得出仍在消耗。透過 [ccusage](https://github.com/ryoppippi/ccusage) 取得，需要 Node.js。在背景每 5 分鐘更新一次，不會拖慢狀態列。 |
| **花費（選配）** | `$5.40`，$5 起黃、$10 起紅。給 API 計費的使用者用；這是 Claude Code 依定價估算的金額，不一定等於實際帳單。 |
| **ASCII 模式（選配）** | 用 `#`／`-` 取代方塊字元，用 `\|` 當分隔線，並拿掉 🤖 圖示，給字型顯示不了方塊字元的終端機用。 |

**速度**：平均啟動時間約 47 ms（Windows 11、Python 3.14，以模擬資料連續執行 10 次取平均，未開 burn rate）。git 的 `*` 快取過期、需要重新執行 `git status` 的那一次會比較慢。

## 為什麼要 Windows 版

下面每一項都是我在 Windows 上實際遇到的問題，括號內是程式中處理它的位置。

1. **stdin 編碼**
   Windows 上的 Python 預設用系統的 ANSI 字碼頁（cp1252、cp950 等）解碼 stdin。Claude Code 送來的 JSON 是 UTF-8，路徑裡只要有中文或其他非 ASCII 字元就會變成亂碼。
   → 直接讀位元組，自己用 UTF-8 解碼。（`read_stdin()`）

2. **輸出編碼**
   主控台的字碼頁印不出 `█`、`░` 這類方塊字元和 emoji。
   → 不經過文字層，直接把 UTF-8 位元組寫到 stdout。（`main()`）

3. **黑色視窗閃爍**
   狀態列每次更新都可能啟動 `git.exe` 或 `npx.cmd`，這些主控台程式會閃出黑色視窗。光用 pythonw 執行主程式還不夠，因為它啟動的主控台程式會自己再開一個主控台。
   → 主程式用 `pythonw.exe` 執行，所有子程序再加上 `CREATE_NO_WINDOW` 旗標。（`NO_WINDOW`）

4. **`npx` 是批次檔**
   Windows 上的 `npx` 其實是 `npx.cmd`，subprocess 直接叫 `npx` 會找不到。
   → 在 Windows 上明確呼叫 `npx.cmd`。（`update_usage_cache()`）

5. **雲端同步資料夾讓 git 卡死**
   專案放在 Google Drive 桌面版的串流磁碟上時，git 可能永遠卡在檔案系統呼叫裡：殺不掉、每次更新又多開一個、越積越多，還可能留下 `.git/index.lock`，擋住之後的 commit。
   → 在雲端磁碟上完全不啟動 git，只讀 `.git/HEAD` 取得分支名稱（因此不會顯示 `*`）。Google Drive 以磁碟標籤「Google Drive」辨識。OneDrive 資料夾（依 `OneDrive` 系列環境變數判斷）則是**預防性**略過：`git status` 會觸發隨選檔案（Files On-Demand）下載，所以一併跳過。（`is_cloud_path()`、`branch_from_head()`）

6. **高頻輪詢不搶 index.lock**
   狀態列很常執行 `git status`，如果剛好跟你自己的 commit 撞在一起，就會出現 `index.lock` 衝突。
   → 加上 `--no-optional-locks`，唯讀的 status 不建立 `index.lock`。（`is_dirty()`）

7. **不需要 jq、bash 或 macOS 專用指令**
   許多 statusline 依賴 `jq`、bash 語法，或 macOS 的 `stat -f`。
   → 只用 Python 標準函式庫，裝好 Python 就能跑。

8. **快取的舊額度**
   Claude Code 在每個 session 第一則回覆之前不會送額度資料，所以本工具會快取上次的數值先顯示。但舊數字看起來跟正確的一模一樣，所以快取有兩道關卡：
   - **換了帳號就丟掉**：比對方案欄位（Windows 上 OAuth 憑證是一般檔案 `.credentials.json`，不像 macOS 放在鑰匙圈裡）以及 `/login` 會改寫的帳號 ID（只存雜湊值），同方案的兩個帳號也分得出來。
   - **已經重設的視窗就丟掉**：快取裡的 `resets_at` 已經過了，代表那個額度早就歸零，不再顯示舊的百分比。
   → **只讀方案與帳號 ID 欄位，絕不讀 token。**（`account_fingerprint()`、`resolve_rate_limits()`）

9. **浮點尾差**
   JSON 裡的百分比是浮點數，偶爾會出現 `7.000000000000001%`。
   → 顯示前先取整數。（`fmt_pct()`）

## 安裝

### 前置條件

- Windows 11（我的使用環境）。Windows 10 應該也可以用，但我沒有測試過。
- Python 3.8 以上（從 [python.org](https://www.python.org/downloads/windows/) 安裝的版本會附 `pythonw.exe`）
- [Claude Code](https://code.claude.com/docs)
- 選用：git（顯示未提交標記 `*` 需要它；只顯示分支名稱不需要）
- 選用：Node.js（burn rate 需要）

### 快速安裝

```powershell
git clone https://github.com/invokerdtw/claude-code-statusline-windows.git
cd claude-code-statusline-windows
python install.py --dry-run   # 先看會改什麼，不寫入任何檔案
python install.py
```

沒有 git 的話，也可以用 Download ZIP 下載後在資料夾中執行。

安裝程式會：

1. 把 `statusline.py` 複製到 `%USERPROFILE%\.claude\statusline-windows\statusline.py`
2. 先備份 `settings.json`（`settings.json.bak-statusline-<時間>`），並記下你原本的 `statusLine` 設定，再寫入新的設定
3. 指令中使用 `pythonw.exe` 的絕對路徑；路徑含空白時改用不含空白的短檔名（8.3），電腦停用短檔名時，會依有沒有 Git Bash 寫成 Git Bash 或 PowerShell 都看得懂的格式
4. 保留 `settings.json` 原本的縮排與 BOM，只改 `statusLine` 這一項

打錯參數或加 `--help` 只會顯示說明，不會寫入任何東西。

重開 Claude Code 後生效。

移除：

```powershell
python install.py --uninstall
```

移除時會還原你原本的 `statusLine` 設定（原本沒有就刪掉這個鍵），並刪除 `statusline-windows` 資料夾。如果你安裝之後把 `statusLine` 的指令換成別的，移除時會保留你改的設定，不會蓋回去；只是多加了 `refreshInterval` 之類的欄位，仍會照常還原。若你的設定還在執行本工具資料夾裡的腳本，資料夾會保留下來，避免留下指向不存在檔案的設定。

想請 AI 程式助理代為安裝的話，請它照 [INSTALL_FOR_AI.md](INSTALL_FOR_AI.md) 的步驟做。

### 手動安裝

1. 把 `statusline.py` 複製到 `%USERPROFILE%\.claude\statusline-windows\`。

2. 找出 Python 的安裝位置，`pythonw.exe` 就在同一個資料夾：

   ```powershell
   python -c "import sys; print(sys.executable)"
   ```

3. 編輯 `%USERPROFILE%\.claude\settings.json`，加入（把路徑換成你自己的）：

   ```json
   { "statusLine": { "type": "command", "command": "C:/Users/<你>/AppData/Local/Programs/Python/Python312/pythonw.exe \"C:/Users/<你>/.claude/statusline-windows/statusline.py\"" } }
   ```

4. 重開 Claude Code。

三個細節：

- **路徑用正斜線 `/`**：Windows 上的 Claude Code 有安裝 Git Bash 時會透過 Git Bash 執行這個指令，而 Git Bash 會把沒加引號的反斜線當成跳脫字元，路徑分隔符號被吃掉後指令就會失敗，而且不會顯示錯誤（見[官方文件](https://code.claude.com/docs/en/statusline#windows-configuration)）。正斜線在 Git Bash 和 PowerShell 都能用。
- **路徑含空白時**：例如 Python 裝在 `C:\Program Files\…`。有 Git Bash 的話，前後加上雙引號即可；沒有 Git Bash 時，Claude Code 會改用 PowerShell 執行，這時開頭要加 `& `，寫成 `& "C:/Program Files/…/pythonw.exe" "…/statusline.py"`，否則 PowerShell 會出現語法錯誤，狀態列直接空白。`install.py` 會自動處理這件事。
- **用 `pythonw.exe` 而不是 `python.exe`**：`python.exe` 是主控台程式，`pythonw.exe` 不會開主控台視窗，避免狀態列更新時閃出黑色視窗。

## 設定

所有設定都透過環境變數。用 `setx` 設定後，重開終端機（以及 Claude Code）才會生效：

```powershell
setx CLAUDE_STATUSLINE_BURN_RATE 1
```

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `CLAUDE_STATUSLINE_WARN` | `65` | 從這個百分比起轉黃 |
| `CLAUDE_STATUSLINE_CRIT` | `85` | 從這個百分比起轉紅 |
| `CLAUDE_STATUSLINE_ASCII` | 關 | 設為 `1` 改用純 ASCII 用量條與分隔線，不顯示 emoji |
| `CLAUDE_STATUSLINE_BURN_RATE` | 關 | 設為 `1` 顯示 burn rate（需要 Node.js；第一次執行時 npx 會下載**固定版本**的 ccusage，不會自動跑 npm 上的最新版。抓取失敗時也會等 5 分鐘才重試） |
| `CLAUDE_STATUSLINE_SHOW_COST` | 關 | 設為 `1` 顯示本 session 估算花費 |
| `CLAUDE_STATUSLINE_NO_GIT` | （空） | 不啟動 git 的路徑前綴，多個用分號 `;` 分隔，例如 `D:\Shared;E:\Sync`。以完整資料夾比對（`C:\Work` 不會比對到 `C:\Workspace`），這些路徑下只顯示分支名稱 |
| `CLAUDE_STATUSLINE_GIT_IN_CLOUD` | 關 | 設為 `1` 關閉 Google Drive／OneDrive 的自動偵測，在雲端磁碟上也照常執行 git。`CLAUDE_STATUSLINE_NO_GIT` 列出的路徑仍然不會啟動 git |
| `CLAUDE_STATUSLINE_STATE_DIR` | `%USERPROFILE%\.claude\statusline-windows` | 快取檔（額度、git 狀態、burn rate）存放的資料夾 |

開關類的變數接受 `1`、`true`、`yes`、`on`；要關閉就設成 `0`。

## 運作原理

Claude Code 在 session 開始時，以及之後每次有新的回覆、`/compact` 完成等事件時，會把目前的 session 狀態打包成 JSON，經由 stdin 傳給 `statusLine` 指定的指令；指令印出的內容就是狀態列（詳見[官方文件](https://code.claude.com/docs/en/statusline)）。

用量、額度、倒數、行數、時間這些數字都直接取自這份 JSON，不在本機推算。例外只有三個：模型名稱會再對照 transcript 檔確認、git 狀態讀自你的 repo、burn rate 由 ccusage 計算。

關於額度百分比：依我的觀察，5 小時與 7 天的百分比是「階梯式」更新，大約十幾分鐘才跳一次，不是每則回覆都會變。想看到「現在還在消耗」，可以開 burn rate。

## 測試

```powershell
python -m unittest discover tests   # 單元測試
python examples/mock.py             # 用模擬資料展示各種情境
python examples/mock.py danger      # 只看其中一個情境（normal／warning／danger／startup）
```

## 授權

MIT，詳見 [LICENSE](LICENSE)。

## 致謝與靈感

- [Claude Code 官方 statusline 文件](https://code.claude.com/docs/en/statusline)：JSON 欄位與更新時機都以它為準
- [kcchien/claude-code-statusline](https://github.com/kcchien/claude-code-statusline)：版面與預覽圖的編排給了我很多參考
- [ccstatusline](https://github.com/sirmalloc/ccstatusline)
- [ccusage](https://github.com/ryoppippi/ccusage)：burn rate 的資料來源
