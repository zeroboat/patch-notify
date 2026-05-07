from django.views.generic import TemplateView
from django.core.paginator import Paginator

from web_project import TemplateLayout
from apps.base.mixins import RoleRequiredMixin, get_user_role
from apps.customer.models import Customer
from apps.patchnote.models import PatchNote
from .models import DispatchLog


class DispatchLogView(RoleRequiredMixin, TemplateView):
    """Admin + SE: 발송 로그 조회"""
    allowed_roles = ['se']
    template_name = "logs/dispatch_log.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        # 외부 발송 대기 중인 패치노트 (지연 발송 대기열)
        pending_external = (
            PatchNote.objects
            .filter(external_send_status=PatchNote.EXTERNAL_SEND_PENDING)
            .select_related('product__solution')
            .order_by('external_send_scheduled_at')
        )
        user_role = get_user_role(self.request.user) if self.request.user.is_authenticated else 'guest'
        can_control_external = user_role in ('admin', 'manager')

        qs = DispatchLog.objects.select_related('customer', 'solution', 'official_notice')

        # 필터
        log_type = self.request.GET.get('log_type', '')
        channel = self.request.GET.get('channel', '')
        status = self.request.GET.get('status', '')
        customer_id = self.request.GET.get('customer_id', '')
        date_from = self.request.GET.get('date_from', '')
        date_to = self.request.GET.get('date_to', '')

        if log_type:
            qs = qs.filter(log_type=log_type)
        if channel:
            qs = qs.filter(channel=channel)
        if status:
            qs = qs.filter(status=status)
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if date_from:
            qs = qs.filter(sent_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(sent_at__date__lte=date_to)

        # 요약
        total = qs.count()
        success_count = qs.filter(status=DispatchLog.STATUS_SUCCESS).count()
        failed_count = qs.filter(status=DispatchLog.STATUS_FAILED).count()
        pending_count = qs.filter(status=DispatchLog.STATUS_PENDING).count()

        # 페이지네이션
        paginator = Paginator(qs, 50)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context.update({
            'pending_external': pending_external,
            'can_control_external': can_control_external,
            'page_obj': page_obj,
            'total': total,
            'success_count': success_count,
            'failed_count': failed_count,
            'pending_count': pending_count,
            'customers': Customer.objects.order_by('name'),
            # 현재 필터값 (폼 유지)
            'filter_log_type': log_type,
            'filter_channel': channel,
            'filter_status': status,
            'filter_customer_id': customer_id,
            'filter_date_from': date_from,
            'filter_date_to': date_to,
            'log_type_choices': DispatchLog.LOG_TYPE_CHOICES,
            'channel_choices': DispatchLog.CHANNEL_CHOICES,
            'status_choices': DispatchLog.STATUS_CHOICES,
        })
        return context
