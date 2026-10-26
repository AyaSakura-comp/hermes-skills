---
name: switch-qwen-model
description: 切換本機互斥的 Qwen 模型服務（Qwen 3.6 35B qwen-mtp :8001 ↔ Qwen 3.8 Flash Strata :8090），並同步修改 pi agent 的 defaultProvider/defaultModel 與 piscord（pi-discord-gateway）的 PI_MODEL。當使用者說 /switch-qwen-model、「切換 qwen 模型」、「切到 3.6」、「切到 3.8」、「換回 3.6」、「switch to 3.8 flash」或要求更換 pi／piscord 預設本地模型時使用。
---

# Switch Qwen Model (3.6 ↔ 3.8 Flash)

本機兩個 Qwen 引擎**互斥**（同時運行必定 OOM），切換時必須「停一個、開另一個」，
並同步更新 pi 與 piscord 的預設模型設定。

| 目標 | 服務 | Port | pi provider | pi model id | piscord `PI_MODEL` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **3.6** | `qwen-mtp.service`（system systemd） | 8001 | `local-llama` | `qwen3.6-35b-q4` | `local-llama/qwen3.6-35b-q4` |
| **3.8** | `strata.service`（**user** systemd） | 8090 | `local-strata` | `qwen3.8-flash` | `local-strata/qwen3.8-flash` |

## 操作方式

一律使用技能內腳本（具備健康檢查與 settings.json 自動備份）：

```bash
bash ~/.pi/agent/skills/switch-qwen-model/scripts/switch-qwen-model.sh 3.6     # 切到 Qwen 3.6
bash ~/.pi/agent/skills/switch-qwen-model/scripts/switch-qwen-model.sh 3.8     # 切到 Qwen 3.8 Flash (Strata)
bash ~/.pi/agent/skills/switch-qwen-model/scripts/switch-qwen-model.sh status  # 查看目前狀態
```

腳本流程：停止對方服務 → 啟動目標服務 → 等待 `/health`（最長 3 分鐘，Strata 載入需數十秒）
→ 備份並更新 `~/.pi/agent/settings.json` 的 `defaultProvider`/`defaultModel`
→ 備份並更新 `~/.config/pi-discord-gateway/config.env` 的 `PI_MODEL`，若 `pi-discord-gateway.service`
正在運行則 `systemctl --user restart` 讓新模型生效（未運行則下次啟動自動生效）。

3.8 的 health 判斷是 Strata `/health` 的 `"loaded": true`，不是只看 wrapper 有回應：
Strata 的 wrapper 在 engine 死掉（例如 exit -9）或被 unload 時仍會回 `/health` 200、
service 也仍是 active，只有下一個請求才會重新載入 engine（一兩分鐘，再加上冷的 prompt 讀取）。
腳本在 engine 沒載入時會呼叫 Strata 的 `POST /load` 先載好，切換完成時第一個請求就不會卡住。

**piweb 不需要重啟。** piweb worker 每次執行時都會重新讀 `~/.pi/agent/settings.json`
的預設模型：沒有指定模型的對話會用新的預設模型重新啟動 pi（`--model <預設>`），
不會沿用 pi session 檔裡存的舊模型；已經常駐的閒置 pi 程序也會在下一則訊息時自動換掉。
有手動選過模型（override）的對話則維持原本的選擇，若選的是已停止的那個本地模型，
需在該對話用模型選單改選。切換後不要跑 restart-piweb（會重建網頁容器，
把熱部署的前端檔案還原掉），也不要重啟 piweb-worker。

注意：piscord 各頻道若有 per-channel session 記住的模型，切換後該頻道可能仍沿用舊模型，
需在該頻道用 `/model` 重選或開新 session。

## 規範

- **禁止** `kill`/`pkill`/`killall` 引擎 process（qwen-mtp 與 strata 均為受保護服務）；只能透過 `systemctl` / `systemctl --user` 操作。
- qwen-mtp 用 system systemd（`sudo systemctl`）；strata 用 user systemd（`systemctl --user`），不要混用。
- 若切換後 health check 逾時：3.8 查 `journalctl --user -u strata -n 50`（或 `/home/chihmin/src/Strata/strata-iq3_s.log`）；3.6 查 `journalctl -u qwen-mtp -n 50`。
- 第一個請求慢不代表 piweb 壞了：先跑 `status`，看 3.8 是否顯示 `engine loaded`。
- 若使用者只要查狀態不要切換，跑 `status` 即可，不要動服務。
- 3.8 的圖片：`status` 會顯示 `images: true|false`（Strata `/health` 的 `images`）；切到 3.8 時腳本會把 pi `models.json` 的 local-strata `input` 同步成 Strata 實際能力（有 encoder → `[text,image]`）。圖片要能用，`strata-iq3_s.json` 需同時有 `"vision"` 段落**和** engine args 的 `--vision`（缺後者會回 400 `this engine was started without --vision`）。
- 切換完成後向使用者回報：哪個服務 active、health 結果（3.8 要是 engine loaded，並附 images 狀態）、pi 預設模型新值、piscord PI_MODEL 新值與 gateway 是否已重啟。
