// 生产环境配置
module.exports = {
  apps: [
    {
      name: "mempalace-mcp",
      script: ".venv/Scripts/python.exe",
      args: "-m mempalace.mcp_server",
      cwd: process.cwd(),
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      watch: false,  // 生产模式：不监听文件
      env: {
        PYTHONUNBUFFERED: "1",
        ENV: "production"
      },
      error_file: "./logs/prod-error.log",
      out_file: "./logs/prod-out.log"
    }
  ]
};
