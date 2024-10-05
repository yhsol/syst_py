# syst_py

start: pipenv run start

```
syst_py
├─ .gitignore
├─ .pylintrc
├─ Pipfile
├─ README.md
└─ app
   ├─ api
   │  ├─ coin_analysis.py
   │  ├─ signal.py
   │  ├─ trade-by-socket.py
   │  └─ trade.py
   ├─ dependencies
   │  ├─ __init__.py
   │  └─ auth.py
   ├─ lib
   │  └─ bithumb_auth_header
   │     ├─ __pycache__
   │     │  ├─ xcoin_api_client1.cpython-311.pyc
   │     │  └─ xcoin_api_client1.cpython-38.pyc
   │     ├─ api_test.py
   │     └─ xcoin_api_client.py
   ├─ main.py
   ├─ models
   │  └─ __init__.py
   ├─ services
   │  ├─ backtest.py
   │  ├─ bithumb_service.py
   │  ├─ market_monitor.py
   │  ├─ stratege_service.py
   │  ├─ trading-by-socket.py
   │  └─ trading.py
   ├─ telegram
   │  └─ telegram_client.py
   └─ utils
      └─ trading_helpers.py
```