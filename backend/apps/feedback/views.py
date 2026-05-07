import os
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import TemplateView
from django.views.decorators.http import require_POST

from apps.base.mixins import get_user_role
from web_project import TemplateLayout
from .models import Feedback, FeedbackComment

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def _can_edit(user, feedback):
    role = get_user_role(user)
    if role in ('admin', 'manager'):
        return True
    return feedback.author == user


def _can_change_status(user):
    return get_user_role(user) in ('admin', 'manager')


class FeedbackListView(LoginRequiredMixin, TemplateView):
    template_name = 'feedback/list.html'

    def dispatch(self, request, *args, **kwargs):
        if get_user_role(request.user) == 'guest':
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = TemplateLayout.init(self, context)

        qs = Feedback.objects.select_related('author', 'assignee')

        category = self.request.GET.get('category', '')
        status = self.request.GET.get('status', '')
        priority = self.request.GET.get('priority', '')
        q = self.request.GET.get('q', '').strip()
        mine = self.request.GET.get('mine', '')

        if category:
            qs = qs.filter(category=category)
        if status:
            qs = qs.filter(status=status)
        if priority:
            qs = qs.filter(priority=priority)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(content__icontains=q))
        if mine:
            qs = qs.filter(author=self.request.user)

        open_count = Feedback.objects.filter(status__in=['open', 'reviewing']).count()

        context.update({
            'feedbacks': qs,
            'open_count': open_count,
            'user_role': get_user_role(self.request.user),
            'filter_category': category,
            'filter_status': status,
            'filter_priority': priority,
            'filter_q': q,
            'filter_mine': mine,
            'category_choices': Feedback.Category.choices,
            'status_choices': Feedback.Status.choices,
            'priority_choices': Feedback.Priority.choices,
        })
        return context


class FeedbackDetailView(LoginRequiredMixin, TemplateView):
    template_name = 'feedback/detail.html'

    def dispatch(self, request, *args, **kwargs):
        if get_user_role(request.user) == 'guest':
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = TemplateLayout.init(self, context)
        feedback = get_object_or_404(Feedback.objects.prefetch_related('comments__author'), pk=self.kwargs['pk'])
        context.update({
            'feedback': feedback,
            'user_role': get_user_role(self.request.user),
            'can_edit': _can_edit(self.request.user, feedback),
            'can_change_status': _can_change_status(self.request.user),
            'status_choices': Feedback.Status.choices,
            'priority_choices': Feedback.Priority.choices,
        })
        return context


