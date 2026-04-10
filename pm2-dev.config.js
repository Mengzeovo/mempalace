// 开发环境配置
module.exports = {
  apps: [
    {
      name: "mempalace-mcp",
      script: ".venv/Scripts/python.exe",
      args: "-m mempalace.mcp_server",
      cwd: process.cwd(),
      interpreter: "none",
      autorestart: true,
      watch: ["mempalace"],  // 开发模式：监听文件变化
      ignore_watch: ["logs", ".venv", "__pycache__"],
      env: {
        PYTHONUNBUFFERED: "1",
        ENV: "development"
      }
    }
  ]
};
