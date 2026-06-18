# Upload HTML — 靜態網頁一鍵部署

將 HTML 檔案（或整個靜態網站目錄）部署到雲端 hosting，回傳公開網址。支援三大平台，優先級：Netlify > GitHub Pages > Cloudflare Pages。

---

## 1. 前置檢查

```bash
# 確認目標目錄結構
ls /path/to/site/          # 必須包含 index.html
```

網站目錄必須包含 `index.html`（根頁面）。多頁面網站可含 `.html` 副檔名檔案。

---

## 2. 部署平台選擇

### 平台比較

| 平台 | 速度 | 自訂網域 | 免費额度 | 需要 Git |
|------|------|----------|----------|----------|
| **Netlify** | ⚡ 最快（CLI 直接 deploy） | ✅ | 100 GB 頻寬/月 | ❌ 可匿名部署 |
| **GitHub Pages** | 🐢 需要 git push | ✅ | 100 GB/月 | ✅ |
| **Cloudflare Pages** | ⚡ 快 | ✅ | 500 GB/月 | ❌ CLI 可直傳 |

**預設選擇 Netlify**（最簡捷，無需帳號即可匿名部署）。

---

## 3. Netlify 部署（推薦）

### 3.1 安裝 Netlify CLI

```bash
# 系統層級（需 sudo）
sudo npm install -g netlify-cli

# 專案層級（免 sudo）
cd /path/to/site && npm install netlify-cli
# 或
npm install -g netlify-cli --prefix $HOME/.local
```

### 3.2 匿名部署（不需要 Netlify 帳號）

```bash
cd /path/to/site

npx netlify deploy \
  --dir . \
  --allow-anonymous \
  --prod \
  --message "Deployed via Pi" 2>&1
```

**輸出範例：**
```
🚀 Deploy complete

  Site URL:  http://dashing-moonbeam-06d01b.netlify.app
  Password:  My-Drop-Site

  Claim on Netlify:
  https://app.netlify.com/drop/dashing-moonbeam-06d01b#drop_token=...
```

**重點：**
- `--allow-anonymous`：不需要 Netlify 帳號，匿名建立「Drop Site」
- `--prod`：部署到 production（而非 branch deploy）
- `--dir .`：目前目錄就是網站根目錄
- **60 分鐘內**需用 `claim` 連結接管，否則過期
- 匿名部署預設有密碼（`My-Drop-Site`），登入後可移除

### 3.3 設定自訂網址（可选）

如果想在 URL 中使用特定名稱：

```bash
npx netlify deploy \
  --dir . \
  --allow-anonymous \
  --alias shikoku-travel \
  --prod
```

會產生 `shikoku-travel-xxxxxx.netlify.app`。

### 3.4 使用 netlify.toml 設定（可选）

如果網站需要 SPA routing 或 custom headers：

```toml
# netlify.toml
[build]
  publish = "."

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200

[[headers]]
  for = "/*"
  [headers.values]
    X-Frame-Options = "DENY"
    X-Content-Type-Options = "nosniff"
```

### 3.5 部署完成後

1. **複製網址**：從 deploy 輸出中取得 `Site URL`
2. **移除密碼**（可选）：
   - 使用輸出中的 `Claim on Netlify` 連結登入
   - 或在 Settings → Site settings 中關閉 "Password protection"
3. **自訂網域**（可选）：
   - Settings → Domain management → Add custom domain

---

## 4. GitHub Pages 部署（備選）

```bash
cd /path/to/site

# 建立臨時 repo
git init
git checkout -b main
git add .
git commit -m "Deploy site"

# 推到 GitHub repo
git remote add origin https://github.com/USERNAME/REPO.git
git push -u origin main

# 啟用 Pages
gh repo edit USERNAME/REPO --enable-pages true
# 或手動：Settings → Pages → Source: main branch
```

網址格式：`https://USERNAME.github.io/REPO`

---

## 5. Cloudflare Pages 部署（備選）

```bash
# 安裝 wrangler CLI
npm install -g wrangler

# 登入
wrangler login

# 部署
cd /path/to/site
wrangler pages deploy . --project-name=my-site
```

---

## 6. 更新已部署的網站

### Netlify

```bash
npx netlify deploy --dir /path/to/updated-site --allow-anonymous --prod
```

> ⚠️ 匿名部署每次會建立**新 site**，不會更新舊的。
> 
> **正確做法**：先 claim 舊 site，之後用 `--site <site-id>` 更新：
> ```bash
> npx netlify deploy --site YOUR_SITE_ID --dir . --prod
> ```

### GitHub Pages

```bash
cd /path/to/repo
# 修改檔案
git add .
git commit -m "Update site"
git push origin main
```

---

## 7. 完整流程（自動化腳本）

```bash
#!/bin/bash
# deploy.sh — 一鍵部署靜態網站
SITE_DIR="${1:-.}"

echo "🚀 Deploying $SITE_DIR to Netlify..."

cd "$SITE_DIR"

# 檢查 index.html
[ ! -f "index.html" ] && echo "❌ No index.html found" && exit 1

# 檢查 CLI
command -v npx >/dev/null || { echo "❌ npx not found"; exit 1; }

# 部署
OUTPUT=$(npx netlify deploy --dir . --allow-anonymous --prod --message "Deployed via script" 2>&1)
echo "$OUTPUT"

# 提取 URL
URL=$(echo "$OUTPUT" | grep -oP 'Site URL:\s*\Khttp://[^\s]+')
PASSWORD=$(echo "$OUTPUT" | grep -oP 'Password:\s*\K\S+')

if [ -n "$URL" ]; then
  echo ""
  echo "✅ Deployed: $URL"
  [ -n "$PASSWORD" ] && echo "🔒 Password: $PASSWORD"
else
  echo "❌ Deploy failed"
  echo "$OUTPUT"
  exit 1
fi
```

使用：
```bash
./deploy.sh /path/to/site
```

---

## 8. 常見問題

| 問題 | 解法 |
|------|------|
| `npm install -g` 權限不足 | 用 `--prefix $HOME/.local` 或專案層級 `npx` |
| 匿名部署 60 分鐘過期 | 盡快用 claim 連結登入接管 |
| SPA 路由 404 | 加 `netlify.toml` 設定 fallback |
| CSS/JS 不載入 | 確認路徑為相對路徑 `./style.css` 非 `/style.css` |
| 中文內容亂碼 | 確認 `index.html` 有 `<meta charset="UTF-8">` |

---

## 9. 進階：CI/CD 自動部署

將 GitHub repo 連接 Netlify：
1. GitHub repo Settings → Actions → 啟用
2. Netlify Sites → Add new site → Import from GitHub
3. 每次 `git push` 自動觸發部署

---

*最後更新：2026-06-17*
