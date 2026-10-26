# GGUF／ROCm 配方與核心算子

這是歷史已跑通的**特定本機 profile**，不是保證任何版本皆相容的安裝腳本。重新執行前必須讀現有程式與manifest、核對硬體／授權／依賴；缺檔就停，不自动下載大型權重。

## 1. LoRA 與 QLoRA 的區別

LoRA本身不要求量化。標準NF4 QLoRA常使用4-bit codebook、double quantized scales與paged optimizer。GGUF是容器，Q4_0／Q4_K／Q6_K等是不同codec；GGUF＋LoRA不能一律稱NF4實作。

令 X[N,din]、Wq[dout,din]、A[r,din]、B[dout,r]、s=alpha/r：

```
D = Dropout(X)                  # p=0 或 inference 時 identity
Z = D A^T
T = Z B^T
Y = X Wq^T + bias + s*T
```

ops：必要dtype cast、Bernoulli mask、elementwise multiply／rescale、transpose（可能只是GEMM flag）、3個概念MatMul、scalar multiply、broadcast bias add（若有）、branch add、output cast。實際kernel可能融合，不等於每個算子各一個launch。

Backward，G=dL/dY：

```
dB = s G^T Z
dZ = s G B
dA = dZ^T D
dD = dZ A
dX = G Wq + DropoutBackward(dD)
```

Wq凍結，不算其參數更新，但主路徑仍需G Wq，不能detach整個base輸入路徑。

## 2. GGUF 解码例子

| 格式 | 概念式 | 主要ops |
|---|---|---|
| Q4_0，32/block | Wq=d*(q-8) | load FP16 scale/cast、nibble AND/shift、subtract、multiply |
| Q4_K，256/block | Wq=(d*sc)*q-(dmin*mn) | 解4-bit值＋6-bit scale/min、mask/shift、cast、乘法與減法 |
| Q6_K，256/block | q=low4 OR(high2<<4); Wq=d*sc*(q-32) | AND/OR/shift、signed int8 subscale、cast、subtract、multiply |
| NF4（不同路線） | codebook[q]*restored_scale | unpack、LUT gather、scale還原（可能含offset）、multiply |

本機參考：`/home/chihmin/llama-mtp-opt/ggml/src/ggml-quants.c`。其它quant types必須查其定義，不能套同一公式。

某些MMQ kernel另量化activations（absmax reduction、scaling、round/clamp、cast/pack、block sum）；這不是所有training backend必做的LoRA operator。不要拿推論native MMQ路徑冒充已用的training fallback。

## 3. 歷史本機 profile

- gfx1151 Strix Halo，約122.84GiB共享RAM、no swap。
- base：`/home/chihmin/models/Qwen3.6-35B-A3B-selective-Q4_0-proof/Qwen3.6-35B-A3B-UD-Q4_K_M-selective-Q4_0-flashhead.gguf`。
- HF config/tokenizer：`/home/chihmin/models/Qwen3.6-35B-A3B-HF-995ad96e`；revision `995ad96eacd98c81ed38be0c5b274b04031597b0`。不是底模逐值等價證明。
- main Q4_0的92 tensors常駐展開BF16、frozen quantized experts保留、`kernels._gguf_kernel=False` fallback。
- 全體Q4_0計數93與main92是不同統計範圍；不要混用。
- q_proj／v_proj選定20 modules／40 A/B tensors，rank4、alpha8、dropout0，512,000 trainable params。
- 選target時先看實際PEFT trainable names與數量；不要只看到target_modules名稱就假設所有層都相同。
- AdamW lr5e-5、clip1、batch1、max1536、activation checkpointing。

訓練環境：`/home/chihmin/qwen-date-audit/gguf-training-env`，torch2.12.1+rocm7.2、PEFT0.21.0、bnb0.50.2。轉檔環境：`/home/chihmin/qwen-date-audit/training-env-rocm72`。

HIP build曾需ROCm7.14 headers、真正clang-23、rocisa0.1.0：

```
HIPCC_COMPILE_FLAGS_APPEND='-isystem /opt/rocm-7.14.0/include'
PYTORCH_ROCM_ARCH=gfx1151
MAX_JOBS=2
```

先檢查kernel forward/backward相對誤差，不以import成功等同correctness。历史12個native case只支援7個；Q4_K/Q6_K fallback對上reference。不同環境不可默認照搬。

## 4. 訓練啟動範例：有條件，絕不能直接自動執行

以下wrapper是現有Qwen v11 limited job，ROOT／approval schema與epoch=1都硬綁本地實作；新模型應另外建立與審查runner，不只改環境變數。

先讀 `guarded_agentic_job.py`、`run_agentic_training.py` 和approval文件。只有当次授權、hashes及GPU gates都通過，才可將下列佔位路徑換成已核准的新路徑：

```sh
ROOT=/home/chihmin/qwen-date-audit
# DATA 是已審查且採納的資料目錄；OUT 必須不存在、不得在 DATA 內。
"$ROOT/gguf-training-env/bin/python" "$ROOT/guarded_agentic_job.py" \
  --mode preflight --data "$DATA" --output "$PREFLIGHT_OUT"
# 訓練需要另一個不存在的 output；通過 preflight 不自動授權 training。
"$ROOT/gguf-training-env/bin/python" "$ROOT/guarded_agentic_job.py" \
  --mode train --data "$DATA" --output "$TRAIN_OUT" --epochs 1
```

必須監控到 `supervisor-result.json`，不可啟動後把「已開始」說成「已完成」。不要直接繞wrapper跑trainer以規避記憶體守門。

## 5. Optimizer 與記憶體

AdamW概念ops：gradient accumulation、optional AMP unscale、finite checks、reduce-sum squares/sqrt norm、clip；一二階moving averages、bias correction、sqrt/divide、decoupled decay、parameter add/subtract、zero_grad。

paged optimizer是記憶體管理策略，不是不同LoRA矩陣公式。本案例使用一般AdamW，不宣稱paged。

MemoryMax不一定完整涵蓋GPU共享配置，需主機MemAvailable watchdog。一次load成功不表示完整backward夠空間。改allocator不是未驗證的萬用解法。

## 6. 匯出

- 先讀目前converter的help/source，確認base參數是config/tokenizer目錄，輸入是adapter目錄。
- 本案例用`training-env-rocm72`、`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`，`PYTHONPATH=/home/chihmin/llama-mtp-opt/gguf-py`、`--outtype f32`。
- 曾修正combined `LoraTorchTensor`須套用`self.filter_tensors()`，包括nested／legacy names regression。
- 全部tensor名字／shape／值核對；F32 export避免額外rounding，但不能只用檔案能打開就算等價。
- adapter輸出小不表示整個base或optimizer已保存。

圖解：`../assets/gguf-qlora-all-ops.png`；簡圖：`../assets/qlora-simple.png`。
