#!/bin/bash
# Runs inside every benchmark container. Drives the agent against the task
# prompt, then executes the task's grader. Exit code 0 = pass, non-zero = fail.
set -u

fail() { echo "[myclaw-entrypoint] $*" >&2; exit 2; }

PROMPT_FILE="/myclaw/task-prompt.txt"
[ -f "$PROMPT_FILE" ] || fail "task prompt missing at $PROMPT_FILE"

: "${MYCLAW_MODEL:?MYCLAW_MODEL not set}"
: "${MYCLAW_ENDPOINT:?MYCLAW_ENDPOINT not set}"
: "${MYCLAW_API_KEY:?MYCLAW_API_KEY not set}"
MYCLAW_MAX_TURNS="${MYCLAW_MAX_TURNS:-50}"

echo "[myclaw-entrypoint] Running agent (max_turns=$MYCLAW_MAX_TURNS)..."
/usr/local/bin/myclaw-oneshot \
    --prompt-file "$PROMPT_FILE" \
    --model "$MYCLAW_MODEL" \
    --endpoint "$MYCLAW_ENDPOINT" \
    --api-key "$MYCLAW_API_KEY" \
    --max-turns "$MYCLAW_MAX_TURNS"
agent_rc=$?
echo "[myclaw-entrypoint] Agent exited with rc=$agent_rc"

# Grader: the task's run-tests.sh is mounted at /myclaw/run-tests.sh by the host
# harness. $TEST_DIR points at the task's mounted tests/ folder — same contract
# Terminal-Bench's own runner uses.
GRADER_SCRIPT="/myclaw/run-tests.sh"
export TEST_DIR="${TEST_DIR:-/myclaw/tests}"

[ -f "$GRADER_SCRIPT" ]   || fail "grader missing at $GRADER_SCRIPT"
[ -d "$TEST_DIR" ]        || fail "TEST_DIR missing at $TEST_DIR"

echo "[myclaw-entrypoint] Running grader ($GRADER_SCRIPT, TEST_DIR=$TEST_DIR)..."
bash "$GRADER_SCRIPT"
grader_rc=$?
echo "[myclaw-entrypoint] Grader exited with rc=$grader_rc"
exit "$grader_rc"
