# Временная передача: telegram_bot → GitLab

Эта папка — временный транспорт между сессиями Claude Code, к Discord RPC отношения не имеет.
`telegram_bot.bundle` — git-бандл ветки `feature/web-chat` репозитория
[ai-agent4370812/telegram_bot](https://gitlab.com/ai-agent4370812/telegram_bot) поверх `main`.

Применить и запушить:

```bash
git clone https://gitlab.com/ai-agent4370812/telegram_bot.git && cd telegram_bot
git fetch /путь/к/telegram_bot.bundle feature/web-chat:feature/web-chat
git push -u origin feature/web-chat
```

После переноса в GitLab папку `transfer/` и эту ветку можно удалить.
