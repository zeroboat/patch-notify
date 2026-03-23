import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriber', '0003_add_monthly_frequency'),
        ('product', '0005_move_icon_to_solution'),
    ]

    operations = [
        # 기존 데이터 삭제 (solution → product 구조 변경)
        migrations.RunSQL("DELETE FROM subscriber_subscription;", migrations.RunSQL.noop),
        migrations.AlterUniqueTogether(
            name='subscription',
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name='subscription',
            name='solution',
        ),
        migrations.AddField(
            model_name='subscription',
            name='product',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='subscriptions',
                to='product.product',
                verbose_name='제품',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='subscription',
            unique_together={('customer', 'product', 'channel')},
        ),
        migrations.AlterModelOptions(
            name='subscription',
            options={
                'ordering': ['customer__name', 'product__solution__name', 'channel'],
                'verbose_name': '구독',
                'verbose_name_plural': '구독 목록',
            },
        ),
    ]
