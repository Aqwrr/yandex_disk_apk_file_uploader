# Выгрузка APK на Яндекс Диск (версия для GitHub)

## Что делает скрипт

1. Ищет последний (самый свежий по времени изменения) APK в указанной папке.
2. Загружает APK на Яндекс Диск через API.
3. Публикует файл как доступный по ссылке.
4. Возвращает:
   - `public_url` (постоянная публичная страница файла),
   - `direct_download_url` (прямая ссылка на скачивание, обычно временная),
   - `remote_path`, `upload_status` и путь к выбранному локальному файлу.

## Как создать OAuth-приложение в Яндексе

1. Откройте страницу:
   [https://oauth.yandex.ru/client/new/](https://oauth.yandex.ru/client/new/)
2. Создайте приложение.
3. Добавьте права:
   - `cloud_api:disk.read`
   - `cloud_api:disk.write`
4. Скопируйте `ClientID`.
5. Откройте ссылку:
   `https://oauth.yandex.ru/authorize?response_type=token&client_id=ВАШ_CLIENT_ID`
6. После редиректа возьмите `access_token` из URL.

## Куда подставлять данные

Рекомендуется через переменные окружения (PowerShell):

```powershell
$env:YANDEX_OAUTH_TOKEN="ВАШ_OAUTH_ТОКЕН"
$env:APK_DIR="~\app\build\app\outputs\flutter-apk"
$env:DISK_UPLOAD_DIR="disk:/apk_builds"
$env:OVERWRITE_IF_EXISTS="true"
$env:APK_GLOB_PATTERN="*.apk"
$env:APK_SEARCH_RECURSIVE="false"
```

Опционально можно вписать значения прямо в константы в файле скрипта.

## Поиск последнего APK

Используется функция `find_latest_apk`:

1. Берет файлы по шаблону `APK_GLOB_PATTERN` (по умолчанию `*.apk`).
2. Если `APK_SEARCH_RECURSIVE=true`, ищет рекурсивно по подпапкам.
3. Выбирает файл с максимальным `mtime` (самый свежий).

## Запуск

Из корня проекта:

```powershell
python scripts/upload_apk_to_yadisk_github.py
```

## Важно по безопасности

1. Не коммитьте реальный OAuth-токен.
2. Храните токен в переменных окружения или CI/CD Secrets.
3. При утечке токена сразу перевыпустите его.

