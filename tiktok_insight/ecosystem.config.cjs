module.exports = {
  apps: [
    {
      name: "insight-http",
      script: "./pm2_services/run_insight_http.sh",
      interpreter: "/bin/bash",
      autorestart: true,
      restart_delay: 5000,
      out_file: "./logs/pm2-insight-http.out.log",
      error_file: "./logs/pm2-insight-http.err.log",
      time: true
    },
    {
      name: "insight-feishu-bot",
      script: "./pm2_services/run_insight_feishu_bot.sh",
      interpreter: "/bin/bash",
      autorestart: true,
      restart_delay: 5000,
      out_file: "./logs/pm2-insight-feishu-bot.out.log",
      error_file: "./logs/pm2-insight-feishu-bot.err.log",
      time: true
    },
    {
      name: "localekit-http",
      script: "./pm2_services/run_localekit_http.sh",
      interpreter: "/bin/bash",
      autorestart: true,
      restart_delay: 5000,
      out_file: "./logs/pm2-localekit-http.out.log",
      error_file: "./logs/pm2-localekit-http.err.log",
      time: true
    },
    {
      name: "localekit-feishu-bot",
      script: "./pm2_services/run_localekit_feishu_bot.sh",
      interpreter: "/bin/bash",
      autorestart: true,
      restart_delay: 5000,
      out_file: "./logs/pm2-localekit-feishu-bot.out.log",
      error_file: "./logs/pm2-localekit-feishu-bot.err.log",
      time: true
    }
  ]
}
