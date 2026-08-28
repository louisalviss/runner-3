package tools

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
	"unicode/utf8"

	"github.com/voocel/agentcore/schema"
)

const (
	writingBrainVersion    = "v2.3"
	writingBrainReleaseTag = "webnovel-writing-brain-nli-v2-3-2026-08-20"
	writingBrainAssetSHA   = "f961aa5d4b924b4ef7201fb2d0f5b676fa7fd6579e0d70eedbe5669447fbc4db"
)

// WritingBrainTool exposes Louis' Vietnamese-first Writing Brain V2.3 as a
// retrieval/review tool without coupling ainovel-cli to the 169 MB index asset.
// The external Python runtime remains the source of truth for retrieval ranking,
// context relations, NLI decisions and evidence provenance.
type WritingBrainTool struct {
	python   string
	script   string
	index    string
	traceDir string
	timeout  time.Duration
	failOpen bool
	traceMu  sync.Mutex
}

func NewWritingBrainToolFromEnv(bookDir string) *WritingBrainTool {
	index := strings.TrimSpace(os.Getenv("AINOVEL_WRITING_BRAIN_INDEX"))
	script := strings.TrimSpace(os.Getenv("AINOVEL_WRITING_BRAIN_SCRIPT"))
	if index == "" || script == "" {
		return nil
	}

	python := strings.TrimSpace(os.Getenv("AINOVEL_WRITING_BRAIN_PYTHON"))
	if python == "" {
		python = "python3"
	}

	timeout := 30 * time.Second
	if raw := strings.TrimSpace(os.Getenv("AINOVEL_WRITING_BRAIN_TIMEOUT_SECONDS")); raw != "" {
		if seconds, err := strconv.Atoi(raw); err == nil && seconds > 0 && seconds <= 300 {
			timeout = time.Duration(seconds) * time.Second
		}
	}

	traceDir := strings.TrimSpace(os.Getenv("AINOVEL_WRITING_BRAIN_TRACE_DIR"))
	if traceDir == "" {
		traceDir = filepath.Join(bookDir, "meta", "writing_brain")
	}

	failOpen := true
	if raw := strings.ToLower(strings.TrimSpace(os.Getenv("AINOVEL_WRITING_BRAIN_FAIL_OPEN"))); raw == "0" || raw == "false" || raw == "no" {
		failOpen = false
	}

	return &WritingBrainTool{
		python:   python,
		script:   script,
		index:    index,
		traceDir: traceDir,
		timeout:  timeout,
		failOpen: failOpen,
	}
}

func (t *WritingBrainTool) Name() string  { return "writing_brain" }
func (t *WritingBrainTool) Label() string { return "Writing Brain V2.3" }
func (t *WritingBrainTool) Description() string {
	return "Retrieve Vietnamese-first fiction-writing rules from Writing Brain V2.3. Use query/direct before planning or drafting; use review on prose; use checklist for a focused craft topic. Results preserve context relations, NLI audit data and linked evidence."
}
func (t *WritingBrainTool) ReadOnly(_ json.RawMessage) bool        { return true }
func (t *WritingBrainTool) ConcurrencySafe(_ json.RawMessage) bool { return true }
func (t *WritingBrainTool) StrictSchema() bool                     { return false }

func (t *WritingBrainTool) Schema() map[string]any {
	return schema.Object(
		schema.Property("action", schema.Enum("Writing Brain operation", "query", "direct", "review", "checklist")),
		schema.Property("task", schema.String("Concrete writing/planning/revision question")),
		schema.Property("phase", schema.Enum("Calling role", "architect", "writer", "editor")),
		schema.Property("genre", schema.String("Genre or subgenre when relevant")),
		schema.Property("chapter_goal", schema.String("Current chapter or scene goal")),
		schema.Property("current_context", schema.String("Compact story context needed to disambiguate the retrieval")),
		schema.Property("text", schema.String("Target prose for action=review")),
		schema.Property("topic", schema.String("Canonical Writing Brain topic for action=checklist; optional filter for query")),
		schema.Property("chapter", schema.Int("Chapter number for trace grouping; 0 when not applicable")),
		schema.Property("limit", schema.Int("Maximum returned rules; capped at 15")),
	)
}

