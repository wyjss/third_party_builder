import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional, Tuple

try:
    from .config_context import ConfigContext
except ImportError:
    from config_context import ConfigContext


ARCHIVE_SUFFIXES = (
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".tgz",
    ".tbz2",
    ".txz",
    ".zip",
)


def apply_source_defaults(ctx: ConfigContext) -> None:
    """推导 source 模块的核心变量。

    当前阶段只把真正需要跨模块共享的值写回 map:
      source/cache_name  缓存文件名
      source/source_dir  源码目录名

    完整路径通过 ctx.cache_file() / ctx.source_path() 按需计算。
    """
    package_name = ctx.require("package/name")

    if ctx.has("source/source_dir"):
        ctx.set("source/source_dir", normalize_source_dir(ctx.require("source/source_dir")))

    # tag/branch 在 source 模块里统一收敛成 ref，后续 git 逻辑只关心一个字段。
    if not ctx.has("source/ref"):
        if ctx.has("source/tag"):
            ctx.set("source/ref", ctx.require("source/tag"))
        elif ctx.has("source/branch"):
            ctx.set("source/ref", ctx.require("source/branch"))

    if not ctx.has("source/type"):
        ctx.set("source/type", infer_source_type(ctx))

    source_type = ctx.require("source/type")

    if source_type == "local":
        _apply_local_defaults(ctx)
        return

    if not ctx.has("source/url"):
        raise KeyError("缺少必要配置: source/url")

    if source_type == "git":
        _apply_git_defaults(ctx, package_name)
        return

    if not ctx.has("source/cache_name"):
        ctx.set("source/cache_name", infer_cache_name(package_name, ctx.require("source/url"), source_type))

    if source_type == "archive" and not ctx.has("source/source_dir"):
        ctx.set("source/source_dir", infer_source_dir(ctx.require("source/cache_name")))


def prepare_source(ctx: ConfigContext) -> None:
    """准备源码。

    会执行:
      1. 推导 source/cache_name 和 source/source_dir
      2. local 类型校验目录，git 类型执行最小 clone
      3. archive/file 类型下载或复制缓存文件
      4. archive 类型解压到临时目录，再移动成 source/source_dir 指定的最终目录名
    """
    apply_source_defaults(ctx)
    source_type = ctx.require("source/type")

    if source_type == "local":
        _ensure_local_source_exists(ctx)
        return

    if source_type == "git":
        clone_git_source(ctx)
        return

    if source_type == "archive":
        source_path = ctx.source_path()
        if os.path.isdir(source_path):
            print(f"源码目录已存在，跳过下载和解压: {source_path}")
            return

    cache_file = ctx.cache_file()
    if not os.path.exists(cache_file):
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        download_to_file(ctx.require("source/url"), cache_file)
    else:
        print(f"使用已有缓存文件: {cache_file}")

    if source_type == "file":
        return

    if source_type != "archive":
        raise ValueError(f"暂不支持的 source/type: {source_type}")

    extract_archive_to_source(cache_file, source_path)


def infer_cache_name(package_name: str, url: str, source_type: str = "archive") -> str:
    """根据 package/name 和 URL 推导缓存文件名。

    规则:
      .../zstd-v1.5.zip -> zstd-v1.5.zip
      .../v1.5.zip      -> zstd-v1.5.zip
      .../download?id=1 -> zstd-download
      https://x/y/      -> zstd-download
    """
    file_name = get_url_file_name(url) or "download"
    file_name = normalize_cache_name(file_name)

    stem, _ = split_archive_suffix(file_name)
    if contains_package_name(stem, package_name):
        return file_name

    return f"{package_name}-{file_name}"


def infer_source_dir(cache_name: str) -> str:
    """根据缓存文件名推导源码目录名。"""
    stem, _ = split_archive_suffix(cache_name)
    return normalize_source_dir(stem)


def infer_source_type(ctx: ConfigContext) -> str:
    """自动推导 source/type。"""
    if ctx.has("source/path") and not ctx.has("source/url"):
        return "local"

    if ctx.has("source/cache_name"):
        cache_name = ctx.require("source/cache_name")
        if is_archive_name(cache_name):
            return "archive"
        return "file"

    url = ctx.get("source/url", "") or ""
    if is_git_url(url):
        return "git"

    file_name = get_url_file_name(url)
    if is_archive_name(file_name):
        return "archive"
    if has_useful_download_name(file_name):
        return "file"
    return "file"


def get_url_file_name(url: str) -> str:
    """从 URL path 中取最后一段文件名，自动忽略 query 和 fragment。"""
    parsed = urllib.parse.urlparse(url)
    path = urllib.parse.unquote(parsed.path)
    return os.path.basename(path)


def split_archive_suffix(file_name: str) -> Tuple[str, str]:
    """拆分压缩包文件名，支持 .tar.gz 这类多段后缀。"""
    lower_name = file_name.lower()
    for suffix in ARCHIVE_SUFFIXES:
        if lower_name.endswith(suffix):
            return file_name[: -len(suffix)], file_name[-len(suffix) :]
    # 弱 URL 可能是 v1.5 这类名字，不能把 .5 当作扩展名剥掉。
    return file_name, ""


