# MemPalace 虚拟环境激活脚本（PowerShell）

# 允许脚本执行
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force

# 激活虚拟环境
& .\.venv\Scripts\Activate.ps1

Write-Host "✅ MemPalace virtual environment activated!" -ForegroundColor Green
Write-Host ""
Write-Host "To run MCP server:" -ForegroundColor Cyan
Write-Host "  python -m mempalace.mcp_server"
Write-Host ""
Write-Host "To deactivate:" -ForegroundColor Cyan
Write-Host "  deactivate"
