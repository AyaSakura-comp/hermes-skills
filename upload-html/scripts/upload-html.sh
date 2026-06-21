#!/usr/bin/env bash
set -euo pipefail

DEFAULT_REPO="git@github.com:AyaSakura-comp/TempHtml.git"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <html-file|site-folder> [owner/repo|https://github.com/owner/repo|git@github.com:owner/repo.git]" >&2
  exit 1
fi

input="$1"
target_repo="${2:-${UPLOAD_HTML_REPO:-$DEFAULT_REPO}}"

if [[ ! -e "$input" ]]; then
  echo "error: path not found: $input" >&2
  exit 1
fi

normalize_repo_spec() {
  local spec="$1"
  spec="${spec%.git}"
  spec="${spec#https://github.com/}"
  spec="${spec#http://github.com/}"
  spec="${spec#git@github.com:}"
  printf '%s' "$spec"
}

resolve_clone_url() {
  local spec="$1"
  if [[ "$spec" == git@github.com:* ]]; then
    printf '%s' "${spec%.git}.git"
  elif [[ "$spec" == http://github.com/* || "$spec" == https://github.com/* ]]; then
    printf '%s' "${spec%.git}"
  else
    printf 'git@github.com:%s.git' "$spec"
  fi
}

workdir="$(mktemp -d)"
site_dir="$workdir/site"
published_name=""
cleanup() {
  rm -rf "$workdir"
}
trap cleanup EXIT
mkdir -p "$site_dir"

stage_file() {
  local src="$1"
  local base
  base="$(basename "$src")"
  cp "$src" "$site_dir/$base"
  published_name="$base"
}

stage_folder() {
  cp -R "$1"/. "$site_dir"/
  if [[ -f "$site_dir/index.html" ]]; then
    published_name="index.html"
    return
  fi
  mapfile -t html_files < <(find "$site_dir" -maxdepth 1 -type f \( -iname '*.html' -o -iname '*.htm' \) | sort)
  if [[ "${#html_files[@]}" -eq 1 ]]; then
    published_name="$(basename "${html_files[0]}")"
  else
    echo "error: site folder must contain index.html (or exactly one .html/.htm file)" >&2
    exit 1
  fi
}

if [[ -f "$input" ]]; then
  case "${input,,}" in
    *.html|*.htm)
      stage_file "$input"
      ;;
    *)
      echo "error: single-file upload expects an .html or .htm file" >&2
      exit 1
      ;;
  esac
else
  stage_folder "$input"
fi

repo_url=""
raw_url=""
site_url=""

repo_spec="$(normalize_repo_spec "$target_repo")"
clone_url="$(resolve_clone_url "$target_repo")"
clone_dir="$workdir/repo"

if ! git clone "$clone_url" "$clone_dir" >/dev/null 2>&1; then
  echo "error: failed to clone target repo: $target_repo" >&2
  exit 1
fi

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude='.git' "$site_dir"/ "$clone_dir"/
else
  find "$clone_dir" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
  cp -R "$site_dir"/. "$clone_dir"/
fi

cd "$clone_dir"
branch="$(git branch --show-current 2>/dev/null || true)"
if [[ -z "$branch" ]]; then
  branch="main"
  git checkout -B "$branch" >/dev/null 2>&1 || true
fi
git config user.name "${GIT_AUTHOR_NAME:-Pi Upload}"
git config user.email "${GIT_AUTHOR_EMAIL:-pi-upload@example.com}"
git add .
if ! git diff --cached --quiet; then
  git commit -q -m "Update uploaded HTML site"
fi
git push -u origin "$branch" >/dev/null

repo_url="https://github.com/$repo_spec"
raw_url="https://raw.githubusercontent.com/$repo_spec/$branch/$published_name"
site_url="https://raw.githack.com/$repo_spec/$branch/$published_name"

printf 'Repo URL: %s\n' "$repo_url"
printf 'Raw URL: %s\n' "$raw_url"
printf 'Site URL: %s\n' "$site_url"
