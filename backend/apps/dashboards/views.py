from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.utils import timezone
from web_project import TemplateLayout

from apps.product.models import Solution
from apps.patchnote.models import PatchNote
from apps.customer.models import Customer


class DashboardsView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard_analytics.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        now = timezone.now()
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 요약 카드
        total_customers = Customer.objects.count()
        total_solutions = Solution.objects.count()
        monthly_patches = PatchNote.objects.filter(release_date__gte=this_month_start).count()
        no_email_count = Customer.objects.filter(emails__isnull=True).distinct().count()

        # 솔루션별 고객사 수
        solutions_with_customers = (
            Solution.objects
            .prefetch_related('customers')
            .order_by('name')
        )

        # 최근 패치노트 5건
        recent_patches = (
            PatchNote.objects
            .select_related('product__solution')
            .order_by('-release_date')[:5]
        )

        # 이메일 미등록 고객사
        no_email_customers = (
            Customer.objects
            .filter(emails__isnull=True)
            .prefetch_related('solutions')
            .distinct()
            .order_by('name')
        )

        context.update({
            'total_customers': total_customers,
            'total_solutions': total_solutions,
            'monthly_patches': monthly_patches,
            'no_email_count': no_email_count,
            'solutions_with_customers': solutions_with_customers,
            'recent_patches': recent_patches,
            'no_email_customers': no_email_customers,
            'current_month': now.strftime('%Y년 %m월'),
        })
        return context
