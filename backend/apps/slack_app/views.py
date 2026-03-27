from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from web_project import TemplateLayout
from apps.base.mixins import RoleRequiredMixin, role_required
from apps.customer.models import Customer
from .models import SlackWorkspace


class SlackWorkspaceManagementView(RoleRequiredMixin, TemplateView):
    """Admin + Manager: Slack 워크스페이스 관리"""
    allowed_roles = []
    template_name = "slack_app/slack_workspace_management.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        workspaces = SlackWorkspace.objects.select_related('customer').order_by('-created_at')

        context['workspaces'] = workspaces
        context['customers'] = Customer.objects.order_by('name')
        context['total'] = workspaces.count()
        context['pending_count'] = workspaces.filter(status=SlackWorkspace.STATUS_PENDING).count()
        context['approved_count'] = workspaces.filter(status=SlackWorkspace.STATUS_APPROVED).count()
        context['rejected_count'] = workspaces.filter(status=SlackWorkspace.STATUS_REJECTED).count()
        return context


@require_POST
@role_required()
def update_workspace_status(request):
    """Admin+Manager AJAX: 워크스페이스 상태 변경"""
    workspace_id = request.POST.get('workspace_id')
    status = request.POST.get('status')

    if status not in ('pending', 'approved', 'rejected'):
        return JsonResponse({'ok': False, 'error': '유효하지 않은 상태입니다.'})

    try:
        workspace = SlackWorkspace.objects.get(pk=workspace_id)
    except SlackWorkspace.DoesNotExist:
        return JsonResponse({'ok': False, 'error': '워크스페이스를 찾을 수 없습니다.'}, status=404)

    workspace.status = status
    workspace.save(update_fields=['status', 'updated_at'])

    return JsonResponse({
        'ok': True,
        'message': f'{workspace.team_name} 상태가 {workspace.get_status_display()}(으)로 변경되었습니다.',
    })


@require_POST
@role_required()
def link_workspace_customer(request):
    """Admin+Manager AJAX: 워크스페이스에 고객사 연결/해제"""
    workspace_id = request.POST.get('workspace_id')
    customer_id = request.POST.get('customer_id')

    try:
        workspace = SlackWorkspace.objects.get(pk=workspace_id)
    except SlackWorkspace.DoesNotExist:
        return JsonResponse({'ok': False, 'error': '워크스페이스를 찾을 수 없습니다.'}, status=404)

    if customer_id:
        try:
            customer = Customer.objects.get(pk=customer_id)
        except Customer.DoesNotExist:
            return JsonResponse({'ok': False, 'error': '고객사를 찾을 수 없습니다.'}, status=404)
        workspace.customer = customer
        msg = f'{workspace.team_name}이(가) {customer.name}에 연결되었습니다.'
    else:
        workspace.customer = None
        msg = f'{workspace.team_name}의 고객사 연결이 해제되었습니다.'

    workspace.save(update_fields=['customer', 'updated_at'])
    return JsonResponse({'ok': True, 'message': msg})
