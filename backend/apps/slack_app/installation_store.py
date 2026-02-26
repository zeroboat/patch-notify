from slack_sdk.oauth.installation_store import InstallationStore
from slack_sdk.oauth.installation_store.models.bot import Bot
from slack_sdk.oauth.installation_store.models.installation import Installation


class DjangoInstallationStore(InstallationStore):
    """SlackWorkspace 모델 기반 Installation Store"""

    def save(self, installation: Installation, **kwargs):
        from .models import SlackWorkspace
        SlackWorkspace.objects.update_or_create(
            team_id=installation.team_id,
            defaults={
                'team_name': installation.team_name or '',
                'bot_token': installation.bot_token,
            },
        )

    def find_bot(self, *, enterprise_id=None, team_id=None, **kwargs):
        """Bolt이 이벤트 처리 시 토큰 조회 — 미승인도 토큰 반환 (핸들러에서 승인 여부 확인)"""
        from .models import SlackWorkspace
        workspace = SlackWorkspace.objects.filter(team_id=team_id).first()
        if not workspace:
            return None
        return Bot(
            bot_token=workspace.bot_token,
            team_id=workspace.team_id,
            team_name=workspace.team_name,
        )

    def find_installation(self, *, enterprise_id=None, team_id=None, **kwargs):
        from .models import SlackWorkspace
        workspace = SlackWorkspace.objects.filter(team_id=team_id).first()
        if not workspace:
            return None
        return Installation(
            bot_token=workspace.bot_token,
            team_id=workspace.team_id,
            team_name=workspace.team_name,
        )
