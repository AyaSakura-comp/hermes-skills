---
name: upload-html
description: Publish a local HTML file or static site folder to git@github.com:AyaSakura-comp/TempHtml.git by default, or to another GitHub repo you already have access to, then return a raw.githack CDN URL.
allowed-tools: bash read write
---

# upload-html

Publish a single HTML file or static site folder by staging it in a temp dir, then push it to a GitHub repo and return a shareable raw.githack URL.

## Default behavior

- Default target repo: `git@github.com:AyaSakura-comp/TempHtml.git`.
- If a target repo is provided (`owner/repo`, `https://github.com/owner/repo`, or `git@github.com:owner/repo.git`), use that repo directly.
- Single `.html` / `.htm` file: keep the original filename; do **not** rename it to `index.html`.
- Folder: sync it as-is; use `index.html` only if it already exists or is required by the site structure.
- For direct repo pushes, SSH access or GitHub auth must already work.

## Usage

```bash
./scripts/upload-html.sh /path/to/index.html
./scripts/upload-html.sh /path/to/site-folder
./scripts/upload-html.sh /path/to/site-folder owner/repo
./scripts/upload-html.sh /path/to/site-folder git@github.com:owner/repo.git
```

## Workflow

1. Validate the input path exists.
2. Stage files into a temp directory.
3. If a target repo was supplied, clone it and sync the staged files into it.
4. Otherwise use the default repo `git@github.com:AyaSakura-comp/TempHtml.git`.
5. Push the updated branch and return:
   - `Repo URL`
   - `Raw URL` (`raw.githubusercontent.com`)
   - `Site URL` (`raw.githack.com`)

## Troubleshooting

- If the repo exists but you do not have permission, stop and report the GitHub error.
- If the site has relative assets, include them in the pushed folder.
- raw.githack may cache briefly after the first push.
