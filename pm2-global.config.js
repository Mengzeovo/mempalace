// 全局 PM2 配置 - 管理所有项目
// 保存到：C:\Users\YourUsername\pm2-global.config.js

module.exports = {
  apps: [
    // MemPalace MCP 服务器
    {
      name: "mempalace-mcp",
      script: ".venv/Scripts/python.exe",
      args: "-m mempalace.mcp_server",
      cwd: "D:/projects/mempalace",  // 修改为你的实际路径
      interpreter: "none",
      watch: false,
      autorestart: true,
      max_restarts: 10,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8"
      },
      error_file: "D:/projects/mempalace/logs/error.log",
      out_file: "D:/projects/mempalace/logs/out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss"
    },

    // 其他项目示例
    // {
    //   name: "project2-api",
    //   script: "server.js",
    //   cwd: "D:/projects/project2",
    //   env: {
    //     NODE_ENV: "production",
    //     PORT: 3000
    //   }
    // },

    // {
    //   name: "project3-worker",
    //   script: ".venv/Scripts/python.exe",
    //   args: "worker.py",
    //   cwd: "D:/projects/project3",
    //   interpreter: "none"
    // }
  ]
};
