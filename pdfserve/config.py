# pylint: disable=no-self-argument
import json
import logging
import logging.config
import os
from typing import Any, Union

import temporalloop.config_loader
import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from temporalloop.config_loader import TemporalConfigSchema

LOG_LEVELS: dict[str, int] = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}

LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "pdfserve.logutils.DefaultFormatter",
            "fmt": "%(levelprefix)s %(message)s",
            "use_colors": None,
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "level": "INFO",
        },
    },
    "loggers": {
        "temporalio": {"handlers": ["default"], "level": "INFO", "propagate": True},
        "pdfserve": {"handlers": ["default"], "level": "INFO", "propagate": True},
        "temporalloop": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": True,
        },
    },
}


logger: logging.Logger = logging.getLogger("pdfserve")


class BaseConfig(BaseSettings):
    model_config = SettingsConfigDict()


class AppConfigSchema(BaseConfig):
    env: str = Field(default="dev")
    prometheus_dir: str = Field(default="/tmp/prometheus")


class CorsConfigSchema(BaseConfig):
    allow_origin_regex: str = Field(default=".*")
    allow_origins: list[str] = Field(
        default=[
            "http://localhost:8080",
            "http://localhost:8000",
            "http://localhost",
        ]
    )
    allow_credentials: bool = Field(default=False)
    allow_methods: list[str] = Field(default=["*"])
    allow_headers: list[str] = Field(default=["*"])


class FastAPIConfigSchema(BaseConfig):
    middlewares: list[str] = Field(default_factory=list)
    cors: CorsConfigSchema = Field(default_factory=CorsConfigSchema)
    token: str = Field(default="")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8080)
    reload: bool = Field(default=False)

    @field_validator("port")
    def convert_port(cls, v) -> int:
        return int(v)


class LoggingConfigSchema(BaseConfig):
    use_colors: bool = Field(default=True)
    log_config: dict[str, Any] | str | None = Field(
        default_factory=lambda: LOGGING_CONFIG
    )
    level: str = Field(default="info")


class SentryConfigSchema(BaseConfig):
    dsn: str | None = Field(default=None)
    environment: str | None = Field(default=None)
    release: str | None = Field(default=None)
    traces_sample_rate: float | None = Field(default=None)


class S3ConfigSchema(BaseConfig):
    endpoint: str = Field(default="https://s3.eu-central-1.amazonaws.com")
    access_key: str = Field(default="")
    secret_key: str = Field(default="")
    region: str = Field(default="eu-central-1")
    prefix: str = Field(default="pdfserve/")
    bucket: str = Field(default="pdfserve")


# Main configuration schema
class ConfigSchema(BaseConfig):
    # pdfserve: PDFServeConfigSchema = Field(default_factory=PDFServeConfigSchema)
    temporalio: TemporalConfigSchema = Field(default_factory=TemporalConfigSchema)
    logging: LoggingConfigSchema = Field(default_factory=LoggingConfigSchema)
    server: FastAPIConfigSchema = Field(default_factory=FastAPIConfigSchema)
    sentry: SentryConfigSchema = Field(default_factory=SentryConfigSchema)
    app: AppConfigSchema = Field(default_factory=AppConfigSchema)
    s3: S3ConfigSchema = Field(  # pylint: disable=invalid-name
        default_factory=S3ConfigSchema
    )
    model_config = SettingsConfigDict(
        env_prefix="PDFSERVE_", env_nested_delimiter="__", case_sensitive=False
    )


