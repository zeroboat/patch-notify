"""
FastAPI — Slack 외부 공개 엔드포인트
  GET  /slack/install/          → Slack OAuth 시작
  GET  /slack/oauth/callback/   → 토큰 교환 + workspace 저장
  POST /slack/events/           → Slack 이벤트 수신 (bolt)
"""
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', 'dev.env'))

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from slack_bolt.adapter.fastapi import SlackRequestHandler
from sqlalchemy import select

from bolt_app import bolt_app
from database import SessionLocal
from models import slack_workspace

app = FastAPI(title="Patch Notify — Slack API", redirect_slashes=False)
handler = SlackRequestHandler(bolt_app)


@app.get("/slack/install/")
def slack_install(team: str = None):
    """Slack OAuth 설치 시작 — Slack 인증 화면으로 리다이렉트"""
    scopes = "chat:write,channels:read"
    url = (
        "https://slack.com/oauth/v2/authorize"
        f"?client_id={os.environ['SLACK_CLIENT_ID']}"
        f"&scope={scopes}"
        f"&redirect_uri={os.environ['SLACK_REDIRECT_URI']}"
    )
    if team:
        url += f"&team={team}"
    return RedirectResponse(url)


@app.get("/slack/oauth/callback/")
async def slack_oauth_callback(request: Request):
    """Slack OAuth 콜백 — 토큰 교환 후 SlackWorkspace 저장"""
    params = dict(request.query_params)

    if error := params.get('error'):
        return PlainTextResponse(f"Slack 설치 오류: {error}", status_code=400)

    code = params.get('code')
    if not code:
        return PlainTextResponse("인증 코드가 없습니다.", status_code=400)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            'https://slack.com/api/oauth.v2.access',
            data={
                'client_id': os.environ['SLACK_CLIENT_ID'],
                'client_secret': os.environ['SLACK_CLIENT_SECRET'],
                'code': code,
                'redirect_uri': os.environ['SLACK_REDIRECT_URI'],
            },
            timeout=10,
        )
    data = resp.json()

    if not data.get('ok'):
        return PlainTextResponse(f"인증 실패: {data.get('error', 'unknown')}", status_code=400)

    team_id = data['team']['id']
    team_name = data['team']['name']
    bot_token = data['access_token']

    db = SessionLocal()
    try:
        existing = db.execute(
            select(slack_workspace).where(slack_workspace.c.team_id == team_id)
        ).fetchone()
        if existing:
            db.execute(
                slack_workspace.update()
                .where(slack_workspace.c.team_id == team_id)
                .values(team_name=team_name, bot_token=bot_token, updated_at=datetime.now(timezone.utc))
            )
        else:
            now = datetime.now(timezone.utc)
            db.execute(slack_workspace.insert().values(
                team_id=team_id, team_name=team_name, bot_token=bot_token, status='pending',
                created_at=now, updated_at=now,
            ))
        db.commit()
    finally:
        db.close()

    if existing:
        msg = f"✅ '{team_name}' 워크스페이스 토큰이 갱신되었습니다."
    else:
        msg = (
            f"✅ '{team_name}' 워크스페이스 설치가 완료되었습니다.\n"
            "관리자 승인 후 Slack 앱을 이용할 수 있습니다."
        )

    return PlainTextResponse(msg)


@app.post("/slack/events/")
async def slack_events(request: Request):
    """Slack 이벤트 수신 (slack_bolt 서명 검증 포함)"""
    print(request.headers)  # 디버깅용 로그
    # print("Received request at /slack/events/") // 디버깅용 로그
    return await handler.handle(request)
