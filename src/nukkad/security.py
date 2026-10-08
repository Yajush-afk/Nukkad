import secrets

from fastapi.responses import JSONResponse


def install_security(app):
    token = secrets.token_urlsafe(32)
    app.state.csrf_token = token

    @app.middleware("http")
    async def protect(request, call_next):
        if request.url.hostname not in {"127.0.0.1", "localhost", "::1"}:
            return JSONResponse({"detail": "Only localhost hosts are accepted"}, status_code=400)
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.headers.get('host')}"
        if origin and origin != expected or request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-origin access is disabled"}, status_code=403)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not secrets.compare_digest(
            request.headers.get("x-nukkad-token", ""), token
        ):
            return JSONResponse(
                {"detail": "Reload Nukkad before saving; local session token required"},
                status_code=403,
            )
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/session")
    def session():
        return {"token": token}
