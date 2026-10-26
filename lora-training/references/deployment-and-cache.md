# 可回復部署、MTP 與 KV 快取

## 部署不能偷渡進訓練授權

先取得production變更範圍；服務檢查／修復／restart走 `~/.hermes/skills/restart-service/SKILL.md`。不從歷史PID判斷當前狀態；不直接kill llama-server。

順序：
1. 離線export，tensor equivalence。
2. 用不同port／owned temporary service做base/adapter paired smoke。
3. 測tool schema、固定歷史年份、合成時鐘、簡單運算、急迫建議；保留token cap／未核實回答。
4. 測context配置與並行；短prompt成功不是滿context品質。
5. 記錄production原argv、binary、base、env、drop-ins與rollback。
6. 經授權安裝可獨立移除的adapter override，不merge base。
7. 驗證實際argv diff、health、adapter path/scale、tool call、MTP結果。
8. 記錄已部署的checkpoint及為何選它；未做排名就不說best。

歷史Qwen部署只新增：
- `--lora /home/chihmin/models/qwen-agentic-lora-v11/agentic-v11-final-f32.gguf`
- `--slot-save-path /home/chihmin/.cache/llama-slots-agentic-v11/`

override：`/etc/systemd/system/qwen-mtp.service.d/zzzz-agentic-lora-v11.conf`。這是案例定位，不是叫新工作覆寫同一檔。

rollback只撤回自己新增的override，經hub reload/restart；保留adapter／checkpoints，不能刪其他drop-ins。安裝前保存原檔，安裝後verify argv。

## MTP／FlashHead

同一binary不表示相同execution path。須看exact source commit與實際runtime：
- adapter是否傳進target？draft？
- FlashHead fast-path有無`loras->empty()`等條件？
- target保持dense，draft仍可能FlashHead，兩者不能混稱。
- draft18/accepted18的單次短測試，不是長期100%接受率或速度證據。

需要比較速度時交給ab-qwen-profiling；需要kernel歸因時交給rocm-kernel-trace，不從程式碼猜measured TPS。

## 路徑所有權：server vs client

**Server**的`--slot-save-path`決定實際snapshot檔案位置。Pi POST save/restore只傳sanitized filename；client `cacheDir`不能覆寫server實際目錄。

**Client**使用cacheDir做本機metadata/bin存在性與eligibility檢查。部署只改server而漏同步client，會在restore請求前false miss、重新warm。

不要再把這種情況描述為「llama.cpp被Pi指到錯目錄」。

## Identity 隔離與 invalidation

至少區分：model/adapter身份、adapter scale、影響KV的runtime/config、prompt/tools。shape或格式可讀不代表內容語義相容。

- `.bin`是target state，`.bin.dft`是draft sidecar；不能只恢復一半。
- 舊無identity metadata不安全；預設不匯入、不复制base-only cache到LoRA namespace。
- 切換時使舊RAM state／queued jobs失效；取消舊HTTP操作，避免遲到結果覆蓋新runtime。
- headers與body timeout都需有界；不要只在排隊前檢查一次。
- directory不確定時safe miss／disabled persistent reuse，不亂刪orphan metadata。

## 本機extension修法的邊界

`/home/chihmin/src/pi-kv-cache-manager`，歷史修正commit `b2dbf9de50f24a9d9b7708b5255751a71b7b75a1`。

針對支援的Linux loopback listener：驗證PID／ownership／namespace／model，讀取server顯式slot-save-path；localhost驗證後DNS pinning；refresh runtime/namespace。

不是remote／proxy／container任意自動探測。stat identity不是抵抗惡意同inode/mtime竄改的完整內容hash；外部設定在last-check和request之間變動仍有競態。必須如實揭露。

## 快取驗證

1. 先列出idle slots／備份自己的測試範圍；不得回填舊權重KV。
2. 用兩個真正fresh processes，第一個prime、第二個restore。
3. 看restore HTTP200及server prefill log，不能只看cacheRead數字。
4. 再用同一persistent worker做A→B→A；同目錄LoRA scale1→0.5→1，應cold新namespace再restore舊namespace。
5. 測试全套實際extensions/skills、原localhost endpoint、無臨時env override。
6. test fixtures先隔離HOME/cache/network；不讓RED測試污染production。
7. 舊workers須reload／recreate才載入新程式；新session不一定等於新process。

歷史完整Pi測試prime13.63s、fresh1.616s，17,681 tokens restored、32新input。這是固定prompt的小測試，不是普遍延遲保證。

Discord gateway曾確認：闲置後 `/pi model` 重選同模型會close該channel RPC worker並保留對話。未來版本先讀handler，不能永久假設行為不变。
