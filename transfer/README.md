# Временная передача: telegram_bot → GitLab

Эта папка — временный транспорт между сессиями Claude Code, к Discord RPC отношения не имеет.
`telegram_bot.bundle` — git-бандл для [ai-agent4370812/telegram_bot](https://gitlab.com/ai-agent4370812/telegram_bot)
поверх `main` (465a028).

| Ветка в бандле | Что это | Пушить |
|----------------|---------|--------|
| `feature/web-chat` | Веб-чат (паритет с ботом), фиксы деплоя и минимальные исправления бота | **да**, + MR в `main` |
| `backup/bot-ops-extended` | Отложенное: CI/деплой/зависимости (D2–D12) | нет, на будущее |
| `backup/bot-data-extended` | Отложенное: импорт (.xls, VARCHAR, >32k строк, колонки) | нет, на будущее |
| `backup/bot-telegram-extended` | Отложенное: Telegram (fallback plain text, черновики, middleware) | нет, на будущее |

Применить и запушить основную ветку:

```bash
git clone https://gitlab.com/ai-agent4370812/telegram_bot.git && cd telegram_bot
git fetch /путь/к/telegram_bot.bundle 'refs/heads/*:refs/remotes/bundle/*'
git push -u origin refs/remotes/bundle/feature/web-chat:refs/heads/feature/web-chat
```

После переноса в GitLab папку `transfer/` и эту ветку можно удалить.
