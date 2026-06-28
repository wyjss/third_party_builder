import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List

try:
    from .config_context import ConfigContext
except ImportError:
    from config_context import ConfigContext


def run_build(ctx: ConfigContext, install: bool = False, dry_run: bool = False) -> None:
    """执行构建流程。

    默认 build/type=cmake，ini 不需要为普通项目单独配置 build。
    install=True 时会在 build 成功后继续执行 cmake install。
    """
    build_type = ctx.require("build/type")
    if build_type == "cmake":
        run_cmake_build(ctx, install=install, dry_run=dry_run)
        return
    if build_type == "cmd":
        run_cmd_build(ctx, dry_run=dry_run)
        return
    raise ValueError(f"不支持的 build/type: {build_type}")


def get_cmake_commands(ctx: ConfigContext) -> Dict[str, List[str]]:
    """生成 CMake configure/build/install 命令。"""
    configure = [
        "cmake",
        cmake_source_path(ctx),
        "-G",
        ctx.require("build/generator"),
        "-DCMAKE_BUILD_TYPE=" + ctx.require("build/config"),
        "-DCMAKE_PREFIX_PATH=" + ";".join(prefix_paths(ctx)),
        "-DCMAKE_INSTALL_PREFIX=" + ctx.install_path(),
    ]

    if ctx.has("build/arch"):
        configure.extend(["-A", ctx.require("build/arch")])
    if ctx.has("build/toolset"):
        configure.extend(["-T", ctx.require("build/toolset")])

    for key, value in cmake_options(ctx).items():
        configure.append(f"-D{key}={value}")

    build = [
        "cmake",
        "--build",
        ".",
        "--config",
        ctx.require("build/config"),
    ]
    if ctx.has("build/parallel"):
        build.extend(["--parallel", ctx.require("build/parallel")])

    install = [
        "cmake",
        "--install",
        ".",
        "--config",
        ctx.require("build/config"),
    ]

    return {
        "configure": configure,
        "build": build,
        "install": install,
    }


def run_cmake_build(ctx: ConfigContext, install: bool = False, dry_run: bool = False) -> None:
    """执行标准 CMake 构建。"""
    build_dir = build_path(ctx)

    commands = get_cmake_commands(ctx)
    print_build_plan(ctx, commands)
    if dry_run:
        return

    os.makedirs(build_dir, exist_ok=True)
    os.makedirs(ctx.install_path(), exist_ok=True)
    subprocess.check_call(commands["configure"], cwd=build_dir)
    subprocess.check_call(commands["build"], cwd=build_dir)
    if install:
        subprocess.check_call(commands["install"], cwd=build_dir)


def run_cmd_build(ctx: ConfigContext, dry_run: bool = False) -> None:
    """执行自定义脚本构建，主要兼容少数非标准项目。"""
    script = ctx.require("build/script")
    ini_dir = Path(ctx.require("meta/ini_file")).parent
    script_path = Path(script)
    if not script_path.is_absolute():
        script_path = ini_dir / script_path

    work_dir = build_path(ctx)

    env = {
        **os.environ,
        "INSTALL_PATH": ctx.install_path(),
        "BUILD_PATH": work_dir,
        "SOURCE_PATH": ctx.source_path() if ctx.has("source/source_dir") or ctx.has("source/path") else "",
        "CACHE_FILE": ctx.cache_file() if ctx.has("source/cache_name") else "",
    }

    print(f"构建目录: {work_dir}")
    print(f"安装目录: {ctx.install_path()}")
    print(f"执行脚本: {script_path}")
    if dry_run:
        return

    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(ctx.install_path(), exist_ok=True)
    subprocess.check_call(str(script_path), cwd=work_dir, env=env, shell=True)


def print_build_plan(ctx: ConfigContext, commands: Dict[str, List[str]]) -> None:
    """打印 CMake 构建计划。"""
    print(f"源码目录: {ctx.source_path()}")
    print(f"CMake 源码目录: {cmake_source_path(ctx)}")
    print(f"构建目录: {build_path(ctx)}")
    print(f"安装目录: {ctx.install_path()}")
    print("CMake configure:", command_to_text(commands["configure"]))
    print("CMake build:", command_to_text(commands["build"]))
    print("CMake install:", command_to_text(commands["install"]))


def build_path(ctx: ConfigContext) -> str:
    """构建目录默认位于源码目录内部。"""
    return os.path.normpath(str(Path(ctx.source_path()) / ctx.require("build/build_dir")))


def cmake_source_path(ctx: ConfigContext) -> str:
    """CMakeLists.txt 所在目录，默认就是源码根目录。"""
    source_path = Path(ctx.source_path())
    subdir = (ctx.get("build/source_subdir", "") or "").strip("/\\")
    if subdir:
        return os.path.normpath(str(source_path / subdir))
    return os.path.normpath(str(source_path))


def prefix_paths(ctx: ConfigContext) -> List[str]:
    """生成 CMAKE_PREFIX_PATH。

    默认加入 install_root 下的直接子目录和 install_root 本身。
    额外路径可通过 [dependencies] prefix_paths 覆盖/追加。
    """
    result: List[str] = []
    install_root = ctx.require("path/install_root")
    if os.path.isdir(install_root):
        for item in Path(install_root).iterdir():
            if item.is_dir():
                result.append(str(item))
    result.append(install_root)

    for key in ("dependencies/prefix_paths", "build/prefix_paths", "config/prefix_path"):
        if ctx.has(key):
            result.extend(split_path_list(ctx.require(key)))

    return unique_paths(result)


def cmake_options(ctx: ConfigContext) -> Dict[str, str]:
    """读取 CMake -D 选项。

    只支持 [cmake.options]，其中的字段会原样转换为 CMake -D 参数。
    """
    result: Dict[str, str] = {}
    for key, value in ctx.items():
        if key.startswith("cmake.options/"):
            result[key[len("cmake.options/") :]] = value
    return result


def split_path_list(value: str) -> List[str]:
    """拆分逗号或分号分隔的路径列表。"""
    return [item.strip() for item in re.split(r"[;,]", value) if item.strip()]


def unique_paths(paths: List[str]) -> List[str]:
    """保持顺序去重路径。"""
    result: List[str] = []
    seen = set()
    for path in paths:
        normalized = os.path.normcase(os.path.normpath(path))
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(os.path.normpath(path))
    return result


def command_to_text(command: List[str]) -> str:
    """把命令列表转成适合复制的文本。"""
    return subprocess.list2cmdline(command)
