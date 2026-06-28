import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set


def get_default_program_root() -> str:
    """根据当前平台返回默认 Program 根目录。"""
    if sys.platform.startswith("linux"):
        return "/data/wyj2/Program"
    return "D:/Program"


def get_current_platform_name() -> str:
    """返回 ini 使用的稳定平台名。"""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    return sys.platform


DEFAULT_BUILD_VALUES = {
    "build/type": "cmake",
    "build/build_dir": "build_auto",
    "build/source_subdir": "",
    "build/config": "Release",
    "build/generator": "Visual Studio 16 2019",
    "build/arch": "x64",
    "build/toolset": "v142",
    "build/parallel": "12",
}


class ConfigContext:
    """构建流程上下文。

    内部仍然是一个扁平 dict，key 统一使用 "section/key" 格式。
    这里额外记录哪些 key 来自 ini，方便后续模块区分“用户显式配置”和“自动推导结果”。
    """

    def __init__(
        self,
        values: Optional[Dict[str, str]] = None,
        user_keys: Optional[Iterable[str]] = None,
    ) -> None:
        self._values: Dict[str, str] = dict(values or {})
        self._user_keys: Set[str] = set(user_keys or [])

    def has(self, key: str) -> bool:
        """判断 key 是否存在且不是空字符串。"""
        return key in self._values and self._values[key] != ""

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """读取字符串值。"""
        value = self._values.get(key)
        if value is None:
            return default
        return value

    def require(self, key: str) -> str:
        """读取必填值，不存在时直接抛出异常。"""
        value = self.get(key)
        if value is None or value == "":
            raise KeyError(f"缺少必要配置: {key}")
        return value

    def set(self, key: str, value: Any, user_defined: bool = False) -> None:
        """写入值；默认认为是模块自动推导出的值。"""
        self._values[key] = "" if value is None else str(value)
        if user_defined:
            self._user_keys.add(key)

    def set_default(self, key: str, value: Any) -> None:
        """仅当 key 不存在或为空时写入默认值。"""
        if not self.has(key):
            self.set(key, value)

    def is_user_defined(self, key: str) -> bool:
        """判断 key 是否来自 ini 原始配置。"""
        return key in self._user_keys

    def get_bool(self, key: str, default: bool = False) -> bool:
        """读取布尔值，支持常见 ini 写法。"""
        value = self.get(key)
        if value is None or value == "":
            return default
        return value.strip().lower() in ("1", "true", "yes", "on")

    def get_list(self, key: str, default: Optional[Iterable[str]] = None) -> list[str]:
        """读取逗号分隔列表。"""
        value = self.get(key)
        if value is None or value.strip() == "":
            return list(default or [])
        return [item.strip() for item in value.split(",") if item.strip()]

    def set_default_paths(self, program_root: Optional[str] = None) -> None:
        """写入默认路径根目录；完整文件路径按需计算，不长期保存在 map 中。"""
        root = (program_root or get_default_program_root()).rstrip("/\\")
        self.set_default("path/program_root", root)
        self.set_default("path/source_root", f"{root}/third_party_src_test")
        self.set_default("path/cache_root", f"{root}/third_party_builder/projects/downloads")
        self.set_default("path/project_config_root", f"{root}/third_party_builder/projects")
        self.set_default("path/install_root", f"{root}/third_party_test")

    def set_default_install(self) -> None:
        """写入安装模块默认值。"""
        self.set_default("install/name", "all")

    def set_default_build(self) -> None:
        """写入构建模块默认值，后续集中修改构建策略只需要改 DEFAULT_BUILD_VALUES。"""
        for key, value in DEFAULT_BUILD_VALUES.items():
            self.set_default(key, value)

    def cache_file(self) -> str:
        """根据 cache_root + source/cache_name 计算缓存文件完整路径。"""
        cache_root = self.require("path/cache_root")
        cache_name = self.require("source/cache_name")
        return os.path.normpath(str(Path(cache_root) / cache_name))

    def source_path(self) -> str:
        """根据 source_root + source/source_dir 计算源码目录完整路径。

        如果 ini 显式配置了 source/path，则认为它是特殊本地源码路径，优先使用它。
        """
        if self.has("source/path"):
            return os.path.normpath(self.require("source/path"))
        source_root = self.require("path/source_root")
        source_dir = self.require("source/source_dir")
        return os.path.normpath(str(Path(source_root) / source_dir))

    def install_path(self) -> str:
        """根据 install_root + install/name 计算安装目录完整路径。"""
        install_root = self.require("path/install_root")
        install_name = self.require("install/name")
        return os.path.normpath(str(Path(install_root) / install_name))

    def to_dict(self) -> Dict[str, str]:
        """导出普通 dict，主要用于打印和测试。"""
        return dict(self._values)

    def items(self):
        """按 key 排序返回键值对，便于稳定输出。"""
        return sorted(self._values.items(), key=lambda item: item[0])
