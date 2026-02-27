from django.views.generic import TemplateView
from django.contrib.auth.views import LoginView
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.shortcuts import redirect

from web_project import TemplateLayout
from web_project.template_helpers.theme import TemplateHelper


class AuthView(TemplateView):
    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context.update({
            "layout_path": TemplateHelper.set_layout("layout_blank.html", context),
        })
        return context


class UserLoginView(LoginView, AuthView):
    template_name = "auth_login_basic.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Login - Admin Area"})
        return context


class RegisterView(AuthView):
    template_name = "auth_register_basic.html"

    def post(self, request):
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        errors = []
        if not username:
            errors.append('사용자명을 입력해주세요.')
        elif User.objects.filter(username=username).exists():
            errors.append('이미 사용 중인 사용자명입니다.')
        if not password:
            errors.append('비밀번호를 입력해주세요.')

        if errors:
            context = self.get_context_data()
            context['errors'] = errors
            context['form_data'] = {'username': username, 'email': email}
            return self.render_to_response(context)

        user = User.objects.create_user(username=username, email=email, password=password)
        login(request, user)
        return redirect('index')
