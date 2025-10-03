import os
import subprocess
import sys
import parse_utils


DEFAULT_SOURCE_DIR = 'D:/Program/third_party_src'
DEFAULT_PROJECT_CONFIG_DIR = 'D:/Program/third_party_builder/projects'
DEFAULT_DOWNLOAD_CACHE_DIR = 'D:/Program/third_party_builder/projects/downloads'

DEFAULT_INSTALL_DIR = 'D:/Program/third_party'

DEFAULT_BUILD_DIR_NAME = 'build_auto'
DEFAULT_CMAKE_OPTIONS = []

# 
def create_project_with_name(project_name):
    project_config_path = DEFAULT_PROJECT_CONFIG_DIR + f"/{project_name}.ini"
    print(f"project_config_path:{project_config_path}")
    project_config = parse_utils.parse_project_config_file(project_config_path)

    source_name = project_config.get('source_name')
    source_abs_path = ''
    recreate_project = False
    if not project_config.get('source_name'):
        recreate_project = True
    else:
        source_abs_path = DEFAULT_SOURCE_DIR + "/{}".format(project_config.get('source_name'))
        if not os.path.exists(source_abs_path):
             recreate_project = True

    if recreate_project:
        print('recreate_project')
        download_url = ''
        cache_url = ''
        if not project_config.get('url'):
            raise Exception("缺少 url")
        # 从缓存查找
        cache_url = parse_utils.find_file_with_name(DEFAULT_DOWNLOAD_CACHE_DIR, project_name)
        # 没有缓存，直接下载
        if not cache_url:
            cache_url = f'{DEFAULT_DOWNLOAD_CACHE_DIR}/{project_name}'# 获取配置的下载url
            download_url = project_config.get('url')# 获取下载url
            os.makedirs(DEFAULT_DOWNLOAD_CACHE_DIR, exist_ok=True)
            cache_url = parse_utils.download_file(download_url, cache_url)# 下载
            print(f'cache_url to {cache_url}')

        if cache_url.endswith('.exe'):
            print(f'{project_name} is exe, skip extract')
            source_name = project_name
        else:
            # 解压
            source_name = parse_utils.extract_file(cache_url, DEFAULT_SOURCE_DIR)
            
        # 更新配置
        project_config['source_name'] = source_name
        project_config['cache_url'] = cache_url
        parse_utils.write_project_config_file(project_config)
    else:
        print('no recreate_project')
   
    return project_config

#
def build_project(project_config):
    
    project_name = project_config.get('name')
    # 生成build路径
    build_path = '{}/{}/{}'.format(DEFAULT_SOURCE_DIR, project_config.get('source_name'), DEFAULT_BUILD_DIR_NAME)
    if project_config.get('build_dir_name'):
        build_path = '{}/{}/{}'.format(DEFAULT_SOURCE_DIR, project_config.get('source_name'), project_config.get('build_dir_name'))
    print(f'build_path:{build_path}')
    # 生成cmake file相对build的路径
    cmake_file_path = '..'
    if project_config.get('source_cmake_file_dir'):
        cmake_file_path = '{}/{}/{}'.format(DEFAULT_SOURCE_DIR, project_config.get('source_name'), project_config.get('source_cmake_file_dir'))
    
    if not os.path.exists(build_path):
        print(f'mk build dir: {build_path}')
        os.makedirs(build_path, exist_ok=True)
    rep_paths = parse_utils.get_sub_dirs(DEFAULT_INSTALL_DIR)
    rep_paths.append(DEFAULT_INSTALL_DIR)
    if project_config.get('prefix_path'):
        rep_paths.append(project_config.get('prefix_path'))
        
    install_path = '{}/{}'.format(DEFAULT_INSTALL_DIR, project_config.get('install_name'))
    print(f'install_path:{install_path}')
    if not os.path.exists(install_path):
        print(f'mk install dir: {install_path}')
        os.makedirs(install_path, exist_ok=True)
    
    print(f'rep_paths: {rep_paths}')

    cmake_options = [
            "cmake", 
            cmake_file_path, 
            "-G", "Visual Studio 16 2019", 
            "-A x64", 
            "-T v142", 
            "-DCMAKE_BUILD_TYPE=Release", 
            "-DCMAKE_PREFIX_PATH=" + ";".join(rep_paths), 
            "-DCMAKE_INSTALL_PREFIX=" + install_path , 
    ]
    build_options = [
        "cmake", 
        "--build", 
        ".",
        "--config", "Release",
        "--", "/p:Platform=x64",
        "/m:12",
 
    ]
    install_options = [
        "cmake", 
        "--install", 
        ".",
        "--config", "Release"
    ]

    if project_config.get('options'):
        for key, value in project_config.get('options').items():
            cmake_options.append(f"-D{key}={value}")
    print(f'options={cmake_options}')

    code = 0
    if project_config.get('cmd_build'):
        bat_path = '{}/{}'.format(os.path.dirname(project_config.get('ini')), project_config.get('cmd_build'))
        print(f'use bat {bat_path}')
        print('cache_url:{}', project_config.get('cache_url'))
        env_vars = {
            'INSTALL_PATH': install_path,
            'CACHE_URL': project_config.get('cache_url'),
            'BUILD_PATH': build_path,
            **os.environ  # 保留现有环境变量
        }
        code = subprocess.call(f'{bat_path}', cwd=build_path, env=env_vars)
        if code != 0:
            raise Exception("[{}] cmd build失败，code：{}".format(project_name, code))
        return
        
    # cmake
    code = subprocess.call(cmake_options, cwd=build_path)
    if code != 0:
        raise Exception("[{}] cmake失败，code：{}".format(project_name, code))
    # build
    code = subprocess.call(build_options, cwd=build_path)
    if code != 0:
        raise Exception("[{}] build失败，code：{}".format(project_name, code))
    # install
    code = subprocess.call(install_options, cwd=build_path)
    if code != 0:
        raise Exception("[{}] install失败，code：{}".format(project_name, code))