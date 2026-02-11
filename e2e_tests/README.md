# Real-API End-to-End Tests

These tests call a real OpenAI-compatible API endpoint (default: RIGHTCODE) and verify `openagentic_sdk` behavior end-to-end.

## Requirements

- Python 3.11+
- Network access to your configured endpoint
- Env vars (either set these directly, or use `.env` as described below):
  - `RIGHTCODE_API_KEY` (required)
  - `RIGHTCODE_BASE_URL` (optional, default `https://www.right.codes/codex/v1`)
  - `RIGHTCODE_MODEL` (optional, default `gpt-5.2`)
  - `RIGHTCODE_TIMEOUT_S` (optional, default `120`)

### `.env` support (recommended)

The test harness (`e2e_tests/_harness.py`) will best-effort load a repo-root `.env` file (no third-party dependency).

It also supports OpenAI-style variable aliases:
- `OPENAI_API_KEY` → `RIGHTCODE_API_KEY`
- `OPENAI_BASE_URL` → `RIGHTCODE_BASE_URL`

## Run

Run all e2e tests:

`python3 -m unittest discover -s e2e_tests -p "e2e_*.py" -v`

Notes:
- The unit test command `python3 -m unittest -q` does not include these tests (pattern mismatch).
- These tests may incur real model costs.
