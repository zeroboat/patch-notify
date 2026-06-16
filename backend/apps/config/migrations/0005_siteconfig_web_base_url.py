from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('config', '0004_remove_internal_slack_channel'),
    ]

    operations = [
        migrations.AddField(
            model_name='siteconfig',
            name='subscribe_base_url',
            field=models.CharField(
                blank=True,
                help_text='토큰 UUID 바로 앞까지의 URL. 예: https://yourdomain.com/subscriber/subscribe/  →  최종 URL: {입력값}{token}/',
                max_length=300,
                verbose_name='구독 페이지 URL',
            ),
        ),
    ]
