import configparser
from pathlib import Path

try:
    from .config_context import ConfigContext, get_current_platform_name
except ImportError:
    from config_context import ConfigContext, get_current_platform_name


PLATFORM_NAMES = ("windows", "linux", "macos")


def load_ini_as_context(file_path: str) -> ConfigContext:
    """读取 ini 为扁平 ConfigContext。

    所有字段都会被保存成 "section/key" 形式，例如:
      [source]
      url = https://example.com/a.zip

    会变成:
      source/url = https://example.com/a.zip
    """
    ini_path = Path(file_path).resolve()

    parser = configparser.ConfigParser()
    # 保留 CMake 选项里的大小写，例如 BUILD_SHARED_LIBS。
    parser.optionxform = str
    parser.read(ini_path, encoding="utf-8")

    ctx = ConfigContext()
    ctx.set("meta/ini_file", str(ini_path))
    ctx.set("meta/platform", get_current_platform_name())
    ctx.set("package/name", ini_path.stem)

    _load_sections(ctx, parser)

    _apply_legacy_aliases(ctx)
    ctx.set_default_paths()
    ctx.set_default_install()
    ctx.set_default_build()
    return ctx


def _load_sections(ctx: ConfigContext, parser: configparser.ConfigParser) -> None:
    """读取普通 section，并合并当前平台后缀 section。

    例如当前平台为 windows 时:
      [cmake.options]
      BUILD_TESTING = OFF

      [cmake.options.windows]
      BUILD_TESTING = ON

    最终写入:
      cmake.options/BUILD_TESTING = ON
    """
    platform_name = ctx.require("meta/platform")
    platform_suffix = f".{platform_name}"

    for section in parser.sections():
        if not _split_platform_section(section)[1]:
            _copy_section(ctx, parser, section, section)

    for section in parser.sections():
        base_section, section_platform = _split_platform_section(section)
        if section_platform == platform_name:
            _copy_section(ctx, parser, section, base_section)


def _copy_section(
    ctx: ConfigContext,
    parser: configparser.ConfigParser,
    source_section: str,
    target_section: str,
) -> None:
    """把 source_section 的字段写入 target_section 命名空间。"""
    for option in parser.options(source_section):
        ctx.set(f"{target_section}/{option}", parser.get(source_section, option), user_defined=True)


def _split_platform_section(section: str) -> tuple[str, str]:
    """拆分平台后缀 section，非平台后缀返回空平台名。"""
    for platform_name in PLATFORM_NAMES:
        suffix = f".{platform_name}"
        if section.endswith(suffix):
            return section[: -len(suffix)], platform_name
    return section, ""


def write_source_state(ctx: ConfigContext) -> None:
    """把 source 模块的运行结果回写到 ini 的 [state]。

    只回写稳定的相对信息，不写 cache_file/source_path 这类可由根目录计算出的完整路径。
    """
    ini_file = ctx.require("meta/ini_file")

    parser = configparser.ConfigParser()
    parser.optionxform = str
    parser.read(ini_file, encoding="utf-8")

    if not parser.has_section("state"):
        parser.add_section("state")

    for key in (
        "source/type",
        "source/cache_name",
        "source/source_dir",
        "source/ref",
        "source/depth",
        "source/recursive",
    ):
        if ctx.has(key):
            parser.set("state", key, ctx.require(key))

    with open(ini_file, "w", encoding="utf-8") as file:
        parser.write(file)


def _apply_legacy_aliases(ctx: ConfigContext) -> None:
    """兼容旧版 [config] 字段，但不让 [config_out] 覆盖人工配置。

    新版推荐写法是 [package] + [source]。
    这里的兼容只用于当前仓库平滑过渡，后续 ini 全量迁移后可以删除。
    """
    if not ctx.has("source/url") and ctx.has("config/url"):
        ctx.set("source/url", ctx.get("config/url"), user_defined=True)

    if not ctx.has("source/source_dir") and ctx.has("config/source_name"):
        ctx.set("source/source_dir", ctx.get("config/source_name"), user_defined=True)

    if not ctx.has("source/type") and ctx.has("config/source_type"):
        ctx.set("source/type", ctx.get("config/source_type"), user_defined=True)

    if not ctx.has("source/path") and ctx.has("config/source_path"):
        ctx.set("source/path", ctx.get("config/source_path"), user_defined=True)

    if not ctx.has("install/name") and ctx.has("config/install_name"):
        ctx.set("install/name", ctx.get("config/install_name"), user_defined=True)

    if not ctx.has("build/type") and ctx.has("config/cmd_build"):
        ctx.set("build/type", "cmd")

    if not ctx.has("build/script") and ctx.has("config/cmd_build"):
        ctx.set("build/script", ctx.get("config/cmd_build"), user_defined=True)

    if not ctx.has("build/source_subdir") and ctx.has("config/source_cmake_file_dir"):
        ctx.set("build/source_subdir", ctx.get("config/source_cmake_file_dir"), user_defined=True)

    if not ctx.has("build/build_dir") and ctx.has("config/build_dir_name"):
        ctx.set("build/build_dir", ctx.get("config/build_dir_name"), user_defined=True)
