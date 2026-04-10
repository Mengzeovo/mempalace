// 全局配置：管理所有项目
// 使用方法：pm2 start pm2-all-projects.config.js

module.exports = {
  apps: [
    // MemPalace MCP 服务器
    {
      name: "mempalace-mcp",
      script: ".venv/Scripts/python.exe",
      args: "-m mempalace.mcp_server",
      cwd: "D:/projects/mempalace",  // 修改为你的实际路径
      interpreter: "none",
      autorestart: true,
      env: {
        PYTHONUNBUFFERED: "1"
      },
      error_file: "D:/projects/mempalace/logs/error.log",
      out_file: "D:/projects/mempalace/logs/out.log"
    },

    // 项目 2：Node.js API
    {
      name: "myapp-api",
      script: "server.js",
      cwd: "D:/projects/myapp",
      instances: 2,  // 集群模式，2 个实例
      exec_mode: "cluster",
      env: {
        NODE_ENV: "production",
        PORT: 3000
      }
    },

    // 项目 3：Python Worker
    {
      name: "data-worker",
      script: ".venv/Scripts/python.exe",
      args: "worker.py",
      cwd: "D:/projects/data-processor",
      interpreter: "none",
      cron_restart: "0 2 * * *",  // 每天凌晨 2 点重启
      autorestart: true
    },

    // 项目 4：前端开发服务器（开发环境）
    {
      name: "frontend-dev",
      script: "npm",
      args: "run dev",
      cwd: "D:/projects/frontend",
      watch: ["src"],  // 监听 src 目录变化
      ignore_watch: ["node_modules", "dist"],
      env: {
        NODE_ENV: "development"
      }
    }
  ]
};
