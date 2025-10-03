import configparser
from typing import Dict, Any
import os
import urllib.parse
import urllib.request
import shutil
import zipfile
from pathlib import Path
import re

# 从ini文件中解析目标项目的配置信息
def parse_project_config_file(file_path: str) -> Dict[str, Any]:
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(file_path)
    
    result = {}

    file_name_with_ext = os.path.basename(file_path)  # 返回 'test.ini'
    # 去掉扩展名
    name = os.path.splitext(file_name_with_ext)[0] 
    result['ini'] = file_path
    result['name'] = name

    if 'config' in config:
        for option in config.options('config'):
            value = config.get('config', option)
            result[option] = value
    # 读取上次的结果
    if 'config_out' in config:
        for option in config.options('config_out'):
            value = config.get('config_out', option)
            result[option] = value
            
    if not result.get('install_name'):
        result['install_name'] = 'all'
        print('[{}] set default install name all'.format(name))

    if 'options' in config:
        cmake_options = {}
        for option in config.options('options'):
            value = config.get('options', option)
            cmake_options[option] = value
        result['options'] = cmake_options

    return result

# 更新ini source_name
def write_project_config_file(project_config):
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(project_config['ini'])
    if 'config_out' not in config:
        config.add_section('config_out')
        
    config.set('config_out', 'source_name', project_config['source_name'])
    config.set('config_out', 'install_name', project_config['install_name'])
    config.set('config_out', 'cache_url', project_config['cache_url'])
    # 关键步骤：将配置写入文件
    with open(project_config['ini'], 'w') as configfile:
        config.write(configfile)

# 从http或local url下载文件，并返回实际的保存保存路径
def download_file(url, save_path):
    # 自动补全 file:// 协议（如果传入的是纯本地路径）
    print(f"url:{url}")
    if not urllib.parse.urlparse(url).scheme and os.path.exists(url):
        url = "file://" + os.path.abspath(url).replace("\\", "/")

    """通用下载函数，支持 HTTP 和本地文件，带进度显示"""
    parsed = urllib.parse.urlparse(url)
    
    # 处理 HTTP/HTTPS URL
    if parsed.scheme in ("http", "https"):
        print("正在从网络下载...")
        try:
            with urllib.request.urlopen(url) as response:
                # 尝试从响应头获取文件名
                content_disposition = response.headers.get('Content-Disposition', '')
                filename = None
                
                # 从 Content-Disposition 解析文件名（如：attachment; filename="file.zip"）
                if content_disposition:
                    match = re.search(r'filename=["\']?(.*?)["\']?(?:;|$)', content_disposition)
                    if match:
                        filename = match.group(1)
                if filename:
                    save_dir = os.path.dirname(save_path)
                    save_path = f'{save_dir}/{filename}'
                print(f'real filename = {filename}')
                # 获取文件总大小（字节）
                total_size = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                
                with open(save_path, "wb") as f:
                    while True:
                        chunk = response.read(8192)  # 每次读取 8KB
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # 计算并显示进度
                        if total_size > 0:
                            percent = downloaded / total_size * 100
                            print(f"\r已下载: {downloaded}/{total_size} bytes ({percent:.2f}%)", end="", flush=True)
                        else:
                            print(f"\r已下载: {downloaded} bytes", end="", flush=True)
                    
                    print()  # 换行
                    
        except urllib.error.URLError as e:
            raise RuntimeError(f"下载失败: {e.reason}")
    
    # 处理本地文件路径（file:// 或直接路径）
    elif parsed.scheme == "file" or not parsed.scheme:
        print("正在从本地复制...")
        source_path = parsed.path
        # 处理 Windows 路径（file:///C:/... → C:/...）
        if os.name == "nt" and source_path.startswith("/"):
            source_path = source_path[1:]
        
        try:
            # 获取源文件大小
            file_size = os.path.getsize(source_path)
            print(f"文件大小: {file_size} bytes")
            shutil.copy2(source_path, save_path)
        except OSError as e:
            raise RuntimeError(f"复制文件失败: {e.strerror}")
    
    else:
        raise ValueError(f"不支持的 URL 协议: {url}")

    print(f"文件已保存到: {save_path}")

    return save_path

# 将压缩文件解压到指定目录，并返回根文件（假定输入zip，解压后为单个目录）
def extract_file(archive_path, extract_to):
    """
    自动判断文件类型并解压（支持 ZIP/TAR/GZ/BZ2）
    :param archive_path: 压缩文件路径
    :param extract_to: 解压目标路径
    """
    os.makedirs(extract_to, exist_ok=True)
    root_file = ''
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            root_file = file_list[0]
            print(f'extract_to {extract_to}')
            zip_ref.extractall(extract_to)
        print(f"ZIP 文件已解压到: {extract_to}")
    
    elif tarfile.is_tarfile(archive_path):
        mode = 'r'
        if archive_path.endswith('.gz'):
            mode += ':gz'
        elif archive_path.endswith('.bz2'):
            mode += ':bz2'
        
        with tarfile.open(archive_path, mode) as tar_ref:
            tar_ref.extractall(extract_to)
        print(f"TAR 文件已解压到: {extract_to}")
    
    else:
        raise ValueError("不支持的文件格式（仅支持 ZIP/TAR/GZ/BZ2）")

    return root_file

# 在指定路径查找name开头的文件，返回绝对路径，失败返回空
def find_file_with_name(file_dir, name):
    """
    在指定目录查找以name开头的文件，返回绝对路径列表
    
    :param file_dir: 要搜索的目录路径
    :param name: 要匹配的文件名前缀
    :return: 匹配文件的绝对路径列表，如果没有找到则返回空列表
    """
    if not os.path.isdir(file_dir):
        return ''
    
    for entry in os.listdir(file_dir):
        # 忽略大写
        entry_to_compare = entry.lower()
        # 检查是否以name开头且是文件（不是目录）
        if entry_to_compare.startswith(name) and os.path.isfile(os.path.join(file_dir, entry)):
            # 获取绝对路径并添加到结果列表
            return os.path.abspath(os.path.join(file_dir, entry))
    
    return ''

#
def get_sub_dirs(root_dir):
    """
    获取指定目录下的直接子目录（非递归）
    
    Args:
        root_dir (str): 要搜索的根目录路径
        
    Returns:
        list: 直接子目录的绝对路径列表
        
    Raises:
        ValueError: 如果 root_dir 不是有效目录
    """
    root_path = Path(root_dir).absolute()
    
    # 验证目录是否存在
    if not root_path.is_dir():
        raise ValueError(f"路径不存在或不是目录: {root_dir}")
    
    # 获取所有直接子目录（非递归）
    dirs_list = [
        str(root_path / item.name)  # 转换为绝对路径
        for item in os.scandir(root_dir) 
        if item.is_dir()
    ]
    
    return dirs_list