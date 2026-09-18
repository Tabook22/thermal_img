from fastapi import Request
from fastapi.responses import JSONResponse

async def unhandled_error(_: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error":{"code":"internal_error","message":"Unexpected server error"}})

