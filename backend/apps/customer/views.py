import csv
import io
import logging

from django.shortcuts import redirect
from django.views.generic import TemplateView
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from web_project import TemplateLayout
from apps.base.mixins import RoleRequiredMixin, role_required
from .models import Customer, CustomerEmail
from apps.product.models import Solution

logger = logging.getLogger(__name__)


class CustomerManagementView(RoleRequiredMixin, TemplateView):
    """Admin + SE: 고객사 관리"""
    allowed_roles = ['se']
    template_name = "customer/customer_management.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        customers = Customer.objects.prefetch_related('emails', 'solutions').order_by('name')
        solutions = Solution.objects.order_by('name')
        context.update({
            'customers': customers,
            'solutions': solutions,
            'total_customers': customers.count(),
        })
        return context


@role_required('se')
def create_customer(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            is_on_premise = request.POST.get('is_on_premise') == 'on'
            Customer.objects.create(name=name, is_on_premise=is_on_premise)
            messages.success(request, f'고객사 "{name}"이 등록되었습니다.')
        else:
            messages.error(request, '고객사명을 입력해주세요.')
    return redirect('customer:customer_management')


@require_POST
@role_required('se')
def add_email(request):
    customer_id = request.POST.get('customer_id')
    email = request.POST.get('email', '').strip()
    name = request.POST.get('name', '').strip()

    try:
        customer = Customer.objects.get(id=customer_id)
        if not email:
            return JsonResponse({'error': '이메일을 입력해주세요.'}, status=400)
        obj, created = CustomerEmail.objects.get_or_create(
            customer=customer,
            email=email,
            defaults={'name': name or None},
        )
        if not created:
            return JsonResponse({'error': '이미 등록된 이메일입니다.'}, status=400)
        return JsonResponse({'message': f'이메일 {email}이 등록되었습니다.', 'email_id': obj.id})
    except Customer.DoesNotExist:
        return JsonResponse({'error': '고객사를 찾을 수 없습니다.'}, status=404)


@require_POST
@role_required('se')
def delete_email(request):
    email_id = request.POST.get('email_id')
    try:
        email_obj = CustomerEmail.objects.get(id=email_id)
        email_addr = email_obj.email
        email_obj.delete()
        return JsonResponse({'message': f'{email_addr}이 삭제되었습니다.'})
    except CustomerEmail.DoesNotExist:
        return JsonResponse({'error': '이메일을 찾을 수 없습니다.'}, status=404)


@require_POST
@role_required('se')
def delete_customer(request):
    customer_id = request.POST.get('customer_id')
    try:
        customer = Customer.objects.get(id=customer_id)
        name = customer.name
        customer.delete()
        return JsonResponse({'message': f'"{name}"이 삭제되었습니다.'})
    except Customer.DoesNotExist:
        return JsonResponse({'error': '고객사를 찾을 수 없습니다.'}, status=404)


@require_POST
@role_required('se')
def update_customer(request):
    customer_id = request.POST.get('customer_id')
    name = request.POST.get('name', '').strip()
    solution_ids = request.POST.getlist('solution_ids')
    is_on_premise = request.POST.get('is_on_premise') == 'true'

    try:
        customer = Customer.objects.get(id=customer_id)
        if name:
            customer.name = name
        customer.is_on_premise = is_on_premise
        customer.save()
        customer.solutions.set(solution_ids)
        return JsonResponse({'message': f'"{customer.name}" 정보가 저장되었습니다.'})
    except Customer.DoesNotExist:
        return JsonResponse({'error': '고객사를 찾을 수 없습니다.'}, status=404)


@require_POST
@role_required('se')
def import_csv(request):
    """Google 연락처 CSV 파일에서 고객사 + 이메일 일괄 등록"""
    csv_file = request.FILES.get('csv_file')
    if not csv_file:
        return JsonResponse({'error': 'CSV 파일을 선택해주세요.'}, status=400)

    if not csv_file.name.endswith('.csv'):
        return JsonResponse({'error': 'CSV 파일만 업로드 가능합니다.'}, status=400)

    try:
        raw = csv_file.read()
        # BOM 제거 + UTF-8 디코딩 (Excel CSV 호환)
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            text = raw.decode('euc-kr')
        except UnicodeDecodeError:
            return JsonResponse({'error': '파일 인코딩을 인식할 수 없습니다. UTF-8 또는 EUC-KR을 사용해주세요.'}, status=400)

    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []

    # Google Contacts CSV 컬럼 매핑 (대소문자 무시)
    headers_lower = {h.lower(): h for h in headers}
    # 표시명(Name) 컬럼 — 없으면 성/이름 분리 컬럼으로 조합
    name_col       = _find_col_ci(headers_lower, ['name', '이름'])
    last_name_col  = _find_col_ci(headers_lower, ['family name', 'last name', '성'])
    middle_name_col = _find_col_ci(headers_lower, ['additional name', 'middle name'])
    first_name_col = _find_col_ci(headers_lower, ['given name', 'first name', '이름'])
    org_col = _find_col_ci(headers_lower, [
        'organization 1 - name', '조직 1 - 이름',
        'organization name', 'company', '회사',
    ])
    # 이메일 값 컬럼: *value* 포함 우선, 없으면 *label* 제외한 mail 컬럼
    email_cols = [h for h in headers if 'value' in h.lower() and 'mail' in h.lower()]
    if not email_cols:
        email_cols = [h for h in headers if 'mail' in h.lower()
                      and 'label' not in h.lower() and 'type' not in h.lower()]

    if not email_cols:
        return JsonResponse({
            'error': '이메일 컬럼을 찾을 수 없습니다. Google 연락처에서 내보낸 CSV인지 확인해주세요.',
            'headers': headers,
        }, status=400)

    created_customers = 0
    created_emails = 0
    skipped_emails = 0

    for row in reader:
        org_name = (row.get(org_col, '') if org_col else '').strip()

        # 담당자명: 표시명 우선, 없으면 성+이름 조합 (한국식: 성 먼저)
        contact_name = (row.get(name_col, '') if name_col else '').strip()
        if not contact_name:
            last   = (row.get(last_name_col,   '') if last_name_col   else '').strip()
            middle = (row.get(middle_name_col, '') if middle_name_col else '').strip()
            first  = (row.get(first_name_col,  '') if first_name_col  else '').strip()
            contact_name = ''.join(filter(None, [last, middle, first]))

        # 이메일 수집 (셀 내 ':::' 구분자로 복수 이메일 지원)
        emails = []
        for col in email_cols:
            raw = (row.get(col, '') or '').strip()
            for addr in raw.split(':::'):
                addr = addr.strip()
                if addr and '@' in addr:
                    emails.append(addr)

        if not emails:
            continue

        # 고객사명: 조직명 우선, 없으면 개인명
        customer_name = org_name or contact_name
        if not customer_name:
            continue

        # 담당자명: 이름이 있고 회사명과 다를 때만 저장
        email_contact = contact_name if contact_name and contact_name != customer_name else None

        customer, c_created = Customer.objects.get_or_create(name=customer_name)
        if c_created:
            created_customers += 1

        for addr in emails:
            _, e_created = CustomerEmail.objects.update_or_create(
                customer=customer,
                email=addr,
                defaults={'name': email_contact},
            )
            if e_created:
                created_emails += 1
            else:
                skipped_emails += 1

    return JsonResponse({
        'message': f'가져오기 완료 — 고객사 {created_customers}개 신규, 이메일 {created_emails}개 추가, {skipped_emails}개 중복 건너뜀',
        'created_customers': created_customers,
        'created_emails': created_emails,
        'skipped_emails': skipped_emails,
    })


def _find_col_ci(headers_lower: dict, candidates: list) -> str | None:
    """대소문자 무시하여 후보 컬럼명과 일치하는 원본 컬럼명 반환
    headers_lower: {lower_key: original_header} 형태의 dict
    """
    for c in candidates:
        if c.lower() in headers_lower:
            return headers_lower[c.lower()]
    return None
