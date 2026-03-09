#!/bin/bash
# 检查是否安装了 Python
if ! command -v python &>/dev/null; then
    echo "错误：未检测到 Python，请先安装 Python。"
    exit 1
fi

# 检查 Python 版本是否为 Python 3
PYTHON_VERSION=$(python -c 'import sys; print(".".join(map(str, sys.version_info[:1])))' 2>/dev/null)
if [ "$PYTHON_VERSION" -lt 3 ]; then
    echo "错误：检测到 Python 版本为 $PYTHON_VERSION，需要 Python 3。"
    exit 1
fi

# 调用 repo.py 脚本
python "$(dirname "$0")/repo.py" "$@"