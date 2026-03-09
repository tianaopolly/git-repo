#!/bin/bash
# filepath: d:\code\gerrit\repo\setup.sh

set -e

TARGET="$HOME/bin"

# 1) 若不存在则创建 $HOME/bin
if [ ! -d "$TARGET" ]; then
    mkdir -p "$TARGET" || {
        echo "无法创建目录 $TARGET"
        exit 1
    }
fi

# 3) 复制 repo 和 repo.cmd 到 $HOME/bin
cp -f "$(dirname "$0")/repo" "$TARGET/"
cp -f "$(dirname "$0")/repo.cmd" "$TARGET/"

# 2) 将 $HOME/bin 添加到当前用户环境变量 PATH（避免重复）
if ! echo "$PATH" | grep -q "$HOME/bin"; then
    echo "export PATH=\$PATH:\$HOME/bin" >> "$HOME/.bashrc"
    export PATH="$PATH:$HOME/bin"
    echo "已将 \$HOME/bin 添加到 PATH（永久生效，需重新打开终端）。"
else
    echo "\$HOME/bin 已存在于 PATH 中。"
fi

echo "完成。"