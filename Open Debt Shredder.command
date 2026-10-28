#!/bin/zsh
cd -- "$(dirname -- "$0")" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  print 'The Debt Shredder Python environment is missing from this folder.'
  read '?Press Enter to close.'
  exit 1
fi
.venv/bin/python START_APP.py
if [[ $? -ne 0 ]]; then
  read '?Press Enter to close.'
fi