type writingBrainArgs struct {
	Action         string `json:"action"`
	Task           string `json:"task"`
	Phase          string `json:"phase"`
	Genre          string `json:"genre"`
	ChapterGoal    string `json:"chapter_goal"`
	CurrentContext string `json:"current_context"`
	Text           string `json:"text"`
	Topic          string `json:"topic"`
	Chapter        int    `json:"chapter"`
	Limit          int    `json:"limit"`
}

func (t *WritingBrainTool) Execute(ctx context.Context, raw json.RawMessage) (json.RawMessage, error) {
	var a writingBrainArgs
	if err := json.Unmarshal(raw, &a); err != nil {
		return nil, fmt.Errorf("writing_brain invalid args: %w", err)
	}

	a.Action = strings.TrimSpace(strings.ToLower(a.Action))
	if a.Action == "" {
		a.Action = "query"
	}
	if a.Limit <= 0 {
		a.Limit = 12
	}
	if a.Limit > 15 {
		a.Limit = 15
	}

	cmdArgs, cleanup, err := t.commandArgs(a)
	if err != nil {
		return nil, err
	}
	if cleanup != nil {
		defer cleanup()
	}

	runCtx, cancel := context.WithTimeout(ctx, t.timeout)
	defer cancel()
	cmd := exec.CommandContext(runCtx, t.python, append([]string{t.script}, cmdArgs...)...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	start := time.Now()
	err = cmd.Run()
	elapsed := time.Since(start)

	if err != nil {
		msg := strings.TrimSpace(stderr.String())
		if runCtx.Err() == context.DeadlineExceeded {
			msg = "Writing Brain timeout"
		}
		if msg == "" {
			msg = err.Error()
		}
		if !t.failOpen {
			return nil, fmt.Errorf("writing_brain failed: %s", msg)
		}
		result, marshalErr := json.Marshal(map[string]any{
			"available":  false,
			"action":     a.Action,
			"version":    writingBrainVersion,
			"release_tag": writingBrainReleaseTag,
			"error":      msg,
			"fail_open":  true,
			"elapsed_ms": elapsed.Milliseconds(),
		})
		if marshalErr != nil {
			return nil, marshalErr
		}
		_ = t.appendTrace(a, result)
		return result, nil
	}

	payload := bytes.TrimSpace(stdout.Bytes())
	if !json.Valid(payload) {
		msg := "Writing Brain returned non-JSON output"
		if s := strings.TrimSpace(stderr.String()); s != "" {
			msg += ": " + s
		}
		if !t.failOpen {
			return nil, fmt.Errorf("%s", msg)
		}
		result, _ := json.Marshal(map[string]any{
			"available":   false,
			"action":      a.Action,
			"version":     writingBrainVersion,
			"release_tag": writingBrainReleaseTag,
			"error":       msg,
			"fail_open":   true,
		})
		_ = t.appendTrace(a, result)
		return result, nil
	}

	var decoded any
	if err := json.Unmarshal(payload, &decoded); err != nil {
		return nil, fmt.Errorf("decode writing_brain output: %w", err)
	}
	result, err := json.Marshal(map[string]any{
		"available":      true,
		"action":         a.Action,
		"version":        writingBrainVersion,
		"release_tag":    writingBrainReleaseTag,
		"asset_sha256":   writingBrainAssetSHA,
		"knowledge_mode": "semantic-canonical-context-nli-first",
		"elapsed_ms":     elapsed.Milliseconds(),
		"result":         decoded,
	})
	if err != nil {
		return nil, err
	}
	_ = t.appendTrace(a, result)
	return result, nil
}

func (t *WritingBrainTool) commandArgs(a writingBrainArgs) ([]string, func(), error) {
	base := []string{a.Action, "--index", t.index}
	limit := strconv.Itoa(a.Limit)

	switch a.Action {
	case "query":
		q := composeWritingBrainQuery(a)
		if q == "" {
			return nil, nil, fmt.Errorf("writing_brain query requires task, chapter_goal or current_context")
		}
		base = append(base, "--q", q, "--limit", limit)
		if strings.TrimSpace(a.Topic) != "" {
			base = append(base, "--topic", strings.TrimSpace(a.Topic))
		}
		return base, nil, nil
	case "direct":
		brief := composeWritingBrainBrief(a)
		if brief == "" {
			return nil, nil, fmt.Errorf("writing_brain direct requires a non-empty brief")
		}
		path, cleanup, err := tempTextFile("ainovel-writing-brain-direct-*.txt", brief)
		if err != nil {
			return nil, nil, err
		}
		return append(base, "--file", path, "--limit", limit), cleanup, nil
	case "review":
		text := strings.TrimSpace(a.Text)
		if text == "" {
			text = strings.TrimSpace(a.CurrentContext)
		}
		if text == "" {
			return nil, nil, fmt.Errorf("writing_brain review requires text")
		}
		path, cleanup, err := tempTextFile("ainovel-writing-brain-review-*.txt", text)
		if err != nil {
			return nil, nil, err
		}
		return append(base, "--file", path, "--limit", limit), cleanup, nil
	case "checklist":
		if strings.TrimSpace(a.Topic) == "" {
			return nil, nil, fmt.Errorf("writing_brain checklist requires topic")
		}
		return append(base, "--topic", strings.TrimSpace(a.Topic), "--limit", limit), nil, nil
	default:
		return nil, nil, fmt.Errorf("unsupported writing_brain action %q", a.Action)
	}
}

func composeWritingBrainQuery(a writingBrainArgs) string {
	parts := make([]string, 0, 5)
	if s := strings.TrimSpace(a.Task); s != "" {
		parts = append(parts, s)
	}
	if s := strings.TrimSpace(a.Genre); s != "" {
		parts = append(parts, "genre: "+s)
	}
	if s := strings.TrimSpace(a.ChapterGoal); s != "" {
		parts = append(parts, "chapter goal: "+s)
	}
	if s := strings.TrimSpace(a.CurrentContext); s != "" {
		parts = append(parts, "context: "+truncateRunes(s, 2400))
	}
	if s := strings.TrimSpace(a.Phase); s != "" {
		parts = append(parts, "phase: "+s)
	}
	return strings.Join(parts, "\n")
}

func composeWritingBrainBrief(a writingBrainArgs) string {
	parts := []string{}
	for _, pair := range []struct {
		label string
		value string
	}{
		{"task", a.Task},
		{"phase", a.Phase},
		{"genre", a.Genre},
		{"chapter_goal", a.ChapterGoal},
		{"current_context", a.CurrentContext},
	} {
		if v := strings.TrimSpace(pair.value); v != "" {
			parts = append(parts, pair.label+": "+v)
		}
	}
	return strings.Join(parts, "\n")
}

func truncateRunes(s string, max int) string {
	if max <= 0 || utf8.RuneCountInString(s) <= max {
		return s
	}
	r := []rune(s)
	return string(r[:max]) + "…"
}

func tempTextFile(pattern, content string) (string, func(), error) {
	f, err := os.CreateTemp("", pattern)
	if err != nil {
		return "", nil, fmt.Errorf("create writing_brain temp file: %w", err)
	}
	name := f.Name()
	cleanup := func() { _ = os.Remove(name) }
	if _, err := f.WriteString(content); err != nil {
		_ = f.Close()
		cleanup()
		return "", nil, fmt.Errorf("write writing_brain temp file: %w", err)
	}
	if err := f.Close(); err != nil {
		cleanup()
		return "", nil, fmt.Errorf("close writing_brain temp file: %w", err)
	}
	return name, cleanup, nil
}

func (t *WritingBrainTool) appendTrace(a writingBrainArgs, result json.RawMessage) error {
	if t.traceDir == "" {
		return nil
	}
	if err := os.MkdirAll(t.traceDir, 0o755); err != nil {
		return err
	}
	name := "global.jsonl"
	if a.Chapter > 0 {
		name = fmt.Sprintf("chapter_%03d.jsonl", a.Chapter)
	}

	record, err := json.Marshal(map[string]any{
		"timestamp":       time.Now().UTC().Format(time.RFC3339Nano),
		"version":         writingBrainVersion,
		"release_tag":     writingBrainReleaseTag,
		"asset_sha256":    writingBrainAssetSHA,
		"action":          a.Action,
		"phase":           a.Phase,
		"chapter":         a.Chapter,
		"task":            a.Task,
		"genre":           a.Genre,
		"chapter_goal":    a.ChapterGoal,
		"current_context": a.CurrentContext,
		"topic":           a.Topic,
		"result":          result,
	})
	if err != nil {
		return err
	}

	t.traceMu.Lock()
	defer t.traceMu.Unlock()
	f, err := os.OpenFile(filepath.Join(t.traceDir, name), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = f.Write(append(record, '\n'))
	return err
}
