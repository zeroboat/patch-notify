# Patch Notify

소프트웨어 솔루션의 패치노트를 관리하고 고객사에 Gmail / Slack으로 자동 발송하는 B2B 알림 플랫폼입니다.

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **로그인 / 권한 관리** | Admin · Dev · SE · Guest 4단계 역할 기반 접근 제어 (RBAC) |
| **패치노트 관리** | 제품별 버전/기능추가/기능개선/버그수정/특이사항 등록·수정·삭제 |
| **패치노트 발행** | 작성 후 명시적 발행 처리 — 발행 시 즉시 주기 구독자에게 자동 알림 전송 |
| **Notion 동기화** | Notion Markdown API 기반 패치노트 자동 동기화 (변경 감지 + 파일 캐싱) |
| **영문 자동 번역** | 패치노트 등록·수정 시 내부 Ollama AI 서버로 한→영 번역 (백그라운드) |
| **고객사 관리** | 고객사 정보 및 솔루션 구독 현황 관리, Google 연락처 CSV 가져오기 |
| **구독 관리** | 고객사별 제품 단위 Gmail / Slack 채널 구독 설정 (주기: 즉시·매주·매월·분기) |
| **공문 발송** | 솔루션 선택 또는 직접 입력 방식으로 Gmail 공문 발송, 발송 전 이메일 미리보기 |
| **Slack 앱** | 고객사 워크스페이스에 앱 설치 → Home Tab에서 구독 직접 설정 및 패치노트 조회 |
| **발송 로그** | 발송 이력 조회 (유형/채널/상태/고객사/날짜 필터), 실패 원인 상세 확인 |

---

## 역할별 권한

| 역할 | 패치노트 | 고객사/구독 | 공문 발송 | 제품 관리 |
|------|----------|------------|----------|----------|
| **Admin** | 읽기/쓰기/수정/삭제 | ✅ | ✅ | ✅ |
| **Dev** | 읽기/쓰기/수정/삭제 | ❌ | ❌ | ❌ |
| **SE** | 읽기 전용 | ✅ | ❌ | ❌ |
| **Guest** | 읽기 전용 | ❌ | ❌ | ❌ |

- 최초 배포 시 `.env`의 `DJANGO_SUPERUSER_*`로 생성된 계정은 자동으로 **Admin** 권한을 가집니다.
- 일반 회원가입 계정의 기본 역할은 **Guest**이며, Django Admin(`/admin/`)에서 역할을 변경할 수 있습니다.

---

## 기술 스택

| 서비스 | 기술 |
|--------|------|
| **Backend (내부)** | Django 6.0.2 (Python 3.12) · Gunicorn · WhiteNoise |
| **Slack API (외부)** | FastAPI · Uvicorn · slack-bolt · SQLAlchemy |
| **Database** | PostgreSQL 18 (두 서비스가 공유) |
| **Email** | Gmail SMTP (`EmailMultiAlternatives`) |
| **AI 번역** | Ollama (내부 서버, `/api/generate`) |
| **Notion 연동** | Notion Markdown API |
| **배포** | Docker Compose (backend + slack-api + db) |

---

## 서비스 구조

```
[내부망]                          [외부 공개]
backend (Django · 포트 8000)      slack-api (FastAPI · 포트 8001)
  - 패치노트 / 고객사 / 공문 관리     - GET  /slack/install/
  - 발송 로그 조회                   - GET  /slack/oauth/callback/
  - Django Admin (워크스페이스 승인)  - POST /slack/events/
          │                                │
          └──────── PostgreSQL ────────────┘
                   (테이블 공유)
```

## 프로젝트 구조

```
patch-notify/
├── backend/                     # Django (내부 전용)
│   ├── Dockerfile
│   ├── apps/
│   │   ├── authentication/      # 로그인, 회원가입, 역할(UserProfile)
│   │   ├── base/                # 공통 믹스인 (RoleRequiredMixin, role_required)
│   │   ├── dashboards/          # 대시보드 (홈)
│   │   ├── patchnote/           # 패치노트 등록·수정·삭제·발행, 영문 번역
│   │   ├── product/             # 솔루션 / 제품 관리
│   │   ├── customer/            # 고객사 관리
│   │   ├── notification/        # 공문 작성 및 Gmail 발송
│   │   ├── subscriber/          # 고객사별 구독 설정 (Gmail / Slack)
│   │   ├── slack_app/           # SlackWorkspace 모델·Admin
│   │   ├── notion/              # Notion 페이지 매핑 및 동기화
│   │   └── logs/                # 발송 로그 조회
│   ├── core/                    # settings, urls, context_processors
│   ├── notion_md/               # Notion MD 파일 캐시 (Docker volume)
│   └── requirements.txt
├── slack-api/                   # FastAPI (외부 공개)
│   ├── Dockerfile
│   ├── main.py                  # OAuth install/callback, events 라우트
│   ├── bolt_app.py              # slack_bolt 이벤트 핸들러
│   ├── home_tab.py              # Block Kit 빌더
│   ├── database.py              # SQLAlchemy 엔진
│   ├── models.py                # Django 테이블 Table 정의
│   └── requirements.txt
├── docker-compose.yml
└── .env.example
```

---

## Notion 동기화

Notion 페이지에 작성된 패치노트를 자동으로 가져와 DB에 저장합니다.

