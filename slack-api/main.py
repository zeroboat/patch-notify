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
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from slack_bolt.adapter.fastapi import SlackRequestHandler
from sqlalchemy import select

from bolt_app import bolt_app
from database import SessionLocal
from models import slack_workspace

app = FastAPI(title="Patch Notify — Slack API", redirect_slashes=False)
handler = SlackRequestHandler(bolt_app)


_INSTALL_PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Slack 앱 설치 — Patch Notify</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f4f5f7; display: flex; align-items: center;
            justify-content: center; min-height: 100vh; padding: 20px; }}
    .card {{ background: #fff; border-radius: 12px; padding: 40px 36px;
             max-width: 440px; width: 100%; box-shadow: 0 4px 20px rgba(0,0,0,.08); }}
    .logo {{ display: flex; align-items: center; gap: 10px; margin-bottom: 28px; }}
    .logo svg {{ width: 32px; height: 32px; }}
    .logo span {{ font-size: 1.2rem; font-weight: 700; color: #1a1a2e; }}
    h1 {{ font-size: 1.1rem; font-weight: 600; color: #1a1a2e; margin-bottom: 8px; }}
    p {{ font-size: 0.875rem; color: #6b7280; margin-bottom: 24px; line-height: 1.6; }}
    label {{ display: block; font-size: 0.8rem; font-weight: 600;
             color: #374151; margin-bottom: 6px; }}
    .input-wrap {{ display: flex; align-items: center; border: 1.5px solid #d1d5db;
                   border-radius: 8px; overflow: hidden; background: #fff;
                   transition: border-color .15s; }}
    .input-wrap:focus-within {{ border-color: #4a154b; }}
    .prefix {{ padding: 0 10px; color: #9ca3af; font-size: 0.875rem;
               border-right: 1.5px solid #d1d5db; background: #f9fafb;
               height: 44px; display: flex; align-items: center; white-space: nowrap; }}
    input {{ border: none; outline: none; padding: 0 12px; height: 44px;
             font-size: 0.875rem; flex: 1; min-width: 0; }}
    .suffix {{ padding: 0 10px; color: #9ca3af; font-size: 0.875rem;
               border-left: 1.5px solid #d1d5db; background: #f9fafb;
               height: 44px; display: flex; align-items: center; white-space: nowrap; }}
    .hint {{ font-size: 0.75rem; color: #9ca3af; margin-top: 6px; }}
    .btn {{ display: block; width: 100%; margin-top: 24px; padding: 12px;
            background: #4a154b; color: #fff; border: none; border-radius: 8px;
            font-size: 0.9rem; font-weight: 600; cursor: pointer;
            transition: background .15s; }}
    .btn:hover {{ background: #611f69; }}
    .divider {{ display: flex; align-items: center; gap: 12px;
                margin: 20px 0; color: #d1d5db; font-size: 0.75rem; }}
    .divider::before, .divider::after {{ content: ''; flex: 1; border-top: 1px solid #e5e7eb; }}
    .btn-direct {{ display: block; width: 100%; padding: 11px; background: #fff;
                   color: #4a154b; border: 1.5px solid #4a154b; border-radius: 8px;
                   font-size: 0.85rem; font-weight: 600; cursor: pointer;
                   transition: background .15s; text-align: center; text-decoration: none; }}
    .btn-direct:hover {{ background: #f9f0fa; }}
  </style>
</head>
<body>
<div class="card">
  <div class="logo">
    <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="32" height="32" rx="8" fill="#4a154b"/>
      <path d="M8 10h16M8 16h10M8 22h12" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>
    </svg>
    <span>Patch Notify</span>
  </div>

  <h1>Slack 워크스페이스에 앱 설치</h1>
  <p>설치할 Slack 워크스페이스 주소를 입력하세요.<br>
     여러 워크스페이스에 로그인된 경우 올바른 워크스페이스가 자동 선택됩니다.</p>

  <form onsubmit="return handleSubmit(event)">
    <label for="workspace">워크스페이스 URL</label>
    <div class="input-wrap">
      <span class="prefix">https://</span>
      <input id="workspace" type="text" placeholder="mycompany"
             autocomplete="off" spellcheck="false">
      <span class="suffix">.slack.com</span>
    </div>
    <p class="hint">예: mycompany.slack.com → <strong>mycompany</strong> 입력</p>
    <button type="submit" class="btn">설치하기</button>
  </form>

  <div class="divider">또는</div>
  <a href="#" class="btn-direct" onclick="return directInstall(event)">
    워크스페이스 URL 없이 설치
  </a>
</div>

<script>
function handleSubmit(e) {{
  e.preventDefault();
  const val = document.getElementById('workspace').value.trim()
    .replace(/\\.slack\\.com.*$/, '').replace(/^https?:\\/\\//, '').trim();
  if (!val) {{ document.getElementById('workspace').focus(); return false; }}
  window.location.href = '?team=' + encodeURIComponent(val);
  return false;
}}
function directInstall(e) {{
  e.preventDefault();
  window.location.href = '?team=';
  return false;
}}
</script>
</body>
</html>"""


@app.get("/slack/install/")
def slack_install(team: str = None):
    """Slack OAuth 설치 — team 미지정 시 워크스페이스 입력 페이지 표시"""
    if team is None:
        return HTMLResponse(_INSTALL_PAGE)

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
