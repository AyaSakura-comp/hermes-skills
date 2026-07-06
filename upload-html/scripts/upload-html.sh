#!/usr/bin/env bash
set -euo pipefail

DEFAULT_REPO="git@github.com:AyaSakura-comp/TempHtml.git"

usage() {
  cat >&2 <<EOF
usage: $0 <html-file|site-folder> [owner/repo|https://github.com/owner/repo|git@github.com:owner/repo.git] [--flat] [--name PATH]

  --flat         Do NOT nest under a unique date/stamp folder; keep legacy
                 behaviour (single-file -> repo root with original name).
  --name PATH    Override the destination sub-path (relative to repo root).
                 Use this when you want a custom stable URL slug.
                 Mutually exclusive with --flat.
EOF
  exit 1
}

if [[ $# -lt 1 ]]; then
  usage
fi

# --- parse args (target repo is positional[1] if it looks like a repo spec) ---
input=""
target_repo=""
flat=0
custom_name=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --flat) flat=1; shift;;
    --name)
      [[ $# -ge 2 ]] || usage
      custom_name="$2"; shift 2;;
    -h|--help) usage;;
    *)
      if [[ -z "$input" ]]; then
        input="$1"
      elif [[ -z "$target_repo" ]]; then
        target_repo="$1"
      else
        echo "error: unexpected argument: $1" >&2; usage
      fi
      shift;;
  esac
done

if [[ -z "$input" ]]; then usage; fi
target_repo="${target_repo:-${UPLOAD_HTML_REPO:-$DEFAULT_REPO}}"

if [[ "$flat" -eq 1 && -n "$custom_name" ]]; then
  echo "error: --flat and --name are mutually exclusive" >&2; exit 1
fi


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
published_name=""           # entry HTML filename (index.html etc.)
dest_subpath=""              # where under the repo root this upload lands
cleanup() {
  rm -rf "$workdir"
}
trap cleanup EXIT
mkdir -p "$site_dir"

# Build a unique destination sub-path: YYYY/MM-DD/<slug>-HHMMSS
# This guarantees every upload gets its own URL and never overwrites a prior one.
timestamp="$(date +%Y/%m-%d/%H%M%S)"
slug_from_input="$(basename "$input")"
slug_from_input="${slug_from_input%.*}"
# If the file is a generic name (index.html / main.html / site.html ...),
# use the parent directory name as the slug — that's far more descriptive.
case "${slug_from_input,,}" in
  index|main|default|site|app|page|home)
    parent="$(basename "$(dirname "$input")")"
    if [[ -n "$parent" && "$parent" != "/" && "$parent" != "." ]]; then
      slug_from_input="$parent"
    fi
    ;;
esac
slug_from_input="${slug_from_input,,}"              # lowercase
slug_from_input="${slug_from_input//[^a-z0-9._-]/-}" # sanitize
slug_from_input="${slug_from_input//---/-}"
slug_from_input="${slug_from_input//--/-}"
slug_from_input="${slug_from_input#-}"
slug_from_input="${slug_from_input%-}"
[[ -z "$slug_from_input" ]] && slug_from_input="site"

default_subpath="$timestamp/$slug_from_input"


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
  mapfile -t html_files < <(find "$site_dir" -maxdepth 1 -type \( -iname '*.html' -o -iname '*.htm' \) | sort)
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

# Decide destination sub-path under the repo root.
if [[ -n "$custom_name" ]]; then
  # Trim leading/trailing slashes, collapse double slashes.
  dest_subpath="${custom_name#/}"
  dest_subpath="${dest_subpath%/}"
  dest_subpath="${dest_subpath//\//_}"   # treat --name as a single slug segment for safety
  [[ -z "$dest_subpath" ]] && dest_subpath="$default_subpath"
elif [[ "$flat" -eq 1 ]]; then
  dest_subpath=""                         # legacy: live at repo root
else
  dest_subpath="$default_subpath"         # new default: unique date/stamp folder
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

# Sync staged files into the chosen sub-path (or repo root if --flat).
dest_root="$clone_dir"
if [[ -n "$dest_subpath" ]]; then
  dest_root="$clone_dir/$dest_subpath"
  mkdir -p "$dest_root"
  # Clean any prior upload at this exact sub-path so a re-run with the same
  # --name stays deterministic (default timestamped path is already unique).
  find "$dest_root" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} + 2>/dev/null || true
else
  # --flat legacy behaviour: clear repo root (except .git) before staging.
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude='.git' "$site_dir"/ "$clone_dir"/
  else
    find "$clone_dir" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
    cp -R "$site_dir"/. "$clone_dir"/
  fi
fi
if [[ -n "$dest_subpath" ]]; then
  if command -v rsync >/dev/null 2>&1; then
    rsync -a "$site_dir"/ "$dest_root"/
  else
    cp -R "$site_dir"/. "$dest_root"/
  fi
fi


cd "$clone_dir"
branch="$(git branch --show-current 2>/dev/null || true)"
if [[ -z "$branch" ]]; then
  branch="main"
  git checkout -B "$branch" >/dev/null 2>&1 || true
fi
git config user.name "${GIT_AUTHOR_NAME:-Pi Upload}"
git config user.email "${GIT_AUTHOR_EMAIL:-pi-upload@example.com}"

# Ensure no stray local noise directories get tracked.
printf '.DS_Store\n*.log\nThumbs.db\n' > "$clone_dir/.gitignore.new"
if [[ -f "$clone_dir/.gitignore" ]]; then
  cat "$clone_dir/.gitignore" >> "$clone_dir/.gitignore.new"
fi
mv "$clone_dir/.gitignore.new" "$clone_dir/.gitignore"

git add -A
if ! git diff --cached --quiet; then
  commit_msg="Upload $published_name"
  [[ -n "$dest_subpath" ]] && commit_msg="$commit_msg -> $dest_subpath/"
  git commit -q -m "$commit_msg"
fi
git push -u origin "$branch" >/dev/null

repo_url="https://github.com/$repo_spec"
rel_path="$published_name"
[[ -n "$dest_subpath" ]] && rel_path="$dest_subpath/$published_name"
raw_url="https://raw.githubusercontent.com/$repo_spec/$branch/$rel_path"
site_url="https://raw.githack.com/$repo_spec/$branch/$rel_path"

printf 'Repo URL: %s\n' "$repo_url"
printf 'Path:      %s\n' "$rel_path"
printf 'Raw URL:   %s\n' "$raw_url"
printf 'Site URL:  %s\n' "$site_url"
