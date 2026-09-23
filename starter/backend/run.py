import os
import sys
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

import asyncio
import selectors
import uvicorn


def selector_event_loop():
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    config = uvicorn.Config(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        loop="asyncio",
    )

    server = uvicorn.Server(config)

    if sys.platform == "win32":
        asyncio.run(
            server.serve(),
            loop_factory=selector_event_loop,
        )
    else:
        asyncio.run(server.serve())
