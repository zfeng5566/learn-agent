#!/bin/bash
# 运行第一章智能旅行助手（Thought-Action-Observation 智能体）
# 用法: ./run_chapter1.sh
set -e
cd "$(dirname "$0")"

exec .venv/bin/python chapter1/travel_agent.py
