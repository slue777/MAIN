#!/usr/bin/env bash
# Install the harness (skills + agent team) from this repo into the global
# Claude Code config at ~/.claude/. Idempotent: re-run after any edit to the
# repo source to push changes live. The repo is the source of truth; ~/.claude
# is an install of it (and is NOT version-controlled, so edit the repo, not the
# install).
set -euo pipefail

# Resolve the repo root (directory containing this script).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_HOME:-$HOME/.claude}"

SKILLS_DST="$CLAUDE_DIR/skills"
AGENTS_DST="$CLAUDE_DIR/agents"

mkdir -p "$SKILLS_DST" "$AGENTS_DST"

echo "Installing harness from $REPO_ROOT -> $CLAUDE_DIR"

# Skills. Source dir name -> installed skill name.
#   skills/harness -> ~/.claude/skills/harness
#   skills/evolve  -> ~/.claude/skills/harness-evolve   (matches original intent)
install_skill() {
  local src="$1" name="$2"
  rm -rf "${SKILLS_DST:?}/$name"
  cp -r "$REPO_ROOT/skills/$src" "$SKILLS_DST/$name"
  echo "  skill: $name"
}

install_skill harness harness
install_skill evolve  harness-evolve

# Agent team.
agent_count=0
for f in "$REPO_ROOT"/agents/*.md; do
  cp "$f" "$AGENTS_DST/"
  echo "  agent: $(basename "$f" .md)"
  agent_count=$((agent_count + 1))
done

echo "Done. Harness skills and $agent_count agents installed under $CLAUDE_DIR."
echo "Skills:  harness, harness-evolve   (invoke with /harness, /evolve)"
echo "Agents:  planner researcher implementer tester reviewer debugger"
