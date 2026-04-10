#!/bin/bash
# MemPalace 开发环境设置脚本

set -e

echo "🏰 Setting up MemPalace development environment..."

# 检查是否安装了 uv
if ! command -v uv &> /dev/null; then
    echo "❌ uv not found. Installing uv..."
    pip install uv
fi

# 创建虚拟环境
echo "📦 Creating virtual environment..."
uv venv

# 激活虚拟环境
echo "🔌 Activating virtual environment..."
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source .venv/Scripts/activate
else
    source .venv/bin/activate
fi

# 使用 uv.lock 同步依赖
echo "⬇️  Syncing dependencies from uv.lock..."
uv sync

# 验证安装
echo "✅ Verifying installation..."
python -c "import mempalace; print(f'MemPalace version: {mempalace.__version__}')"

echo ""
echo "🎉 Setup complete!"
echo ""
echo "To activate the environment in the future, run:"
echo "  source .venv/Scripts/activate"
echo ""
echo "To start the MCP server:"
echo "  python -m mempalace.mcp_server"
