import argparse
import json
from pathlib import Path

try:
    from .build import build_path, cmake_source_path, run_build
    from .ini_loader import load_ini_as_context, write_source_state
    from .source import apply_source_defaults, prepare_source
except ImportError:
    from build import build_path, cmake_source_path, run_build
    from ini_loader import load_ini_as_context, write_source_state
    from source import apply_source_defaults, prepare_source


def resolve_ini_path(value: str) -> str:
    """支持传入 ini 路径，也支持直接传入项目名。"""
    path = Path(value)
    if path.exists():
        return str(path)

    if path.suffix != ".ini":
        # 从脚本位置反推工程根目录，避免在 py2 目录执行时找错 projects。
        project_root = Path(__file__).resolve().parent.parent
        candidate = project_root / "projects" / f"{value}.ini"
        if candidate.exists():
            return str(candidate)

    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="py2 source 模块测试入口")
    parser.add_argument("ini", help="项目 ini 路径，或 projects 目录下的项目名")
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="真正执行下载/复制和解压；默认只推导 source 字段",
    )
    parser.add_argument(
        "--write-state",
        action="store_true",
        help="把 source 模块的运行结果回写到 ini 的 [state]",
    )
    parser.add_argument(
        "--dry-run-build",
        action="store_true",
        help="只打印构建命令，不下载、不编译、不安装",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="准备源码并执行构建",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="准备源码、执行构建并安装",
    )
    args = parser.parse_args()

    ctx = load_ini_as_context(resolve_ini_path(args.ini))
    if args.build or args.install:
        prepare_source(ctx)
        run_build(ctx, install=args.install)
    elif args.dry_run_build:
        apply_source_defaults(ctx)
        run_build(ctx, install=True, dry_run=True)
    elif args.prepare:
        prepare_source(ctx)
    else:
        apply_source_defaults(ctx)

    if args.write_state:
        write_source_state(ctx)

    # 只打印本阶段关心的字段，方便观察 source 推导结果。
    result = {
        "meta/platform": ctx.get("meta/platform"),
        "package/name": ctx.get("package/name"),
        "source/type": ctx.get("source/type"),
        "source/url": ctx.get("source/url"),
        "source/path": ctx.get("source/path"),
        "source/ref": ctx.get("source/ref"),
        "source/depth": ctx.get("source/depth"),
        "source/recursive": ctx.get("source/recursive"),
        "source/cache_name": ctx.get("source/cache_name"),
        "source/cache_file": ctx.cache_file() if ctx.has("source/cache_name") else None,
        "source/source_dir": ctx.get("source/source_dir"),
        "source/source_path": ctx.source_path() if ctx.has("source/source_dir") else None,
        "install/name": ctx.get("install/name"),
        "install/path": ctx.install_path(),
        "build/type": ctx.get("build/type"),
        "build/build_dir": ctx.get("build/build_dir"),
        "build/path": build_path(ctx) if ctx.has("source/source_dir") or ctx.has("source/path") else None,
        "build/source_subdir": ctx.get("build/source_subdir"),
        "build/cmake_source_path": cmake_source_path(ctx) if ctx.has("source/source_dir") or ctx.has("source/path") else None,
        "build/config": ctx.get("build/config"),
        "build/generator": ctx.get("build/generator"),
        "build/arch": ctx.get("build/arch"),
        "build/toolset": ctx.get("build/toolset"),
        "build/parallel": ctx.get("build/parallel"),
        "build/script": ctx.get("build/script"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
