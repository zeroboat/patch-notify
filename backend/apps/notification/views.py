from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

from web_project import TemplateLayout

# Create your views here.

class OfficialNoticeView(LoginRequiredMixin, TemplateView):
    template_name = "notification/official_notice.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Sneat 레이아웃 초기화 (layout_path 설정)
        context = TemplateLayout.init(self, context)
        context['page_title'] = "공문 작성"
        return context