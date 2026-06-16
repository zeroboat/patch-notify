from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('config', '0005_siteconfig_web_base_url'),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE config_siteconfig RENAME COLUMN web_base_url TO subscribe_base_url',
            reverse_sql='ALTER TABLE config_siteconfig RENAME COLUMN subscribe_base_url TO web_base_url',
            state_operations=[],  # Django 모델 상태는 이미 0005에서 subscribe_base_url로 반영됨
        ),
    ]
