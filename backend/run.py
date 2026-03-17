"""启动 Web 服务: cd backend && uv run python run.py"""
import sys
import uvicorn
from config import HOST, PORT

reload = "--reload" in sys.argv
uvicorn.run("app:app", host=HOST, port=PORT, reload=reload)