def is_archive_name(file_name: str) -> bool:
    """判断文件名是否是当前支持的压缩包。"""
    lower_name = file_name.lower()
    return any(lower_name.endswith(suffix) for suffix in ARCHIVE_SUFFIXES)


def has_useful_download_name(file_name: str) -> bool:
    """判断 URL 最后一段是否足以当作下载文件名。

    弱 URL 现在也会自动生成 cache_name；这个函数只用于判断能否自动推导 source/type。
    """
    if not file_name:
        return False
    if is_archive_name(file_name):
        return True
    suffix = os.path.splitext(file_name)[1]
    return bool(suffix and re.search(r"[a-zA-Z]", suffix))


def is_git_url(url: str) -> bool:
    """判断 URL 是否明显是 git 仓库地址。"""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    return path.endswith(".git") or parsed.scheme in ("git", "ssh")


def contains_package_name(stem: str, package_name: str) -> bool:
    """判断文件名主体是否已经包含包名。"""
    return normalize_token(package_name) in normalize_token(stem)


def normalize_token(value: str) -> str:
    """把名字归一化后用于宽松比较。"""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def normalize_cache_name(value: str) -> str:
    """把 URL 最后一段整理成可用缓存文件名。"""
    cache_name = value.strip().strip("/\\")
    cache_name = re.sub(r"[<>:\"/\\|?*]+", "-", cache_name)
    cache_name = cache_name.strip(". ")
    return cache_name or "download"


def normalize_dir_name(value: str) -> str:
    """源码目录统一去掉结尾的路径分隔符。"""
    return value.strip().rstrip("/\\")


def normalize_source_dir(value: str) -> str:
    """规范化源码目录名，并保证它是相对目录。"""
    source_dir = normalize_dir_name(value)
    path = Path(source_dir)
    if not source_dir or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"source/source_dir 必须是相对目录名: {value}")
    return source_dir


