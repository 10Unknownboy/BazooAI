import asyncio
import uvicorn
from fastapi import FastAPI
app = FastAPI()
config = uvicorn.Config(app, host='127.0.0.1', port=8009)
server = uvicorn.Server(config)
async def main():
    try:
        await asyncio.wait_for(server.serve(), timeout=2.0)
    except asyncio.TimeoutError:
        pass
asyncio.run(main())
