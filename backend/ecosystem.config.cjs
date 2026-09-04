module.exports = {
  apps: [
    {
      name: "ga-backend",
      cwd: __dirname,
      script: "python3",
      args: "-m uvicorn main:app --host 0.0.0.0 --port 8000",
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
    },
  ],
};