def download_to_file(url: str, save_file: str) -> None:
    """下载 HTTP/HTTPS 文件，或复制本地文件到缓存。"""
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme in ("http", "https"):
        print(f"正在下载: {url}")
        with urllib.request.urlopen(url) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            if total_size:
                print(f"文件大小: {_format_bytes(total_size)}")
            else:
                print("文件大小: 未知")
            downloaded = 0
            with open(save_file, "wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        percent = downloaded / total_size * 100
                        progress = f"{_format_bytes(downloaded)} / {_format_bytes(total_size)} ({percent:.2f}%)"
                    else:
                        progress = _format_bytes(downloaded)
                    print(f"\r已下载: {progress}", end="", flush=True)
            print()
        print(f"下载完成: {save_file}")
        return

    local_file = _resolve_local_url(url)
    if local_file:
        print(f"正在复制本地缓存: {local_file}")
        shutil.copy2(local_file, save_file)
        print(f"复制完成: {save_file} ({_format_bytes(os.path.getsize(save_file))})")
        return

    raise ValueError(f"不支持的 source/url: {url}")


def clone_git_source(ctx: ConfigContext) -> None:
    """执行最小 git clone。

    默认 depth=1、recursive=true；ref 可以是 tag、branch 或其它 git 可识别的引用。
    """
    source_path = ctx.source_path()
    if os.path.isdir(source_path):
        print(f"git 源码目录已存在，跳过 clone: {source_path}")
        return

    os.makedirs(os.path.dirname(source_path), exist_ok=True)

    command = ["git", "clone", "--depth", ctx.require("source/depth")]
    if ctx.has("source/ref"):
        command.extend(["--branch", ctx.require("source/ref")])
    if ctx.get_bool("source/recursive", default=True):
        command.extend(["--recurse-submodules", "--shallow-submodules"])
    command.extend([ctx.require("source/url"), source_path])

    print("执行 git clone:", " ".join(command))
    subprocess.check_call(command)


def extract_archive_to_source(archive_file: str, source_path: str) -> None:
    """解压到临时目录，再移动成最终源码目录名。"""
    source_root = os.path.dirname(source_path)
    os.makedirs(source_root, exist_ok=True)

    if os.path.isdir(source_path):
        print(f"源码目录已存在，跳过解压: {source_path}")
        return

    print(f"正在解压: {archive_file}")
    temp_dir = tempfile.mkdtemp(prefix=".extract_", dir=source_root)
    temp_dir_alive = True
    try:
        root_dir = extract_archive(archive_file, temp_dir)
        extracted_path = temp_dir
        if root_dir:
            extracted_path = os.path.join(temp_dir, root_dir)

        if os.path.exists(source_path):
            print(f"目标源码目录已存在，保留现有目录: {source_path}")
            return

        shutil.move(extracted_path, source_path)
        if extracted_path == temp_dir:
            temp_dir_alive = False
        print(f"源码目录已准备: {source_path}")
    finally:
        if temp_dir_alive:
            _remove_temp_dir(temp_dir, source_root)


def extract_archive(archive_file: str, source_root: str) -> Optional[str]:
    """解压压缩包，并返回压缩包内唯一的顶层目录名。"""
    os.makedirs(source_root, exist_ok=True)

    if zipfile.is_zipfile(archive_file):
        with zipfile.ZipFile(archive_file, "r") as archive:
            root_dir = _get_zip_root_dir(archive)
            _safe_extract_zip(archive, source_root)
            return root_dir

    if tarfile.is_tarfile(archive_file):
        with tarfile.open(archive_file, "r:*") as archive:
            root_dir = _get_tar_root_dir(archive)
            _safe_extract_tar(archive, source_root)
            return root_dir

    raise ValueError(f"不支持的压缩包格式: {archive_file}")


def _apply_local_defaults(ctx: ConfigContext) -> None:
    """本地源码模式下，source_dir 默认取 source/path 的目录名。"""
    if not ctx.has("source/path"):
        raise KeyError("source/type=local 时必须配置 source/path")
    if not ctx.has("source/source_dir"):
        ctx.set("source/source_dir", normalize_source_dir(os.path.basename(normalize_dir_name(ctx.require("source/path")))))


def _apply_git_defaults(ctx: ConfigContext, package_name: str) -> None:
    """git 源码的默认值。"""
    if not ctx.has("source/source_dir"):
        ctx.set("source/source_dir", infer_git_source_dir(package_name, ctx.require("source/url")))
    ctx.set_default("source/depth", "1")
    ctx.set_default("source/recursive", "true")


def infer_git_source_dir(package_name: str, url: str) -> str:
    """根据 git URL 推导源码目录名，失败时退回 package/name。"""
    repo_name = get_url_file_name(url)
    if repo_name.lower().endswith(".git"):
        repo_name = repo_name[:-4]
    if not repo_name:
        repo_name = package_name
    return normalize_source_dir(repo_name)


def _ensure_local_source_exists(ctx: ConfigContext) -> None:
    """校验本地源码目录存在。"""
    source_path = ctx.source_path()
    if not os.path.isdir(source_path):
        raise FileNotFoundError(f"本地源码目录不存在: {source_path}")
    print(f"使用本地源码目录: {source_path}")


def _resolve_local_url(url: str) -> Optional[str]:
    """支持 file:// URL 和普通本地路径。"""
    # Windows 的 C:\xxx 会被 urlparse 误判成 scheme=c，所以先按普通路径判断。
    if os.path.exists(url):
        return url

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        path = urllib.parse.unquote(parsed.path)
        if os.name == "nt" and path.startswith("/"):
            path = path[1:]
        return path
    return None


def _get_zip_root_dir(archive: zipfile.ZipFile) -> Optional[str]:
    """从 zip 成员中识别唯一顶层目录。"""
    roots = set()
    for name in archive.namelist():
        normalized = name.replace("\\", "/").strip("/")
        if normalized:
            roots.add(normalized.split("/", 1)[0])
    return next(iter(roots)) if len(roots) == 1 else None


def _get_tar_root_dir(archive: tarfile.TarFile) -> Optional[str]:
    """从 tar 成员中识别唯一顶层目录。"""
    roots = set()
    for member in archive.getmembers():
        normalized = member.name.replace("\\", "/").strip("/")
        if normalized:
            roots.add(normalized.split("/", 1)[0])
    return next(iter(roots)) if len(roots) == 1 else None


def _safe_extract_zip(archive: zipfile.ZipFile, target_dir: str) -> None:
    """安全解压 zip，避免压缩包条目逃逸到目标目录外。"""
    target_root = Path(target_dir).resolve()
    members = archive.infolist()
    for member in members:
        target_path = (target_root / member.filename).resolve()
        if not _is_relative_to(target_path, target_root):
            raise ValueError(f"zip 条目路径不安全: {member.filename}")
    total = len(members)
    for index, member in enumerate(members, start=1):
        archive.extract(member, target_dir)
        print(f"\r正在解压: {index}/{total}", end="", flush=True)
    if total:
        print()


def _safe_extract_tar(archive: tarfile.TarFile, target_dir: str) -> None:
    """安全解压 tar，避免压缩包条目逃逸到目标目录外。"""
    target_root = Path(target_dir).resolve()
    members = archive.getmembers()
    for member in members:
        target_path = (target_root / member.name).resolve()
        if not _is_relative_to(target_path, target_root):
            raise ValueError(f"tar 条目路径不安全: {member.name}")
    total = len(members)
    for index, member in enumerate(members, start=1):
        archive.extract(member, target_dir)
        print(f"\r正在解压: {index}/{total}", end="", flush=True)
    if total:
        print()


def _remove_temp_dir(temp_dir: str, source_root: str) -> None:
    """删除临时解压目录，删除前确认它仍位于 source_root 内。"""
    temp_path = Path(temp_dir).resolve()
    root_path = Path(source_root).resolve()
    if temp_path.exists() and _is_relative_to(temp_path, root_path):
        shutil.rmtree(temp_path)


def _format_bytes(size: int) -> str:
    """把字节数格式化成适合进度提示的短文本。"""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024


def _is_relative_to(path: Path, root: Path) -> bool:
    """兼容旧 Python 的 Path.is_relative_to。"""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
