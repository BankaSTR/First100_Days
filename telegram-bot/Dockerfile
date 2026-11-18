FROM python:3.13-slim
WORKDIR /app
COPY config.py main.py service.py store.py telegram.py ./
COPY seed_data.py catalogue.json ./
RUN useradd --create-home bot && mkdir /data && chown bot:bot /data
USER bot
ENV PYTHONUNBUFFERED=1 BOT_DATABASE=/data/bot.sqlite3
CMD ["python", "main.py"]
