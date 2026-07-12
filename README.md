# BoostX

### Run app

``` bash
cp .env.example .env   # или свои значения
python -m venv .venv && .venv/bin/pip install -e .
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
# либо: docker compose up
```

### Run sever

``` bash
python -m venv .venv && .venv/bin/pip install -e .
export BOOSTX_API_URL=http://localhost:8000/api/v1
.venv/bin/python -m boostx
```


*** If u want open server panel

``` bash
http://localhost:8000/docs
```
