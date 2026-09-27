<!--
  README профиля github.com/dzotyara.
  Всё в assets/generated/ каждый день перерисовывает .github/workflows/refresh.yml
  (scripts/build_profile.py + Platane/snk). Чтобы поменять карточки, правь data/*, а не SVG.
-->

привет <img src="assets/wave.svg" width="34" alt="👋"> я Никита
=================================================================

<div align="center">

<img src="assets/typing.svg" alt="Python-разработчик · укротитель ботов · делаю ботов, которые всё помнят">

<img src="assets/generated/neofetch.svg" alt="Карточка в стиле neofetch: живая статистика GitHub и загрузка CPU, RAM и swap раннера, который её нарисовал">

</div>

- 🤖 Сейчас делаю **[Ботяру](https://github.com/dzotyara/backseat)** — участника групповых чатов в Telegram и Discord, который помнит всю беседу и припоминает её к месту

- 💬 Спрашивай меня про **ботов для Telegram и Discord, LLM-инструменты, бэкенды на FastAPI, Discord Rich Presence и то, как сделать логи читаемыми**

- 🖥️ Фан-факт: я научил свой статус в Discord показывать [CPU, RAM и swap](https://github.com/dzotyara/discord_rpc_with_system_monitoring). Карточка выше делает то же самое для раннера GitHub, который её нарисовал

- 🎮 Rich Presence для игр — тоже моё хобби: вот [форк War Thunder RPC](https://github.com/dzotyara/WarThunderDiscordRPC_Fork)

- 📫 Как со мной связаться: открой issue в любом моём репозитории
<!-- Добавь сюда контакты, например:
  [Telegram](https://t.me/<username>), [Discord](https://discord.com/users/<user_id>), [LinkedIn](https://linkedin.com/in/<username>)
-->

# Что я сделал

| | Проект | Что делает | Стек |
|---|---|---|---|
| 🤖 | **[backseat](https://github.com/dzotyara/backseat)** | Ботяра: бот-участник групповых чатов в Telegram и Discord с долгой памятью, итогами недели и веб-панелью. 233 теста | aiogram · discord.py · OpenRouter · SQLite · Docker |
| 🧠 | **[Quizzard](https://github.com/dzotyara/Quizzard)** | Telegram-бот для викторин на любую тему: три уровня сложности, вопросы от LLM в реальном времени, мультиплеер | aiogram · SQLAlchemy · Alembic · Docker |
| 📜 | **[WebLoggy](https://github.com/dzotyara/WebLoggy)** | Превращает логи Python-приложения в живой веб-интерфейс: страницы, трейсы, поиск, уведомления в Telegram и Discord | Python · HTML · CSS · JS |
| ✅ | **[approval-service](https://github.com/dzotyara/approval-service)** | API для одобрения, отклонения и отмены публикаций: идемпотентность, аудит-лог, outbox и изоляция воркспейсов | FastAPI · SQLAlchemy · Alembic · PostgreSQL |
| 🖥️ | **[discord_rpc_with_system_monitoring](https://github.com/dzotyara/discord_rpc_with_system_monitoring)** | Загрузка CPU, RAM и swap прямо в статусе Discord | pypresence · psutil |
| 🎨 | **[qwen-discord-bot](https://github.com/dzotyara/qwen-discord-bot)** | `/imagine` для Discord: генерирует картинки через Qwen | discord.py · DashScope |

# Любимые инструменты

[![Мои инструменты](https://skillicons.dev/icons?i=py,fastapi,sqlite,postgres,docker,linux,bash,git,github,githubactions,discord,html,css,js,md&perline=15)](https://skillicons.dev)

# Мой settings.json

```jsonc
// тот же формат, что у моего Discord RPC-монитора
{
    "client_id": "dzotyara",
    "name": "Никита",
    "update_interval": 5,
    "monitoring_1": "bots_online",     // Ботяра, Quizzard, /imagine
    "monitoring_2": "tests_passed",    // 233 только в backseat
    "monitoring_3": "coffee_percent",
    "monitoring_4": "swap_percent",    // своп мозга, в основном регулярками
    "stack": ["Python", "aiogram", "discord.py", "FastAPI", "SQLAlchemy", "Docker"],
    "favorites": {
        "language": "Python",
        "database": "SQLite, пока хватает",
        "license": "MIT",
        "game": "War Thunder",
        "emoji": "🤖"
    }
}
```

<div align="center">

<h3>Комментарий дня от Ботяры</h3>

<img src="assets/generated/botyara-says.svg" alt="Ботяра, бот из backseat, каждый день пишет новую ехидную реплику">

<h3>Мои контрибуции на обед змейке</h3>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/generated/snake-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/generated/snake-light.svg">
  <img alt="Змейка ест мой граф контрибуций" src="assets/generated/snake-light.svg">
</picture>

<sub>Карточки на этой странице каждый день перерисовывают <a href=".github/workflows/refresh.yml">GitHub Action</a> и <a href="scripts/build_profile.py">небольшой Python-скрипт</a>.</sub>

</div>
