#!/usr/bin/env bash
# Install the harness (skills + agent team) from this repo into the global
# Claude Code config at ~/.claude/. Idempotent: re-run after any edit to the
# repo source to push changes live. The repo is the source of truth; ~/.claude
# is an install of it (and is NOT version-controlled, so edit the repo, not the
# install).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_HOME:-$HOME/.claude}"
# Paths (relative to CLAUDE_DIR) the previous run installed. Anything listed
# there that this run does not install is removed, so deleting or renaming a
# skill or agent in the repo takes effect — and nothing else is ever removed.
MANIFEST="$CLAUDE_DIR/.harness-installed"

mkdir -p "$CLAUDE_DIR/skills" "$CLAUDE_DIR/agents"
echo "Installing harness from $REPO_ROOT -> $CLAUDE_DIR"
: > "$MANIFEST.tmp"

# Copy a file or directory to $CLAUDE_DIR/<dst> through a hidden temp path and
# swap it in, so a half-copied item is never live.
install_item() {
  local src="$1" dst="$2"
  local tmp="$CLAUDE_DIR/${dst%/*}/.${dst##*/}.tmp.$$"
  rm -rf "$tmp"
  cp -r "$src" "$tmp"
  rm -rf "${CLAUDE_DIR:?}/$dst"
  mv "$tmp" "$CLAUDE_DIR/$dst"
  echo "$dst" >> "$MANIFEST.tmp"
  echo "  $dst"
}

# A skill installs under the name its SKILL.md declares (skills/evolve is
# "harness-evolve"), not its directory name.
for d in "$REPO_ROOT"/skills/*/; do
  name=$(sed -n 's/^name: *//p' "$d/SKILL.md" | head -1)
  case "$name" in ""|*/*|.*) echo "bad or missing name in $d/SKILL.md" >&2; exit 1 ;; esac
  install_item "${d%/}" "skills/$name"
done

for f in "$REPO_ROOT"/agents/*.md; do
  install_item "$f" "agents/${f##*/}"
done

if [ -f "$MANIFEST" ]; then
  while IFS= read -r old; do
    case "$old" in *..*|*/*/*) continue ;; skills/?*|agents/?*.md) ;; *) continue ;; esac
    if ! grep -qxF -- "$old" "$MANIFEST.tmp"; then
      rm -rf "${CLAUDE_DIR:?}/$old"
      echo "  removed stale: $old"
    fi
  done < "$MANIFEST"
fi
mv "$MANIFEST.tmp" "$MANIFEST"

echo "Done: $(wc -l < "$MANIFEST") items installed under $CLAUDE_DIR."
