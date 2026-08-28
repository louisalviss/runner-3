#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-.}"
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$TARGET/internal/agents/build.go"

if [[ ! -f "$TARGET/go.mod" || ! -f "$BUILD" ]]; then
  echo "error: target does not look like ainovel-cli root" >&2
  exit 2
fi

mkdir -p "$TARGET/internal/tools" "$TARGET/docs" "$TARGET/configs"
cp "$PKG_DIR/internal/tools/writing_brain.go" "$TARGET/internal/tools/writing_brain.go"
cp "$PKG_DIR/docs/WRITING_BRAIN_INTEGRATION.md" "$TARGET/docs/WRITING_BRAIN_INTEGRATION.md"
cp "$PKG_DIR/configs/writing-brain.env.example" "$TARGET/configs/writing-brain.env.example"

python3 - "$BUILD" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')
anchor='''\tcontextTool := tools.NewContextTool(store, bundle.References, cfg.Style, styleStats)\n\treadChapter := tools.NewReadChapterTool(store)\n'''
replacement=anchor+'''\twritingBrain := tools.NewWritingBrainToolFromEnv(store.Dir())\n'''
if 'writingBrain := tools.NewWritingBrainToolFromEnv(store.Dir())' not in s:
    if anchor not in s:
        raise SystemExit('error: build.go constructor anchor not found; upstream drift requires manual merge')
    s=s.replace(anchor,replacement,1)

anchor2='''\teditorTools := []agentcore.Tool{\n\t\tcontextTool,\n\t\treadChapter,\n\t\ttools.NewSaveReviewTool(store),\n\t\ttools.NewSaveArcSummaryTool(store),\n\t\ttools.NewSaveVolumeSummaryTool(store),\n\t}\n'''
addition=anchor2+'''\n\tif writingBrain != nil {\n\t\tarchitectTools = append(architectTools, writingBrain)\n\t\twriterTools = append(writerTools, writingBrain)\n\t\teditorTools = append(editorTools, writingBrain)\n\t}\n'''
if 'architectTools = append(architectTools, writingBrain)' not in s:
    if anchor2 not in s:
        raise SystemExit('error: build.go tool-list anchor not found; upstream drift requires manual merge')
    s=s.replace(anchor2,addition,1)
p.write_text(s,encoding='utf-8')
PY

if command -v gofmt >/dev/null 2>&1; then
  gofmt -w "$TARGET/internal/tools/writing_brain.go" "$BUILD"
fi

echo "Writing Brain V2.3 integration applied to $TARGET"
