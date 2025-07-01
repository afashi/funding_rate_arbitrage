import yaml
import urllib
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import threading
import os


@dataclass
class OkxConfig:
    api_key: str
    secret: str
    password: str
    sandbox_mode: bool = field(default=False)


@dataclass
class DatabaseConfig:
    type: str
    host: str
    user: str
    password: str
    dbname: str
    port: int = field(default=5432)

    @property
    def connection_string(self) -> str:
        """生成完整的数据库连接字符串"""
        # 对用户名和密码进行 URL 编码
        safe_user = urllib.parse.quote_plus(self.user)
        safe_password = urllib.parse.quote_plus(self.password)

        # 根据不同类型生成连接字符串
        if self.type == "postgresql":
            return (
                f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.dbname}"
            )
        elif self.type == "mysql":
            return (
                f"mysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.dbname}"
            )
        else:
            raise ValueError(f"Unsupported database type: {self.type}")

    @property
    def async_connection_string(self) -> str:
        """生成异步驱动连接字符串 (适用于 SQLAlchemy 等)"""
        base_str = self.connection_string
        if self.type == "postgresql":
            return base_str.replace("postgresql://", "postgresql+asyncpg://")
        elif self.type == "mysql":
            return base_str.replace("mysql://", "mysql+aiomysql://")
        return base_str

@dataclass
class StrategyConfig:
    min_annualized_return: float = field(default=0.15)
    capital_per_trade_ratio: float = field(default=0.1)
    max_open_positions: int = field(default=5)
    scan_interval_seconds: int = field(default=300)
    enable_negative_rate_strategy: bool = field(default=False)
    enable_spot_earning: bool = field(default=True)


@dataclass
class RiskConfig:
    leverage: float = field(default=3.0)
    margin_reset_threshold: float = field(default=0.2)
    profit_close_threshold: float = field(default=0.05)
    max_allowed_slippage: float = field(default=0.01)


@dataclass
class TelegramConfig:
    enabled: bool = field(default=False)
    bot_token: Optional[str] = field(default=None)
    chat_id: Optional[str] = field(default=None)


@dataclass
class AppConfig:
    okx: OkxConfig
    database: DatabaseConfig
    strategy: StrategyConfig
    risk: RiskConfig
    telegram: TelegramConfig


class ConfigManager:
    _instance = None
    _lock = threading.Lock()
    _config: Optional[AppConfig] = None
    _config_path: Optional[str] = None

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def load_config(self, config_path: str, reload: bool = False) -> AppConfig:
        """加载/重载配置文件，支持线程安全"""
        self._config_path = config_path

        if reload or not self._config:
            with self._lock:
                if reload or not self._config:
                    try:
                        # 环境变量覆盖
                        env_path = os.getenv("APP_CONFIG_PATH", config_path)

                        with open(env_path, 'r', encoding='utf-8') as f:
                            raw_config = yaml.safe_load(f) or {}

                        self._config = self._parse_and_validate(raw_config)
                        return self._config

                    except FileNotFoundError:
                        raise RuntimeError(f"配置文件未找到: {env_path}")
                    except yaml.YAMLError as e:
                        raise ValueError(f"YAML解析错误: {e}")
                    except KeyError as e:
                        raise KeyError(f"缺少必要配置项: {e}")
                    except TypeError as e:
                        raise TypeError(f"配置类型错误: {e}")
        return self.config

    def _parse_and_validate(self, raw_config: Dict[str, Any]) -> AppConfig:
        """带验证的配置解析"""

        # 类型转换器
        def convert_types(config_dict: Dict[str, Any], target_type: type) -> Dict[str, Any]:
            """将字典值转换为目标数据类字段类型"""
            type_hints = target_type.__annotations__
            for k, v in config_dict.items():
                if k in type_hints:
                    target_type_hint = type_hints[k]
                    if isinstance(v, str) and "|" in str(target_type_hint):
                        # 处理Union类型
                        for t in target_type_hint.__args__:
                            try:
                                config_dict[k] = t(v)
                                break
                            except (TypeError, ValueError):
                                pass
                    elif isinstance(target_type_hint, type):
                        try:
                            if target_type_hint is bool and isinstance(v, str):
                                config_dict[k] = v.lower() in ('true', '1', 'yes')
                            elif v is not None:
                                config_dict[k] = target_type_hint(v)
                        except (TypeError, ValueError):
                            pass
            return config_dict

        # 验证必填字段
        required_sections = {'okx', 'database', 'strategy', 'risk'}
        if missing := required_sections - set(raw_config.keys()):
            raise KeyError(f"配置缺少必备模块: {missing}")

        # 转换并创建配置对象
        okx_cfg = OkxConfig(**convert_types(raw_config['okx'], OkxConfig))
        db_cfg = DatabaseConfig(**convert_types(raw_config['database'], DatabaseConfig))
        strategy_cfg = StrategyConfig(**convert_types(raw_config['strategy'], StrategyConfig))
        risk_cfg = RiskConfig(**convert_types(raw_config['risk'], RiskConfig))
        telegram_cfg = TelegramConfig(**convert_types(raw_config.get('telegram', {}), TelegramConfig))

        # 密钥脱敏日志
        safe_config = dict(raw_config)
        safe_config['okx'] = {**raw_config['okx'], 'api_key': '***', 'secret': '***', 'password': '***'}

        return AppConfig(
            okx=okx_cfg,
            database=db_cfg,
            strategy=strategy_cfg,
            risk=risk_cfg,
            telegram=telegram_cfg
        )

    @property
    def config(self) -> AppConfig:
        if not self._config:
            if not self._config_path:
                raise RuntimeError("请先调用load_config()加载配置")
            self.load_config(self._config_path)
        return self._config

    @property
    def masked_config(self) -> Dict[str, Any]:
        """返回脱敏的配置字典（安全日志用）"""
        return self._safe_dict(vars(self.config))

    def _safe_dict(self, data: Any) -> Any:
        """递归脱敏敏感字段"""
        if isinstance(data, dict):
            return {k: self._safe_dict(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._safe_dict(item) for item in data]
        elif hasattr(data, '__dataclass_fields__'):
            return self._safe_dict(vars(data))
        else:
            if 'key' in str(data) or 'secret' in str(data) or 'password' in str(data):
                return '***'
            return data


# 使用示例
if __name__ == "__main__":
    try:
        config_manager = ConfigManager()
        # 使用环境变量或默认路径
        config_path = "D:\\Code\\Workspace\\PyProject\\funding_rate_arbitrage\\config\\config.yml"
        cfg = config_manager.load_config(config_path)

        print("配置加载成功（敏感字段已脱敏）:")
        print(config_manager.masked_config)
        print(config_manager.config.database.connection_string)

    except Exception as e:
        print(f"配置错误: {type(e).__name__}: {e}")
        # 实际项目中应使用日志框架