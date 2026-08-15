#!/usr/bin/env bash
set -euo pipefail

# Provider-neutral SCM orchestration. It deliberately does not stage or
# commit files: choosing what enters a release remains an explicit developer
# action.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PROVIDER="${SCM_PROVIDER:-}"
REMOTE="${SCM_REMOTE:-origin}"

usage() {
  cat <<'EOF'
Usage:
  scripts/scm_release.sh pr [--base main] [--title "..."]
  scripts/scm_release.sh tag [--version 0.1.0]
  scripts/scm_release.sh release [--version 0.1.0]

Environment:
  SCM_PROVIDER=github|gitlab  Override provider detection
  SCM_REMOTE=origin           Git remote to use

Requirements:
  GitHub: gh (authenticated with `gh auth login`)
  GitLab: glab (authenticated with `glab auth login`)

The working tree must be clean. The script never stages or commits files.
`pr` pushes the current branch and opens a PR/MR. `tag` creates and pushes an
annotated v<version> tag. `release` creates the SCM release after CI has
published the OS artifacts.
EOF
}

die() { echo "ERROR: $*" >&2; exit 2; }

detect_provider() {
  [[ -n "$PROVIDER" ]] && return
  local url
  url="$(git remote get-url "$REMOTE" 2>/dev/null || true)"
  case "$url" in
    *github.com:*.git|*github.com/*) PROVIDER="github" ;;
    *gitlab.com:*.git|*gitlab.com/*) PROVIDER="gitlab" ;;
    *) die "Cannot detect SCM provider from remote '$REMOTE'. Set SCM_PROVIDER=github or SCM_PROVIDER=gitlab." ;;
  esac
}

require_clean_tree() {
  [[ -z "$(git status --porcelain)" ]] || die "Working tree is not clean; commit or stash changes first."
}

version_from_project() {
  sed -nE 's/^version = "([^"]+)"/\1/p' pyproject.toml | head -n 1
}

normalise_version() {
  local version="${1:-$(version_from_project)}"
  version="${version#v}"
  [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || die "Invalid version: $version"
  printf '%s' "$version"
}

open_pr() {
  local base="main" title="Release preparation"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --base) base="$2"; shift 2 ;;
      --title) title="$2"; shift 2 ;;
      *) die "Unknown pr option: $1" ;;
    esac
  done
  require_clean_tree
  detect_provider
  local branch
  branch="$(git branch --show-current)"
  [[ -n "$branch" && "$branch" != "$base" ]] || die "Checkout a release branch before opening a PR/MR."
  git push --set-upstream "$REMOTE" "$branch"
  if [[ "$PROVIDER" == "github" ]]; then
    command -v gh >/dev/null || die "GitHub CLI 'gh' is required."
    gh pr create --base "$base" --head "$branch" --title "$title" --body "Automated release preparation."
  else
    command -v glab >/dev/null || die "GitLab CLI 'glab' is required."
    glab mr create --target-branch "$base" --source-branch "$branch" --title "$title" --description "Automated release preparation."
  fi
}

push_tag() {
  local version="$(normalise_version "${1:-}")" tag="v$version"
  require_clean_tree
  detect_provider
  git rev-parse "$tag" >/dev/null 2>&1 && die "Tag already exists locally: $tag"
  git tag -a "$tag" -m "Release $tag"
  git push "$REMOTE" "$tag"
  echo "Pushed $tag; CI will build and publish the OS artifacts."
}

create_release() {
  local version="$(normalise_version "${1:-}")" tag="v$version"
  detect_provider
  git rev-parse "$tag" >/dev/null 2>&1 || die "Tag does not exist locally: $tag"
  if [[ "$PROVIDER" == "github" ]]; then
    command -v gh >/dev/null || die "GitHub CLI 'gh' is required."
    gh release create "$tag" --generate-notes
  else
    command -v glab >/dev/null || die "GitLab CLI 'glab' is required."
    glab release create "$tag" --name "SeratoMidiConf $tag" --notes "Release $tag. OS artifacts are attached by CI."
  fi
}

command_name="${1:-}"
shift || true
case "$command_name" in
  pr) open_pr "$@" ;;
  tag) [[ "${1:-}" == "--version" ]] && shift && push_tag "${1:-}" || push_tag "" ;;
  release) [[ "${1:-}" == "--version" ]] && shift && create_release "${1:-}" || create_release "" ;;
  help|-h|--help) usage ;;
  *) usage; exit 2 ;;
esac