### 동작 방식

1. **메타데이터 변경 감지** — Notion 페이지의 `last_edited_time`과 DB에 저장된 타임스탬프를 비교하여 변경 여부 판단
2. **Markdown 파일 캐싱** — Notion Markdown API로 받아온 원본을 Docker volume(`notion_md_data`)에 파일로 저장, 파일 내용 비교로 불필요한 DB 업데이트 방지
3. **파싱 → DB upsert** — 마크다운을 버전별로 분리 후 기능추가/기능개선/버그수정/특이사항으로 분류하여 저장

### 지원 카테고리 매핑

Notion 페이지에서 사용되는 다양한 섹션명을 3개 카테고리로 매핑합니다.

| DB 카테고리 | 매핑되는 섹션명 |
|------------|----------------|
| **기능 추가** (Feature) | 기능 추가, Feature Additions, Added Features, New Features, Feature Addition |
| **기능 개선** (Improvement) | 기능 개선, 기능 수정, 기타, 보안 개선, 가이드, 변경 사항, Feature Improvements, Improvements, Enhancements |
| **버그 수정** (BugFix) | 버그 수정, Bug Fixes, Bug fixes |

### 강제 동기화

동기화 API 호출 시 `force=true` 파라미터를 전달하면 변경 감지를 무시하고 전체 데이터를 갱신합니다.

---

## 시작하기

### 1. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일에 아래 항목을 채워주세요.

```env
SECRET_KEY=...
DEBUG=False
DJANGO_ENVIRONMENT=production

# 접속 허용 호스트 (localhost/127.0.0.1은 자동 포함)
ALLOWED_HOSTS=192.168.0.100,yourdomain.com

# 초기 관리자 계정 (최초 컨테이너 기동 시 자동 생성)
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@yourcompany.com
DJANGO_SUPERUSER_PASSWORD=강력한패스워드!

# PostgreSQL
DB_HOST=db
DB_PORT=5432
DB_NAME=patchnotify
DB_USER=patchuser
DB_PASSWORD=...

# Ollama 번역 서버
OLLAMA_HOST=http://your-ollama-server:11434
OLLAMA_MODEL=your-model-name

# Gmail SMTP (Google 계정 > 보안 > 앱 비밀번호)
GMAIL_USER=your@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# Slack App (FastAPI, 포트 8001)
SLACK_CLIENT_ID=...
SLACK_CLIENT_SECRET=...
SLACK_SIGNING_SECRET=...
SLACK_REDIRECT_URI=https://slack-api.yourdomain.com/slack/oauth/callback/

# Notion 연동
NOTION_ENABLED=false
NOTION_TOKEN=your-notion-integration-token

# [로컬 테스트 전용] SQLite 사용 시 주석 해제
# DATABASE_URL=sqlite:///C:/절대경로/patch-notify/backend/db.sqlite3
```

### 2. Docker 실행

```bash
docker compose up --build -d
```

컨테이너 기동 시 DB 마이그레이션, 초기 관리자 계정 생성, Gunicorn 서버 기동이 자동으로 수행됩니다.

> Notion MD 파일은 `notion_md_data` Docker volume에 영속 저장되므로 컨테이너 재시작 시에도 캐시가 유지됩니다.

```bash
docker compose logs -f backend   # 로그 확인
```

### 3. 로컬 개발 실행

**Django (백엔드)**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver      # http://localhost:8000
```

**FastAPI (Slack API)**
```bash
cd slack-api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

**Slack 로컬 테스트 (ngrok)**
```bash
ngrok http 8001
```
발급된 URL을 Slack App 설정의 Event URL / OAuth Redirect URL에 입력하고 `.env`의 `SLACK_REDIRECT_URI`도 동일하게 변경합니다.

---

## Slack 앱 설정

[api.slack.com/apps](https://api.slack.com/apps)에서 앱 생성 후 아래 항목을 구성합니다.

| 항목 | 값 |
|------|----|
| **OAuth Redirect URL** | `https://slack-api.yourcompany.com/slack/oauth/callback/` |
| **Event Subscriptions URL** | `https://slack-api.yourcompany.com/slack/events/` |
| **Subscribe to Events** | `app_home_opened` |
| **Bot Token Scopes** | `chat:write`, `channels:read` |
| **App Home** | Home Tab 활성화 |

**고객사 연동 흐름:**
1. 고객사 담당자가 `/slack/install/` 접속 → Slack OAuth 동의
2. 관리자가 Django Admin에서 워크스페이스 **승인** + **고객사 연결**
3. 고객사 직원이 Slack Home Tab에서 솔루션별 구독 설정

---

## 오픈소스 라이선스

이 프로젝트는 아래 오픈소스 템플릿을 기반으로 제작되었습니다.

| 항목 | 내용 |
|------|------|
| **템플릿** | [Sneat Free Bootstrap HTML + Django Admin Template](https://themeselection.com/item/sneat-free-bootstrap-html-django-admin-template/) |
| **제작사** | [ThemeSelection](https://themeselection.com/) |
| **라이선스** | [ThemeSelection Freebies License](https://themeselection.com/license/#freebies-license) |
| **GitHub** | [themeselection/sneat-bootstrap-html-django-admin-template-free](https://github.com/themeselection/sneat-bootstrap-html-django-admin-template-free) |
