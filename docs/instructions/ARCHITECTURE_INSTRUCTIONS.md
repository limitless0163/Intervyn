# ARCHITECTURE_INSTRUCTIONS.md

## 总项目架构
```
project/
├── backend/                # 后端
├── docs/                   # 文档
├── frontend/               # 前端
├── infra/                  # 基础设施与部署
├── scripts/                # 项目辅助脚本
├── tests/                  # 系统级 / E2E / 跨服务测试
├── .dockerignore
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Makefile
├── AGENTS.md
├── CLAUDE.md
└── README.md
```


## 前端架构    TypeScript + React + Next.js
```
frontend/
├── public/                 # 图片、字体、图标等静态资源
├── src/                    # 前端核心源码
│   ├── app/                # Next.js 页面、路由、布局
│   ├── components/         # 可复用 UI 组件
│   ├── constants/          # 常量、枚举等
│   ├── features/           # 按业务功能划分的模块
│   ├── hooks/              # 自定义 React Hooks
│   ├── lib/                # 第三方库封装、SDK/client
│   ├── services/           # API 请求、后端服务调用
│   ├── stores/             # 全局状态管理
│   ├── styles/             # 全局样式与样式资源
│   ├── types/              # TypeScript 类型定义
│   └── utils/              # 纯工具函数
│
├── tests/                  # 前端单元测试、组件测试
├── next.config.ts
├── package.json
├── tsconfig.json
├── AGENTS.md
├── CLAUDE.md
└── README.md
```


## 后端架构      Python + FastAPI
```
backend/
├── app/                    # 后端核心源码
│   ├── api/                # API 路由与接口定义
│   │   ├── routes/         # 按业务模块拆分的 API 路由
│   │   └── router.py
│   │
│   ├── core/               # 配置、安全、日志等核心功能
│   ├── db/                 # 数据库连接、会话、初始化
│   ├── dependencies/       # FastAPI 依赖注入
│   ├── middleware/         # 中间件
│   ├── models/             # 数据库 ORM 模型
│   ├── repositories/       # 数据访问层
│   ├── schemas/            # Pydantic 请求/响应数据模型
│   ├── services/           # 业务逻辑层
│   ├── utils/              # 通用工具函数
│   └── main.py
│
├── migrations/             # 数据库迁移
├── scripts/                # 后端专用维护/初始化脚本
├── tests/                  # 后端单元测试、接口测试
├── Dockerfile
├── pyproject.toml
├── AGENTS.md
├── CLAUDE.md
└── README.md
```


## 测试架构
```
Frontend
├── Vitest
└── React Testing Library

Backend
├── pytest
├── FastAPI TestClient
└── HTTPX

Full-stack E2E
└── Playwright

CI
└── GitHub Actions
```


## 注意事项

- 本架构是项目重构与文件归属的强制规范。重构时应检查现有全部文件，并按照其实际职责迁移到本规范对应的位置，避免文件随意堆放、职责混乱或同类文件分散。
- 允许根据项目实际业务在规范目录下继续细分子目录，但不得无必要地引入与本架构冲突的新目录层级。
- 参考架构中的目录无需为了“补齐结构”而全部提前创建；仅在存在对应业务文件或职责时创建，禁止生成无业务内容的空目录、README 占位目录或伪业务目录。
- 重构过程中不得改变原有业务逻辑和功能；移动、重命名文件后必须同步修正 import、配置、脚本、测试及其他引用，确保项目仍可正常运行。
- 对重复文件、临时文件、废弃代码和明显由 AI 随意生成的冗余文件，应确认无引用和无实际用途后再删除，不得仅根据文件名直接删除。
- 若框架、依赖库或开发工具对特定文件名、目录位置存在明确要求，应优先遵循其官方约定，不得为了符合本架构而强行迁移导致框架或工具失效。