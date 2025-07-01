# 资金费率套利机器人

一个高度自动化、7x24小时运行的全天候资金费率套利机器人。该机器人具备主动风险管理、市场深度分析和实时事件通知能力，旨在通过先进的套利策略，在可控风险下追求长期、稳定的资本复合增长。

## ✨ 核心特性

- **三重收益引擎**: 系统性地结合了三种收益来源：
    1.  **双向杠杆化资金费套利**: 同时捕捉正、负资金费率机会，实现市场中性对冲。
    2.  **现货持仓收益增强**: 将正费率策略中持有的现货自动投入OKX“赚币”产品，赚取额外利息。
    3.  **主动风险控制**: 实时监控保证金比率，通过自动“平仓-再开仓”来主动规避强平风险。
- **深度流动性分析**: 在下单前分析L2订单簿，预估并控制滑点成本。
- **全面的成本核算**: 基于包含交易手续费、滑点、借贷成本在内的综合模型做出开仓决策。
- **实时事件通知**: 通过Telegram发送所有关键操作（开/平仓、重置）和异常事件的通知。
- **模块化架构**: 系统采用分层模块化设计，确保职责清晰、高内聚、低耦合。
- **持久化存储**: 使用PostgreSQL数据库记录每一个仓位的完整生命周期，便于复盘和分析。

## 🛠️ 技术栈

- **编程语言**: Python 3.12+
- **核心框架**: `asyncio`
- **环境与依赖管理**: `pip` + `requirements.txt`
- **交易所交互**: `ccxt`
- **数据库**: PostgreSQL (使用 `psycopg2-binary` 驱动)
- **任务调度**: `apscheduler`
- **通知服务**: `python-telegram-bot`
- **辅助库**: `pandas`, `PyYAML`

## 🚀 快速开始

### 1. 环境准备

- 安装 Python 3.12+
- 安装 PostgreSQL 数据库

### 2. 项目设置

1.  **克隆仓库**
    ```bash
    git clone <your-repository-url>
    cd funding_rate_arbitrage
    ```

2.  **创建并激活虚拟环境**
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # macOS / Linux
    source .venv/bin/activate
    ```

3.  **安装依赖**
    *(注意: 项目需要您自行根据 `pyproject.toml` 或文档中的技术栈创建 `requirements.txt`)*
    ```bash
    pip install ccxt psycopg2-binary apscheduler python-telegram-bot pandas PyYAML
    ```

4.  **配置机器人**
    - 复制配置文件模板：
      ```bash
      # Windows
      copy config\config.yml.example config\config.yml
      # macOS / Linux
      cp config/config.yml.example config/config.yml
      ```
    - 编辑 `config/config.yml` 文件，填入你的OKX API密钥、数据库连接信息和Telegram机器人Token。
      **警告: `config.yml` 包含敏感信息，已加入 `.gitignore`，请勿提交到版本控制系统。**

5.  **初始化数据库**
    - 连接到你的PostgreSQL数据库。
    - 执行以下SQL命令以创建 `positions` 表：
      ```sql
      CREATE TABLE IF NOT EXISTS positions (
          id SERIAL PRIMARY KEY,
          symbol TEXT NOT NULL,
          direction TEXT NOT NULL CHECK(direction IN ('SHORT', 'LONG')),
          status TEXT NOT NULL CHECK(status IN ('OPEN', 'CLOSED', 'RESETTING', 'REDEEMING')),
          leverage NUMERIC(5, 2) NOT NULL,
          open_timestamp TIMESTAMPTZ NOT NULL,
          close_timestamp TIMESTAMPTZ,
          last_update_timestamp TIMESTAMPTZ,
          position_amount NUMERIC(20, 10) NOT NULL,
          entry_spot_price NUMERIC(20, 10) NOT NULL,
          entry_swap_price NUMERIC(20, 10) NOT NULL,
          exit_spot_price NUMERIC(20, 10),
          exit_swap_price NUMERIC(20, 10),
          spot_earning_status TEXT DEFAULT 'NONE' CHECK(spot_earning_status IN ('SUBSCRIBED', 'REDEEMED', 'NONE')),
          total_spot_earning_yield NUMERIC(20, 10) DEFAULT 0,
          initial_spot_earning_rate NUMERIC(20, 10),
          margin_ratio NUMERIC(10, 4),
          initial_funding_rate NUMERIC(20, 10) NOT NULL,
          total_funding_fee NUMERIC(20, 10) DEFAULT 0,
          total_trade_fee NUMERIC(20, 10) DEFAULT 0,
          resets_count INTEGER DEFAULT 0,
          pnl_usd NUMERIC(20, 10),
          UNIQUE(symbol, open_timestamp)
      );
      ```

### 3. 运行机器人

```bash
python src/funding_rate_arbitrage_bot/main.py
```

机器人启动后，会根据 `config.yml` 中设置的 `scan_interval_seconds` 周期性地扫描市场机会并执行操作。所有活动都会在控制台输出日志，并通过Telegram发送通知。

## 📂 项目结构

```
funding_rate_arbitrage/
├── .gitignore
├── pyproject.toml
├── README.md
│
├── config/
│   ├── config.yml             # 生产配置文件 (严禁提交到Git)
│   └── config.yml.example     # 配置文件模板
│
└── src/
    └── funding_rate_arbitrage_bot/
        ├── __init__.py
        ├── main.py              # 主入口与调度器
        ├── config_manager.py    # 配置加载
        ├── database_manager.py  # 数据库交互
        ├── logger_config.py     # 日志配置
        ├── data_fetcher.py      # 市场数据采集
        ├── arbitrage_engine.py  # 策略决策分析
        ├── execution_engine.py  # 交易执行
        ├── position_manager.py  # 仓位监控与管理
        └── notification_manager.py # 通知管理模块
```

## ⚠️ 风险管理

此策略虽然旨在市场中性，但仍存在固有风险，使用者必须完全理解并接受：

- **交易成本侵蚀风险**: 在持续的单边行情中，频繁的仓位重置成本可能高于资金费收入。这是本策略最主要的潜在亏损来源。
- **杠杆与爆仓风险**: 程序故障、API延迟或市场极端波动仍可能导致风险。请使用适度杠杆。
- **执行风险 (单边腿风险)**: 开/平仓的多个订单并非绝对同时成交，期间存在短暂的敞口风险。
- **现货做空/赎回风险**: 负费率策略的借贷成本和额度，以及现货从理财产品中赎回的延迟，都可能带来风险。
- **API与系统风险**: 交易所API可能中断，程序自身也可能出现BUG。

## 📄 开源许可

本项目建议使用 [MIT License](https.opensource.org/licenses/MIT) 开源。
