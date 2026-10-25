# Деплой renews.me

Сервер общий с галереей (`image-gallery`, `/srv/artai`): BuyVM, 1 vCPU, 4 ГБ RAM, `ssh deploy@198.98.52.9`.
Порты 80/443 занимает Caddy галереи — он же обслуживает renews.me, импортируя `deploy/caddy/renews.caddy`.

## Схема

```
git push в main
  └─ GitHub Actions (.github/workflows/ci.yml): commitlint + тесты на PostgreSQL
       только push: semantic release (тег vX.Y.Z) → образ ghcr.io/sni10/agregator-backend:<sha>

Сервер:
  /srv/artai   галерея; её caddy (:80/:443) импортирует /etc/caddy/sites/*.caddy  ← /srv/renews/caddy (ro)
               и читает том renews_media (/srv/renews-media, ro)
  /srv/renews  compose.prod.yaml: db, app (gunicorn, 2 воркера), front (SSR, когда есть FRONT_TAG)
               app и front — в общей сети edge под именами renews-app / renews-front

renews.me         → front; /sitemap.xml, /news-sitemap.xml, /rss.xml → app; /robots.txt — Caddy
www.renews.me     → 301 на renews.me
api.renews.me     → read API, publishing API (пайплайн, X-Api-Key), /media; /admin → 404
secure.renews.me  → админка (очередь review); роботам 403 и noindex
```

## DNS (Cloudflare)

| Type | Name | Content | Proxy |
|---|---|---|---|
| A | `@` | `198.98.52.9` | DNS only (прокси — позже, как в галерее) |
| CNAME | `www` | `renews.me` | DNS only |
| A | `api` | `198.98.52.9` | DNS only |
| A | `secure` | `198.98.52.9` | DNS only (всегда) |

## Первый запуск (один раз)

1. На сервере: `docker network create edge`, `docker volume create renews_media`, `mkdir -p /srv/renews/caddy`,
   `/srv/renews/.env` из `.env.production.example` (секреты сгенерировать там же, `chmod 600`).
2. Галерея (`/srv/artai`): в `Caddyfile` в конец — `import /etc/caddy/sites/*.caddy`; в `compose.prod.yaml` у `caddy` —
   тома `/srv/renews/caddy:/etc/caddy/sites:ro`, `renews_media:/srv/renews-media:ro`, сеть `edge`
   (внешние: `renews_media`, `edge`). `docker compose -f compose.prod.yaml up -d caddy` — пересоздаёт только Caddy.
3. `bash deploy/deploy.sh <sha>` с домашнего ПК.
4. Администратор: `ssh deploy@198.98.52.9`, `cd /srv/renews && docker compose -f compose.prod.yaml exec app python manage.py createsuperuser`.
5. Пайплайн (`agregator/.env`): `PUBLISHING_URL=https://api.renews.me`, `PUBLISHING_API_KEY` = ключ из `/srv/renews/.env`.

## Деплой, откат

```bash
bash deploy/deploy.sh <полный sha бэкенда>   # compose + renews.caddy на сервер, pull, up, reload Caddy галереи
bash deploy/deploy.sh <sha фронта>           # из agregator-front: FRONT_TAG в .env, перезапуск только front
```

Откат — та же команда с прошлым SHA. Миграции сами не откатываются (см. DEPLOY.md галереи).

На сервере (`cd /srv/renews`):
```bash
docker compose -f compose.prod.yaml --profile front ps
docker compose -f compose.prod.yaml logs -f app
docker compose -f /srv/artai/compose.prod.yaml logs caddy    # сертификаты renews.me, ошибки прокси
```

⚠ `deploy.sh` галереи копирует её `compose.prod.yaml` и `Caddyfile` из репозитория: изменения шага 2 (и beszel) должны
быть и в репозитории `image-gallery`, иначе следующий деплой галереи отключит renews.me.

## После запуска

- [ ] Google Search Console и Bing Webmaster: подтвердить `renews.me` (TXT в Cloudflare), отправить `https://renews.me/sitemap.xml` и `https://renews.me/news-sitemap.xml`
- [ ] Google News: Publisher Center — после пары недель регулярных публикаций; нужны страницы About и контакты
- [ ] HSTS: неделя → год (сниппет `renews_hsts` в `renews.caddy`), как в галерее
- [ ] Прокси Cloudflare для `renews.me`, `www`, `api` (SSL Full (strict)); `secure` — всегда DNS only
- [ ] Бэкап: `pg_dump` + том `renews_media` (по образцу `image-gallery/deploy/backup.sh`)
