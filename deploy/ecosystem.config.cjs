module.exports = {
  apps: [
    {
      name: "korvexa-api",
      cwd: "/home/pos/Korvexa",
      script: "/home/pos/Korvexa/backend/.venv/bin/uvicorn",
      args: [
        "app.main:app",
        "--app-dir",
        "backend",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--workers",
        "3",
        "--proxy-headers",
        "--forwarded-allow-ips=127.0.0.1",
      ],
      interpreter: "none",
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 10,
      min_uptime: "10s",
      kill_timeout: 30000,
      max_memory_restart: "512M",
      merge_logs: true,
      time: true,
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
