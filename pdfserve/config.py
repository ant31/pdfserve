# pylint: disable=no-self-argument
import logging
import logging.config
from typing import Any, Type

import ant31box.config
from ant31box.config import FastAPIConfigSchema, GConfig, LoggingConfigSchema, S3ConfigSchema
from pydantic import Field
from pydantic_settings import SettingsConfigDict

LOGGING_CONFIG: dict[str, Any] = ant31box.config.LOGGING_CONFIG
LOGGING_CONFIG["loggers"].update({"pdfserve": {"handlers": ["default"], "level": "INFO", "propagate": True}})

logger: logging.Logger = logging.getLogger("pdfserve")

ENVPREFIX = "PDFSERVE"


class FastAPIConfigCustomSchema(FastAPIConfigSchema):
    server: str = Field(default="pdfserve.server.server:serve")


class S3ConfigCustomSchema(S3ConfigSchema):
    bucket: str = Field(default="pdfserve")
    prefix: str = Field(default="pdfserve/")
    endpoint: str = Field(default="https://s3.eu-central-1.amazonaws.com")
    region: str = Field(default="eu-central-1")


class LoggingConfigCustomSchema(LoggingConfigSchema):
    log_config: dict[str, Any] | str | None = Field(default_factory=lambda: LOGGING_CONFIG)


# Main configuration schema
class ConfigSchema(ant31box.config.ConfigSchema):
    model_config = SettingsConfigDict(
        env_prefix=f"{ENVPREFIX}_", env_nested_delimiter="__", case_sensitive=False, extra="allow"
    )
    name: str = Field(default="pdfserve")
    # pdfserve: PDFServeConfigSchema = Field(default_factory=PDFServeConfigSchema)
    logging: LoggingConfigSchema = Field(default_factory=LoggingConfigSchema)
    server: FastAPIConfigCustomSchema = Field(default_factory=FastAPIConfigCustomSchema)
    s3: S3ConfigCustomSchema = Field(default_factory=S3ConfigCustomSchema)


class Config(ant31box.config.Config[ConfigSchema]):
    _env_prefix = ENVPREFIX
    __config_class__: Type[ConfigSchema] = ConfigSchema

    @property
    def s3(self) -> S3ConfigSchema:
        return self.conf.s3


def config(path: str | None = None, reload: bool = False) -> Config:
    GConfig[Config].set_conf_class(Config)
    if reload:
        GConfig[Config].reinit()
    # load the configuration
    GConfig[Config](path)
    # Return the instance of the configuration
    return GConfig[Config].instance()