class Config:
    def __init__(self, conf: ConfigSchema):
        self.loaded = False
        self._conf = conf
        self._set_conf(conf)

    @property
    def conf(self) -> ConfigSchema:
        return self._conf

    def _set_conf(self, conf: ConfigSchema) -> None:
        self._conf = conf
        self.looper_conf = temporalloop.config_loader.config_from_dict(
            conf.model_dump()
        )
        self.load(force=True)

    @property
    def logging(self) -> LoggingConfigSchema:
        return self.conf.logging

    @property
    def temporalio(self) -> TemporalConfigSchema:
        return self.conf.temporalio

    @property
    def server(self) -> FastAPIConfigSchema:
        return self.conf.server

    @property
    def s3(self) -> S3ConfigSchema:
        return self.conf.s3

    @property
    def sentry(self) -> SentryConfigSchema:
        return self.conf.sentry

    # @property
    # def pdfserve(self) -> PDFServeConfigSchema:
    #     return self.conf.pdfserve

    @property
    def app(self) -> AppConfigSchema:
        return self.conf.app

    def load(self, force=True) -> bool:
        if not self.loaded or force:
            self.looper_conf.loaded = False
            self.looper_conf.load()
            self.configure_logging()
            self.loaded = True
            return True
        raise RuntimeError("Config already loaded")

    def configure_logging(self) -> None:
        log_config = self.logging.log_config
        use_colors = self.logging.use_colors
        log_level = self.logging.level

        if log_config:
            if isinstance(log_config, dict):
                if use_colors in (True, False):
                    log_config["formatters"]["default"]["use_colors"] = use_colors
                logging.config.dictConfig(log_config)
            elif log_config.endswith(".json"):
                with open(log_config, encoding="utf-8") as file:
                    loaded_config = json.load(file)
                    logging.config.dictConfig(loaded_config)
            elif log_config.endswith((".yaml", ".yml")):
                with open(log_config, encoding="utf-8") as file:
                    loaded_config = yaml.safe_load(file)
                    logging.config.dictConfig(loaded_config)
            else:
                # See the note about fileConfig() here:
                # https://docs.python.org/3/library/logging.config.html#configuration-file-format
                logging.config.fileConfig(log_config, disable_existing_loggers=False)
        if log_level is not None:
            if isinstance(log_level, str):
                log_level = LOG_LEVELS[log_level.lower()]
            logging.getLogger("pdfserve").setLevel(log_level)
            logging.getLogger("root").setLevel(log_level)

    @classmethod
    def from_yaml(cls, file_path: str) -> "Config":
        with open(file_path, "r", encoding="utf-8") as file:
            config_dict = yaml.safe_load(file)
        return cls(ConfigSchema(**config_dict))

    @classmethod
    def default_config(cls) -> "Config":
        return cls(ConfigSchema())

    @classmethod
    def auto_config(cls, path: str | None = None) -> "Config":
        if path:
            paths = [path]
        else:
            paths = [
                os.environ.get("PDFSERVE_CONFIG", "localconfig.yaml"),
                "config.yaml",
            ]
        config: "Config" = cls.default_config()
        matched = False
        for p in paths:
            if os.path.exists(p):
                config = cls.from_yaml(p)
                config.load()
                logger.info("Config loaded: %s", p)
                matched = True
                break
        if not matched:
            logger.warning("No config file found, using default config")
            config.load()
        return config

    # def merge(self, other: Union["Config", ConfigSchema]) -> None:
    #     if isinstance(other, ConfigSchema):
    #         otherconf = other
    #     else:
    #         otherconf = other.conf
    #     self._set_conf(ConfigSchema(self.conf.copy(update=otherconf.model_dump(), deep=True)))

    def replace(self, other: Union["Config", ConfigSchema]) -> None:
        if isinstance(other, ConfigSchema):
            otherconf = other
        else:
            otherconf = other.conf
        self._set_conf(otherconf)

    def dump(self, destpath: str = "") -> str:
        dump = yaml.dump(self.conf.model_dump())
        if destpath:
            with open(destpath, "w", encoding="utf-8") as file:
                file.write(dump)
        return dump


# Singleton to get the Configuration instance
# pylint: disable=super-init-not-called
class GConfig(Config):
    __instance__ = None

    def __init__(self, path: str | None = None):
        self.path = path

    def __new__(cls, path: str | None = None):
        if cls.__instance__ is None:
            cls.__instance__ = Config.auto_config(path)
        return cls.__instance__

    @classmethod
    def reinit(cls) -> None:
        cls.__instance__ = None
