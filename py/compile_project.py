import sys
import compile_utils

def main():
    # 获取所有命令行参数（列表形式）
    args = sys.argv
    
    # 第一个元素是脚本名称，后续是传入的参数
    print("脚本名称:", args[0])
    print("所有参数:", args[1:])
    
    # 示例：检查是否有足够的参数
    if len(args) < 2:
        print("请提供至少一个参数")
        sys.exit(1)
    
    # 使用参数
    for arg in sys.argv[1:]:  # 从第1个参数开始遍历
        project_config = compile_utils.create_project_with_name(arg)
        compile_utils.build_project(project_config)

if __name__ == "__main__":
    main()