"""
Nextcloud WebDAV 연동 서비스
- 파일 업로드 (WebDAV PUT)
- 공유 링크 생성 (OCS API)
- 파일 삭제 (WebDAV DELETE)
"""

import logging
from pathlib import PurePosixPath

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _is_enabled():
    return bool(getattr(settings, 'NEXTCLOUD_ENABLED', False))


def _base_url():
    return getattr(settings, 'NEXTCLOUD_URL', '').rstrip('/')


def _auth():
    return (
        getattr(settings, 'NEXTCLOUD_USER', ''),
        getattr(settings, 'NEXTCLOUD_PASSWORD', ''),
    )


def _upload_base():
    """Nextcloud 내부 저장 루트 경로 (예: /patch-notify/media)"""
    return getattr(settings, 'NEXTCLOUD_UPLOAD_PATH', '/patch-notify/media')


def _webdav_url(remote_path):
    """WebDAV 전체 URL 생성"""
    user = _auth()[0]
    return f"{_base_url()}/remote.php/dav/files/{user}{remote_path}"


def _ensure_parents(remote_path):
    """상위 디렉토리를 재귀적으로 생성 (MKCOL)"""
    parts = PurePosixPath(remote_path).parents
    # 루트(/)부터 순서대로 생성
    dirs_to_create = [str(p) for p in reversed(list(parts)) if str(p) != '/']
    for d in dirs_to_create:
        url = _webdav_url(d)
        requests.request('MKCOL', url, auth=_auth(), timeout=10)
        # 이미 존재하면 405 반환 — 무시


def upload_to_nextcloud(file_field):
    """
    Django FileField의 파일을 Nextcloud에 업로드.
    Returns: True/False
    """
    if not _is_enabled():
        return False

    try:
        remote_path = f"{_upload_base()}/{file_field.name}"
        _ensure_parents(remote_path)

        url = _webdav_url(remote_path)
        with open(file_field.path, 'rb') as f:
            resp = requests.put(url, data=f, auth=_auth(), timeout=120)

        if resp.status_code in (201, 204):
            logger.info("Nextcloud 업로드 성공: %s", remote_path)
            return True
        else:
            logger.error("Nextcloud 업로드 실패 (%s): %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.error("Nextcloud 업로드 예외: %s", e)
        return False


def create_share_link(file_field):
    """
    Nextcloud OCS API로 공유 링크 생성.
    Returns: 다운로드 URL 문자열 또는 None
    """
    if not _is_enabled():
        return None

    try:
        remote_path = f"{_upload_base()}/{file_field.name}"
        url = f"{_base_url()}/ocs/v2.php/apps/files_sharing/api/v1/shares?format=json"
        resp = requests.post(
            url,
            auth=_auth(),
            headers={
                'OCS-APIRequest': 'true',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            data={
                'path': remote_path,
                'shareType': 3,       # 공개 링크
                'permissions': 1,     # 읽기 전용
            },
            timeout=30,
        )

        if resp.status_code in (200, 201):
            data = resp.json()
            token = data['ocs']['data']['token']
            share_url = f"{_base_url()}/s/{token}"
            logger.info("Nextcloud 공유 링크 생성: %s", share_url)
            return share_url
        else:
            logger.error("Nextcloud 공유 링크 실패 (%s): %s", resp.status_code, resp.text)
            return None
    except Exception as e:
        logger.error("Nextcloud 공유 링크 예외: %s", e)
        return None


def delete_from_nextcloud(file_field):
    """
    Nextcloud에서 파일 삭제 (WebDAV DELETE).
    Returns: True/False
    """
    if not _is_enabled():
        return False

    try:
        remote_path = f"{_upload_base()}/{file_field.name}"
        url = _webdav_url(remote_path)
        resp = requests.delete(url, auth=_auth(), timeout=30)

        if resp.status_code in (200, 204):
            logger.info("Nextcloud 파일 삭제 성공: %s", remote_path)
            return True
        else:
            logger.error("Nextcloud 파일 삭제 실패 (%s): %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.error("Nextcloud 파일 삭제 예외: %s", e)
        return False
