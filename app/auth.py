"""
Company login: one shared password for the company's engineers.

  * Off until APP_PASSWORD is set (Railway → Variables). Changing it signs everyone out.
  * The password never leaves the server; the browser gets a signed, HttpOnly cookie for 30 days.
  * Every page and API needs the cookie, except the login page, its stylesheet/logo and /health.
  * After 8 wrong passwords from one address in 15 minutes, that address waits until the window passes.
"""
import hashlib
import hmac
import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

COOKIE = "tmd_session"
MAX_AGE = 30 * 24 * 3600
OPEN_PATHS = ("/login", "/logout", "/health", "/static/css/", "/static/img/")
_FAILS: Dict[str, Deque[float]] = defaultdict(deque)
_WINDOW, _MAX_FAILS = 15 * 60, 8

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _password() -> str:
    return os.environ.get("APP_PASSWORD", "")


def enabled() -> bool:
    return bool(_password())


def _key() -> bytes:
    # A new password gives a new key, so changing APP_PASSWORD signs everyone out
    secret = os.environ.get("APP_SESSION_SECRET", "")
    return hashlib.sha256(f"tmd-session|{secret}|{_password()}".encode()).digest()


def _sign(expires: int) -> str:
    sig = hmac.new(_key(), f"v1:{expires}".encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def valid(token: str) -> bool:
    try:
        expires_s, sig = token.split(".", 1)
        expires = int(expires_s)
    except (AttributeError, ValueError):
        return False
    return expires > time.time() and hmac.compare_digest(sig, _sign(expires).split(".", 1)[1])


def _client(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


def _locked(ip: str) -> bool:
    q = _FAILS[ip]
    while q and q[0] < time.time() - _WINDOW:
        q.popleft()
    return len(q) >= _MAX_FAILS


async def middleware(request: Request, call_next):
    path = request.url.path
    if not enabled() or path.startswith(OPEN_PATHS) or valid(request.cookies.get(COOKIE, "")):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Please sign in again."}, status_code=401)
    return RedirectResponse("/login", status_code=303)


@router.get("/login")
def login_page(request: Request):
    if not enabled() or valid(request.cookies.get(COOKIE, "")):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": ""})


@router.post("/login")
async def login(request: Request):
    # plain form post read directly (no extra form-parsing package needed)
    body = (await request.body())[:4096].decode("utf-8", "replace")
    password = parse_qs(body).get("password", [""])[0]
    if not enabled():
        return RedirectResponse("/", status_code=303)
    ip = _client(request)
    if _locked(ip):
        return templates.TemplateResponse(request=request, name="login.html", status_code=429,
                                          context={"error": "Too many wrong attempts. Please wait 15 minutes."})
    if not hmac.compare_digest(password.encode(), _password().encode()):
        _FAILS[ip].append(time.time())
        return templates.TemplateResponse(request=request, name="login.html", status_code=401,
                                          context={"error": "Wrong password."})
    _FAILS.pop(ip, None)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(COOKIE, _sign(int(time.time()) + MAX_AGE), max_age=MAX_AGE, httponly=True,
                    secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
                    samesite="lax", path="/")
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login" if enabled() else "/", status_code=303)
    resp.delete_cookie(COOKIE, path="/")
    return resp
