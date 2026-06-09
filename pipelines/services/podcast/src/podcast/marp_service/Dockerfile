# 使用包含 Python 和 Node.js 的镜像
FROM nikolaik/python-nodejs:python3.11-nodejs20

# 设置工作目录
WORKDIR /app

# 安装 Chromium 依赖（Marp CLI 需要用于 PPTX 导出）
RUN apt-get update && apt-get install -y \
    chromium \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# 安装 Marp CLI
RUN npm install -g @marp-team/marp-cli

# 复制 requirements.txt 并安装 Python 依赖
COPY requirements.txt .
RUN pip install -r requirements.txt

# 复制当前目录下的所有文件到工作目录
COPY . .

# 创建临时目录
RUN mkdir -p /tmp

# 设置 Puppeteer 使用系统 Chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

# 设置容器启动时执行的命令
CMD ["python", "main.py"]