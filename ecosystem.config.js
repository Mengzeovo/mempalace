// 所有服务的统一配置文件
module.exports = {
  apps: [
    // MemPalace MCP 服务器
    {
      name: "mempalace-mcp",
      script: process.platform === "win32" ? ".venv/Scripts/pythonw.exe" : ".venv/bin/python",
      args: "-m mempalace.mcp_server --port 8001",
      cwd: process.cwd(),
      interpreter: "none",
      watch: false,
      autorestart: true,
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 4000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8"
      },
      error_file: "./logs/mempalace-error.log",
      out_file: "./logs/mempalace-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true
    }

    // 添加更多服务示例：
    // {
    //   name: "project2-api",
    //   script: "server.js",
    //   cwd: "D:/projects/project2",
    //   env: {
    //     NODE_ENV: "production",
    //     PORT: 3000
    //   }
    // },
    // 
    // {
    //   name: "project3-worker",
    //   script: ".venv/Scripts/python.exe",
    //   args: "worker.py",
    //   cwd: "D:/projects/project3",
    //   interpreter: "none"
    // }
  ]
};
