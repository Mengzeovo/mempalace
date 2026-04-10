#!/bin/bash
# PM2 配置切换脚本 (Mac/Linux 版本)

if [ -z "$1" ]; then
    echo "Usage: ./pm2-switch.sh [dev|prod|minimal]"
    exit 1
fi

ENVIRONMENT=$1

case $ENVIRONMENT in
    dev)
        CONFIG_FILE="pm2-dev.config.js"
        ;;
    prod)
        CONFIG_FILE="pm2-prod.config.js"
        ;;
    minimal)
        CONFIG_FILE="pm2-minimal.config.js"
        ;;
    *)
        echo "❌ Invalid environment: $ENVIRONMENT"
        echo "Valid options: dev, prod, minimal"
        exit 1
        ;;
esac

echo "🔄 Switching to $ENVIRONMENT environment..."

# 停止所有进程
echo "⏸️  Stopping all processes..."
pm2 stop all

# 删除所有进程
echo "🗑️  Removing all processes..."
pm2 delete all

# 启动新配置
echo "🚀 Starting $CONFIG_FILE..."
pm2 start $CONFIG_FILE

# 保存
echo "💾 Saving configuration..."
pm2 save

# 显示状态
echo ""
echo "✅ Switched to $ENVIRONMENT environment!"
pm2 list
