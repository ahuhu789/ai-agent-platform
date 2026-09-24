"""
Cấu hình cho LLM Factory.
Đọc file YAML và cung cấp dataclass cho provider và config tổng thể.
"""

import yaml
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from .exceptions import LLMConfigError


@dataclass
class ProviderConfig:
    """
    Cấu hình cho một provider cụ thể.

    Attributes:
        model (str): Tên model được sử dụng (bắt buộc).
        temperature (float): Nhiệt độ sinh (mặc định 0.7).
        timeout (Optional[int]): Timeout tính bằng giây (mặc định 30).
        extra (Dict[str, Any]): Các tham số bổ sung dành riêng cho provider.
    """
    model: str
    temperature: float = 0.7
    timeout: Optional[int] = 30
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMConfig:
    """
    Cấu hình tổng thể cho LLM Factory.

    Attributes:
        active_provider (str): Tên provider đang được kích hoạt.
        providers (Dict[str, ProviderConfig]): Danh sách các provider có sẵn.
    """
    active_provider: str
    providers: Dict[str, ProviderConfig]


def load_config(path: str = "config.yaml") -> LLMConfig:
    """
    Đọc file YAML và trả về đối tượng LLMConfig.

    Args:
        path (str): Đường dẫn tới file cấu hình.

    Returns:
        LLMConfig: Đối tượng cấu hình đã được validate.

    Raises:
        LLMConfigError: Khi file không tồn tại, YAML không hợp lệ,
                        thiếu trường bắt buộc hoặc active_provider không khớp.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise LLMConfigError(f"Config file not found: {path}")
    except yaml.YAMLError as e:
        raise LLMConfigError(f"Invalid YAML in config file: {e}")

    # Kiểm tra cấu trúc cơ bản
    if not isinstance(data, dict):
        raise LLMConfigError("Config must contain a YAML mapping")
    if "active_provider" not in data:
        raise LLMConfigError("Missing 'active_provider' in config")
    if "providers" not in data or not isinstance(data["providers"], dict):
        raise LLMConfigError("Missing 'providers' section in config")

    # Parse từng provider
    providers = {}
    for name, provider_data in data["providers"].items():
        if not isinstance(provider_data, dict):
            raise LLMConfigError(f"Provider '{name}' must be a mapping")
        if "model" not in provider_data:
            raise LLMConfigError(f"Provider '{name}' missing 'model' field")

        providers[name] = ProviderConfig(
            model=provider_data["model"],
            temperature=provider_data.get("temperature", 0.7),
            timeout=provider_data.get("timeout", 30),
            extra=provider_data.get("extra", {}),
        )

    # Kiểm tra active_provider có tồn tại trong danh sách providers không
    active = data["active_provider"]
    if active not in providers:
        raise LLMConfigError(
            f"active_provider '{active}' not found in providers. "
            f"Available providers: {list(providers.keys())}"
        )

    return LLMConfig(active_provider=active, providers=providers)