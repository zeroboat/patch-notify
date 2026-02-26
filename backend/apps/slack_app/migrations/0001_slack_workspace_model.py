from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('customer', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SlackWorkspace',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('team_id', models.CharField(max_length=50, unique=True, verbose_name='팀 ID')),
                ('team_name', models.CharField(max_length=200, verbose_name='워크스페이스명')),
                ('bot_token', models.CharField(max_length=500, verbose_name='Bot Token')),
                ('status', models.CharField(
                    choices=[('pending', '승인 대기'), ('approved', '승인됨'), ('rejected', '거부됨')],
                    default='pending',
                    max_length=20,
                    verbose_name='상태',
                )),
                ('customer', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='slack_workspaces',
                    to='customer.customer',
                    verbose_name='고객사',
                )),
            ],
            options={
                'verbose_name': 'Slack 워크스페이스',
                'verbose_name_plural': 'Slack 워크스페이스 목록',
            },
        ),
    ]
