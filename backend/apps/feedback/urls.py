from django.urls import path
from . import views

urlpatterns = [
    path('', views.FeedbackListView.as_view(), name='feedback_list'),
    path('new/', views.feedback_create, name='feedback_create'),
    path('<int:pk>/', views.FeedbackDetailView.as_view(), name='feedback_detail'),
    path('<int:pk>/update/', views.feedback_update, name='feedback_update'),
    path('<int:pk>/delete/', views.feedback_delete, name='feedback_delete'),
    path('<int:pk>/status/', views.feedback_status_update, name='feedback_status_update'),
    path('<int:pk>/priority/', views.feedback_priority_update, name='feedback_priority_update'),
    path('<int:pk>/comment/', views.feedback_comment_create, name='feedback_comment_create'),
    path('<int:pk>/comment/<int:comment_pk>/delete/', views.feedback_comment_delete, name='feedback_comment_delete'),
]
