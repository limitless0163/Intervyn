.PHONY: help setup install dev up start stop down restart logs logs-web ps shell build typecheck test lint format schema

LIVEKIT_CONFIGURED := $(shell [ -f .env ] && grep -Eq '^LIVEKIT_URL=.+$$' .env && grep -Eq '^LIVEKIT_API_KEY=.+$$' .env && grep -Eq '^LIVEKIT_API_SECRET=.+$$' .env && echo 1)
LIVE_PROFILE = $(if $(LIVEKIT_CONFIGURED),--profile live)
COMPOSE = docker compose $(LIVE_PROFILE) -f docker-compose.yml -f docker-compose.dev.yml
DOCKER_START_TIMEOUT ?= 120
WEB_START_TIMEOUT ?= 180
WORKER_START_TIMEOUT ?= 120

help: ## 列出常用命令
	@awk 'BEGIN {FS = ":.*##"; printf "Intervyn 开发命令：\n"} /^[a-zA-Z_-]+:.*##/ {printf "  make %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## 安装前端和后端开发依赖
	bash scripts/setup.sh

install: ## 根据锁文件安装 pnpm 依赖
	pnpm install --frozen-lockfile

dev: ## 启动 Docker 开发环境；LiveKit 配置齐全时也启动语音 Worker
	@set -eu; \
	if ! command -v docker >/dev/null 2>&1; then \
		echo "错误：未找到 docker 命令，请先安装 Docker Desktop。" >&2; exit 1; \
	fi; \
	if ! docker info >/dev/null 2>&1; then \
		echo "Docker 尚未运行，正在尝试启动……"; \
		case "$$(uname -s)" in \
			Darwin) \
				if [ -d /Applications/Docker.app ] || [ -d "$$HOME/Applications/Docker.app" ]; then \
					open -a Docker; \
				else \
					echo "错误：未找到 Docker Desktop，请先安装 Docker Desktop。" >&2; exit 1; \
				fi ;; \
			Linux) \
				if command -v systemctl >/dev/null 2>&1; then \
					if [ "$$(id -u)" -eq 0 ]; then systemctl start docker; else sudo systemctl start docker; fi; \
				else \
					echo "错误：无法自动启动 Docker，请启动 Docker 服务后重试。" >&2; exit 1; \
				fi ;; \
			*) echo "错误：此系统不支持自动启动 Docker，请手动启动 Docker 后重试。" >&2; exit 1 ;; \
		esac; \
		attempt=0; \
		until docker info >/dev/null 2>&1; do \
			attempt=$$((attempt + 1)); \
			if [ "$$attempt" -ge "$(DOCKER_START_TIMEOUT)" ]; then \
				echo "错误：等待 Docker 启动超时。" >&2; exit 1; \
			fi; \
			sleep 1; \
		done; \
	fi; \
	$(COMPOSE) up --build --renew-anon-volumes -d; \
	if [ "$(LIVEKIT_CONFIGURED)" = "1" ]; then \
		echo "等待 LiveKit Worker 注册（最多 $(WORKER_START_TIMEOUT) 秒）……"; \
		attempt=0; \
		until $(COMPOSE) logs --no-color --tail=100 agent-worker 2>/dev/null | grep -q "registered worker"; do \
			attempt=$$((attempt + 1)); \
			if [ "$$attempt" -ge "$(WORKER_START_TIMEOUT)" ]; then \
				echo "错误：LiveKit Worker 未能注册，最近日志如下：" >&2; \
				$(COMPOSE) logs --tail=80 agent-worker; exit 1; \
			fi; \
			sleep 1; \
		done; \
		echo "LiveKit Worker 已注册。"; \
	else \
		echo "LiveKit 配置不完整，按离线模式启动；语音 Worker 未启动。"; \
	fi; \
	echo "等待前端就绪（最多 $(WEB_START_TIMEOUT) 秒）……"; \
	attempt=0; \
	until curl --fail --silent http://localhost:3000/api/health >/dev/null; do \
		attempt=$$((attempt + 1)); \
		if [ "$$attempt" -ge "$(WEB_START_TIMEOUT)" ]; then \
			echo "错误：前端启动超时，最近日志如下：" >&2; \
			$(COMPOSE) logs --tail=80 web; exit 1; \
		fi; \
		sleep 1; \
	done; \
	echo "前端已就绪：http://localhost:3000"; \
	if command -v open >/dev/null 2>&1; then open http://localhost:3000 >/dev/null 2>&1 || true; \
	elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:3000 >/dev/null 2>&1 || true; fi

up: dev ## 同 make dev

start: dev ## 同 make dev

stop: ## 停止开发环境容器
	$(COMPOSE) stop

down: ## 停止并移除开发环境容器（保留数据卷）
	$(COMPOSE) down

restart: ## 重启开发环境容器
	$(COMPOSE) restart

logs: ## 跟踪所有容器日志
	$(COMPOSE) logs -f --tail=100

logs-web: ## 跟踪前端容器日志
	$(COMPOSE) logs -f --tail=100 web

ps: ## 查看开发环境容器状态
	$(COMPOSE) ps

shell: ## 进入前端开发容器
	$(COMPOSE) exec web sh

build: ## 构建 workspace
	pnpm build

typecheck: ## 检查 TypeScript 类型
	pnpm typecheck

test: ## 运行 workspace 测试
	pnpm test

lint: ## 检查代码格式和后端 lint
	pnpm lint

format: ## 自动格式化代码
	pnpm format

schema: ## 重新生成共享 JSON Schema
	pnpm gen:schema
