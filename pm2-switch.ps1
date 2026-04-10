# PM2 配置切换脚本
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("dev", "prod", "minimal")]
    [string]$Environment
)

$configFiles = @{
    "dev" = "pm2-dev.config.js"
    "prod" = "pm2-prod.config.js"
    "minimal" = "pm2-minimal.config.js"
}

$configFile = $configFiles[$Environment]

Write-Host "🔄 Switching to $Environment environment..." -ForegroundColor Cyan

# 停止所有进程
Write-Host "⏸️  Stopping all processes..." -ForegroundColor Yellow
pm2 stop all

# 删除所有进程
Write-Host "🗑️  Removing all processes..." -ForegroundColor Yellow
pm2 delete all

# 启动新配置
Write-Host "🚀 Starting $configFile..." -ForegroundColor Green
pm2 start $configFile

# 保存
Write-Host "💾 Saving configuration..." -ForegroundColor Green
pm2 save

# 显示状态
Write-Host ""
Write-Host "✅ Switched to $Environment environment!" -ForegroundColor Green
pm2 list
