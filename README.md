# Patch Notify

소프트웨어 솔루션의 패치노트를 관리하고 고객사에 Gmail / Slack으로 자동 발송하는 B2B 알림 플랫폼입니다.

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **로그인 / 권한 관리** | Admin · Dev · SE 3단계 역할 기반 접근 제어 (RBAC) |
| **패치노트 관리** | 제품별 버전/기능추가/기능개선/버그수정/특이사항 등록·수정·삭제 |
| **영문 자동 번역** | 패치노트 등록·수정 시 내부 Ollama AI 서버로 한→영 번역 (백그라운드) |
| **고객사 관리** | 고객사 정보 및 솔루션 구독 현황 관리 |
| **구독 관리** | 고객사별 Gmail / Slack 채널 구독 설정 (주기, 최대 건수) |
| **공문 발송** | 솔루션 선택 또는 직접 입력 방식으로 Gmail 공문 발송 |
| **Slack 앱** | 고객사 워크스페이스에 앱 설치 → Home Tab에서 구독 직접 설정 |
| **발송 로그** | 발송 이력 조회 (유형/채널/상태/고객사/날짜 필터) |

---

## 역할별 권한

| 역할 | 패치노트 | 고객사/구독 | 공문 발송 | 제품 관리 |
|------|----------|------------|----------|----------|
| **Admin** | 읽기/쓰기/수정/삭제 | ✅ | ✅ | ✅ |
| **Dev** | 읽기/쓰기/수정/삭제 | ❌ | ❌ | ❌ |
| **SE** | 읽기 전용 | ✅ | ❌ | ❌ |

- 최초 배포 후 `.env`의 `DJANGO_SUPERUSER_*`로 생성된 계정은 자동으로 **Admin** 권한을 가집니다.
- 이후 일반 회원가입 계정의 기본 역할은 **SE**이며, Django Admin(`/admin/`)에서 역할을 변경할 수 있습니다.

---

## 기술 스택

- **Backend** Django 6.0.2 (Python 3.12)
- **Database** PostgreSQL 18
- **Static Files** WhiteNoise (Gunicorn 환경에서 static 서빙)
- **Email** Gmail SMTP (`EmailMultiAlternatives`)
- **Slack** slack-bolt (OAuth 2.0, Home Tab, Block Kit)
- **AI 번역** Ollama (내부 서버, `/api/generate`)
- **배포** Docker Compose (backend + db)

---

## 프로젝트 구조

```
patch-notify/
├── backend/
│   ├── apps/
│   │   ├── authentication/  # 로그인, 회원가입, 역할(UserProfile)
│   │   ├── base/            # 공통 믹스인 (RoleRequiredMixin, role_required)
│   │   ├── patchnote/       # 패치노트 등록·수정·삭제, 영문 번역
│   │   ├── product/         # 솔루션 / 제품 관리
│   │   ├── customer/        # 고객사 관리
│   │   ├── notification/    # 공문 작성 및 Gmail 발송
│   │   ├── subscriber/      # 고객사별 구독 설정 (Gmail / Slack)
│   │   ├── slack_app/       # Slack 앱 OAuth, Home Tab, 이벤트 처리
│   │   └── logs/            # 발송 로그 조회
│   ├── core/                # settings, urls, context_processors
│   └── requirements.txt
├── docker-compose.yml
├── .env.example
└── dev.env                  # 로컬 개발용 환경변수 (gitignore)
```

---

## 시작하기

### 1. 환경변수 설정

```bash
cp .env.example .env
```

`.env`를 열어 아래 항목을 채워주세요.

```env
SECRET_KEY=...

# 접속 허용 호스트 (localhost/127.0.0.1은 자동 포함)
ALLOWED_HOSTS=192.168.0.100,yourdomain.com

# 초기 관리자 계정 (최초 컨테이너 기동 시 자동 생성)
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@yourcompany.com
DJANGO_SUPERUSER_PASSWORD=강력한패스워드!

# PostgreSQL
DB_HOST=db
DB_NAME=patchnotify
DB_USER=patchuser
DB_PASSWORD=...

# Ollama 번역 서버
OLLAMA_HOST=http://your-ollama-server:11434
OLLAMA_MODEL=your-model-name

# Gmail SMTP (Google 계정 > 보안 > 앱 비밀번호)
GMAIL_USER=your@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# Slack App (https://api.slack.com/apps)
SLACK_CLIENT_ID=...
SLACK_CLIENT_SECRET=...
SLACK_SIGNING_SECRET=...
SLACK_REDIRECT_URI=https://yourdomain.com/slack/oauth/callback/
```

### 2. Docker 실행

```bash
docker compose up --build -d
```

컨테이너 기동 시 아래 작업이 자동으로 수행됩니다.

1. DB 마이그레이션 (`migrate --noinput`)
2. 초기 관리자 계정 생성 (이미 존재하면 무시)
3. Gunicorn 서버 기동

로그 확인:
```bash
docker compose logs -f backend
```

### 3. 로컬 개발 실행

```bash
cp .env.example dev.env   # dev.env 값 채우기

cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

---

## Slack 앱 설정

[api.slack.com/apps](https://api.slack.com/apps)에서 앱 생성 후 아래 항목을 구성합니다.

| 항목 | 값 |
|------|----|
| **OAuth Redirect URL** | `https://yourdomain.com/slack/oauth/callback/` |
| **Event Subscriptions URL** | `https://yourdomain.com/slack/events/` |
| **Subscribe to Events** | `app_home_opened` |
| **Bot Token Scopes** | `chat:write`, `channels:read` |
| **App Home** | Home Tab 활성화 |

**고객사 연동 흐름:**
1. 고객사 담당자가 `/slack/install/` 접속 → Slack OAuth 동의
2. 관리자가 Django Admin에서 워크스페이스 **승인** + **고객사 연결**
3. 고객사 직원이 Slack Home Tab에서 솔루션별 구독 설정

---

## Gmail 앱 비밀번호 발급

1. Google 계정 → **보안** → **2단계 인증** 활성화
2. **앱 비밀번호** → 앱: `메일` / 기기: `기타(직접 입력)` → 생성
3. 발급된 16자리를 `GMAIL_APP_PASSWORD`에 입력

---

## 발송 로그

`/logs/` 페이지에서 공문 및 구독 자동 발송 이력을 조회할 수 있습니다.

- 필터: 발송 유형 / 채널 / 상태 / 고객사 / 날짜 범위
- 실패 건은 `error_message` 컬럼에서 원인 확인 가능
