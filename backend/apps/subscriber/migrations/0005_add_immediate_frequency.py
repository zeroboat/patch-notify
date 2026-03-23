from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriber', '0004_subscription_product'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subscription',
            name='frequency',
            field=models.CharField(
                choices=[
                    ('immediate', '즉시'),
                    ('weekly', '매주'),
                    ('monthly', '매월'),
                    ('quarterly', '분기'),
                ],
                default='weekly',
                max_length=20,
                verbose_name='전달 주기',
            ),
        ),
    ]
