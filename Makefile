# Makefile for Peer Review Simulator

.PHONY: install playground run test clean

install:
	uv sync --all-extras

playground:
	uv run adk web app --host 127.0.0.1 --port 18081 --reload_agents

run:
	uv run uvicorn app.agent_runtime_app:app --host 127.0.0.1 --port 18081 --reload

test:
	uv run pytest