@require_POST
@login_required
def feedback_create(request):
    if get_user_role(request.user) == 'guest':
        raise PermissionDenied

    title = request.POST.get('title', '').strip()
    content = request.POST.get('content', '').strip()
    category = request.POST.get('category', Feedback.Category.UX)
    page_url = request.POST.get('page_url', '').strip()
    author_name = request.POST.get('author_name', '').strip()

    if not title or not content:
        return JsonResponse({'error': '제목과 내용을 입력해주세요.'}, status=400)

    today_count = Feedback.objects.filter(
        author=request.user, created_at__date=timezone.localdate()
    ).count()
    if today_count >= 10:
        return JsonResponse({'error': '하루 최대 10개의 피드백만 등록할 수 있습니다.'}, status=429)

    if not author_name:
        author_name = request.user.get_full_name() or request.user.username

    feedback = Feedback(
        title=title,
        content=content,
        category=category,
        page_url=page_url,
        author=request.user,
        author_name=author_name,
    )

    attachment = request.FILES.get('attachment')
    if attachment:
        ext = os.path.splitext(attachment.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return JsonResponse({'error': 'jpg, png, gif 파일만 첨부할 수 있습니다.'}, status=400)
        if attachment.size > MAX_FILE_SIZE:
            return JsonResponse({'error': '첨부 파일은 5MB 이하만 가능합니다.'}, status=400)
        feedback.attachment = attachment

    feedback.save()

    # 사내 Slack 알림 (Phase 4에서 연동)
    _notify_slack_new_feedback(feedback)

    return JsonResponse({'id': feedback.id, 'message': '피드백이 등록되었습니다.'})


@require_POST
@login_required
def feedback_update(request, pk):
    feedback = get_object_or_404(Feedback, pk=pk)
    if not _can_edit(request.user, feedback):
        raise PermissionDenied

    role = get_user_role(request.user)

    title = request.POST.get('title', '').strip()
    content = request.POST.get('content', '').strip()
    if not title or not content:
        return JsonResponse({'error': '제목과 내용을 입력해주세요.'}, status=400)

    feedback.title = title
    feedback.content = content
    feedback.category = request.POST.get('category', feedback.category)

    if role in ('admin', 'manager'):
        new_status = request.POST.get('status', feedback.status)
        feedback.status = new_status
        assignee_id = request.POST.get('assignee_id')
        if assignee_id:
            feedback.assignee_id = assignee_id
        feedback.resolution_note = request.POST.get('resolution_note', feedback.resolution_note)
        _closed = (Feedback.Status.DONE, Feedback.Status.WONT_DO, Feedback.Status.DUPLICATE)
        if new_status in _closed and not feedback.resolved_at:
            feedback.resolved_at = timezone.now()
        elif new_status not in _closed:
            feedback.resolved_at = None

    feedback.save()
    return JsonResponse({'message': '수정되었습니다.'})


@require_POST
@login_required
def feedback_delete(request, pk):
    feedback = get_object_or_404(Feedback, pk=pk)
    if not _can_edit(request.user, feedback):
        raise PermissionDenied
    if feedback.attachment:
        feedback.attachment.delete(save=False)
    feedback.delete()
    return JsonResponse({'message': '삭제되었습니다.'})


@require_POST
@login_required
def feedback_status_update(request, pk):
    if not _can_change_status(request.user):
        raise PermissionDenied
    feedback = get_object_or_404(Feedback, pk=pk)
    new_status = request.POST.get('status')
    if new_status not in dict(Feedback.Status.choices):
        return JsonResponse({'error': '유효하지 않은 상태입니다.'}, status=400)

    feedback.status = new_status
    _closed = (Feedback.Status.DONE, Feedback.Status.WONT_DO, Feedback.Status.DUPLICATE)
    if new_status in _closed and not feedback.resolved_at:
        feedback.resolved_at = timezone.now()
    elif new_status not in _closed:
        feedback.resolved_at = None
    feedback.save(update_fields=['status', 'resolved_at', 'updated_at'])
    return JsonResponse({'message': '상태가 변경되었습니다.', 'status_display': feedback.get_status_display()})


@require_POST
@login_required
def feedback_priority_update(request, pk):
    if not _can_change_status(request.user):
        raise PermissionDenied
    feedback = get_object_or_404(Feedback, pk=pk)
    new_priority = request.POST.get('priority')
    if new_priority not in dict(Feedback.Priority.choices):
        return JsonResponse({'error': '유효하지 않은 우선순위입니다.'}, status=400)
    feedback.priority = new_priority
    feedback.save(update_fields=['priority', 'updated_at'])
    return JsonResponse({'message': '우선순위가 변경되었습니다.', 'priority_display': feedback.get_priority_display()})


@require_POST
@login_required
def feedback_comment_create(request, pk):
    if get_user_role(request.user) == 'guest':
        raise PermissionDenied
    feedback = get_object_or_404(Feedback, pk=pk)
    content = request.POST.get('content', '').strip()
    author_name = request.POST.get('author_name', '').strip()
    if not content:
        return JsonResponse({'error': '댓글 내용을 입력해주세요.'}, status=400)
    if not author_name:
        author_name = request.user.get_full_name() or request.user.username
    comment = FeedbackComment.objects.create(
        feedback=feedback, author=request.user,
        author_name=author_name, content=content,
    )
    return JsonResponse({
        'id': comment.id,
        'content': comment.content,
        'author': comment.author_name,
        'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M'),
    })


@require_POST
@login_required
def feedback_comment_delete(request, pk, comment_pk):
    comment = get_object_or_404(FeedbackComment, pk=comment_pk, feedback_id=pk)
    role = get_user_role(request.user)
    if role not in ('admin', 'manager') and comment.author != request.user:
        raise PermissionDenied
    comment.delete()
    return JsonResponse({'message': '삭제되었습니다.'})


def _notify_slack_new_feedback(feedback):
    """사내 Slack 신규 피드백 알림 — Phase 4에서 연동"""
    pass
