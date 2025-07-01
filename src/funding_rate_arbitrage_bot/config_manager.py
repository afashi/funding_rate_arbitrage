import os
from functools import lru_cache
from typing import Optional

import yaml
# 导入 Pydantic 的核心组件
from pydantic import BaseModel, Field, computed_field, SecretStr


# 1. 使用 Pydantic 的 BaseModel 定义配置模型
# 它会自动处理类型转换和验证

class OkxConfig(BaseModel):
    # 使用 SecretStr 保护敏感信息
    api_key: SecretStr
    secret: SecretStr
    password: SecretStr
    sandbox_mode: bool = False


class DatabaseConfig(BaseModel):
    type: str
    host: str
    user: str
    password: SecretStr
    dbname: str
    port: int = 5432

    # 使用 @computed_field 替代 @property，功能更强大
    @computed_field
    @property
    def connection_string(self) -> str:
        """生成 SQLAlchemy 同步连接字符串。"""
        # SecretStr 需要用 .get_secret_value() 来获取真实值
        safe_password = self.password.get_secret_value()
        return f"{self.type}://{self.user}:{safe_password}@{self.host}:{self.port}/{self.dbname}"

    @computed_field
    @property
    def async_connection_string(self) -> str:
        """生成 SQLAlchemy 异步连接字符串。"""
        sync_conn_str = self.connection_string
        if self.type == "postgresql":
            return sync_conn_str.replace("postgresql://", "postgresql+asyncpg://")
        elif self.type == "mysql":
            return sync_conn_str.replace("mysql://", "mysql+aiomysql://")
        return sync_conn_str


class StrategyConfig(BaseModel):
    min_annualized_return: float = Field(0.15, gt=0, description="年化回报率阈值必须大于0")
    capital_per_trade_ratio: float = Field(0.1, gt=0, le=1, description="单次投入资金比例需在(0, 1]之间")
    max_open_positions: int = Field(5, gt=0)
    scan_interval_seconds: int = Field(300, gt=0)
    enable_negative_rate_strategy: bool = False
    enable_spot_earning: bool = True


class RiskConfig(BaseModel):
    leverage: float = Field(3.0, gt=0)
    margin_reset_threshold: float = Field(0.2, gt=0, lt=1)
    profit_close_threshold: float = Field(0.05)
    max_allowed_slippage: float = Field(0.01, gt=0, lt=1)


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token: Optional[SecretStr] = None
    chat_id: Optional[str] = None


class AppConfig(BaseModel):
    # 嵌套模型，Pydantic 会自动递归解析
    okx: OkxConfig
    database: DatabaseConfig
    strategy: StrategyConfig
    risk: RiskConfig
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


# 2. 简化配置加载逻辑
# 使用一个带缓存的函数，而不是一个复杂的单例类
@lru_cache(maxsize=None)
def get_config(config_path: str) -> AppConfig:
    """
    从 YAML 文件加载、解析并验证配置。
    使用 lru_cache 实现单例效果，确保配置文件只被读取和解析一次。
    """
    # 优先使用环境变量指定的路径
    env_path = os.getenv("APP_CONFIG_PATH", config_path)

    if not os.path.exists(env_path):
        raise FileNotFoundError(f"配置文件未找到: {env_path}")

    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)

        # 核心：只需一行代码，Pydantic 就会完成所有解析和验证工作！
        return AppConfig.model_validate(raw_config)

    except yaml.YAMLError as e:
        raise ValueError(f"YAML 格式错误: {e}")
    except Exception as e:
        # Pydantic 的 ValidationError 会提供非常清晰的错误信息
        # 例如："1 validation error for AppConfig\ndatabase -> password\n  Field required [type=missing, ...]"
        raise RuntimeError(f"加载配置时出错: {e}")


# 3. 使用示例
if __name__ == "__main__":
    try:
        # 假设配置文件在项目根目录的 'config/config.yml'
        # 你可以根据实际情况修改这个路径
        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'config.yml')

        # 第一次调用，会加载文件
        app_config = get_config(config_path)

        # 后续调用，会直接从缓存返回，不会再次读取文件
        another_config_ref = get_config(config_path)

        print(f"配置对象是否为同一个实例: {app_config is another_config_ref}")

        # Pydantic 模型可以直接打印，敏感字段已自动脱敏
        print("\n--- 配置加载成功 (Pydantic 自动脱敏) ---")
        print(app_config)

        # 访问数据库连接字符串
        print("\n--- 数据库连接字符串 ---")
        print(f"异步连接: {app_config.database.async_connection_string}")

        # 获取真实密钥值
        print("\n--- 获取真实密钥 ---")
        api_key_value = app_config.okx.api_key.get_secret_value()
        print(f"OKX API Key: {api_key_value}")

    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"配置错误: {e}")
