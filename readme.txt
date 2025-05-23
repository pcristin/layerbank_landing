# LayerBank Deposit - Размещение USDC на LayerBank в сети Scroll

## Настройка

1. Создайте файл `.env` в корневой директории проекта со следующими параметрами:

```
PRIVATE_KEYS={"my_wallet_key":"ВАШ_ПРИВАТНЫЙ_КЛЮЧ"}
PROXIES={"my_proxy":"login:password@host:port"} # Если прокси не используется, оставьте пустые кавычки: ""
```

2. Настройте файл `config/settings.json`:

```json
{
  "proxy": "ENV:my_proxy",       # Ссылка на прокси из .env
  "private_key": "ENV:my_wallet_key", # Ссылка на приватный ключ из .env
  "token": "USDC",               # Токен для депозита (поддерживается только USDC)
  "network": "SCROLL",           # Сеть (поддерживается только SCROLL)
  "amount": 1                    # Количество USDC для размещения (минимум 0.00001)
}
```

## Запуск

1. Установите зависимости:
```
pip install -r requirements.txt
```

2. Запустите скрипт:
```
python main.py
```

## Примечания

- Скрипт автоматически проверит баланс USDC и нативных токенов для оплаты газа
- При необходимости будет выполнен approve USDC перед размещением
- По завершении скрипт покажет ваш баланс lUSDC (токен платформы LayerBank)