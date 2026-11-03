#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export FASHN_DNS_MODE=encrypted
# User approved avatar/reference/preview review with OpenAI on 2026-11-03.
export OPENAI_OUTFIT_REVIEW_ENABLED=1
# Bound this local pilot to the user’s existing purchased 100-credit top-up.
export FASHN_USER_CREDIT_LIMIT=100
export FASHN_GLOBAL_CREDIT_LIMIT=100
exec /Users/ricardozuloaga/Documents/Codex/2026-08-22/i-have-my-apis-listed-in/bin/codex-secrets run --keys FASHN_API_KEY,OPENAI_API_KEY -- .venv/bin/python pilot.py
