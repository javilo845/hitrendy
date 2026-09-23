# HiTrendy offline demo

This demo validates the visual language and main product loop without external API keys.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Open http://127.0.0.1:8000

## Tests

```bash
pytest -q
```

## Important

The deterministic provider is not a real language model. It exists so design, contracts, API flow, and acceptance behavior can be implemented before connecting an external model.
