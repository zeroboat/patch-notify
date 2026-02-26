import requests as http_requests

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from slack_bolt.adapter.django import SlackRequestHandler

from .bolt_app import bolt_app

_handler = SlackRequestHandler(app=bolt_app)


def slack_install(request):
    """Slack OAuth 설치 시작 — Slack 인증 화면으로 리다이렉트"""
    scopes = 'chat:write,channels:read'
    url = (
        "https://slack.com/oauth/v2/authorize"
        f"?client_id={settings.SLACK_CLIENT_ID}"
        f"&scope={scopes}"
        f"&redirect_uri={settings.SLACK_REDIRECT_URI}"
    )
    return redirect(url)


def slack_oauth_callback(request):
    """Slack OAuth 콜백 — 토큰 교환 후 SlackWorkspace 생성"""
    error = request.GET.get('error')
    if error:
        return HttpResponse(f"Slack 설치 오류: {error}", status=400)

    code = request.GET.get('code')
    if not code:
        return HttpResponse("인증 코드가 없습니다.", status=400)

    resp = http_requests.post(
        'https://slack.com/api/oauth.v2.access',
        data={
            'client_id': settings.SLACK_CLIENT_ID,
            'client_secret': settings.SLACK_CLIENT_SECRET,
            'code': code,
            'redirect_uri': settings.SLACK_REDIRECT_URI,
        },
        timeout=10,
    )
    data = resp.json()

    if not data.get('ok'):
        return HttpResponse(f"인증 실패: {data.get('error', 'unknown')}", status=400)

    team_id = data['team']['id']
    team_name = data['team']['name']
    bot_token = data['access_token']

    from .models import SlackWorkspace
    workspace, created = SlackWorkspace.objects.update_or_create(
        team_id=team_id,
        defaults={
            'team_name': team_name,
            'bot_token': bot_token,
        },
    )

    if created:
        msg = (
            f"✅ '{team_name}' 워크스페이스 설치가 완료되었습니다.\n"
            "관리자 승인 후 Slack 앱을 이용할 수 있습니다."
        )
    else:
        msg = f"✅ '{team_name}' 워크스페이스 토큰이 갱신되었습니다."

    return HttpResponse(msg, content_type='text/plain; charset=utf-8')


@csrf_exempt
def slack_events(request):
    """Slack 이벤트 수신 엔드포인트 (slack_bolt가 서명 검증 처리)"""
    return _handler.handle(request)
