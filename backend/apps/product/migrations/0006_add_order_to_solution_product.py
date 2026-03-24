from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0005_move_icon_to_solution'),
    ]

    operations = [
        migrations.AddField(
            model_name='solution',
            name='order',
            field=models.PositiveIntegerField(default=0, verbose_name='정렬 순서'),
        ),
        migrations.AddField(
            model_name='product',
            name='order',
            field=models.PositiveIntegerField(default=0, verbose_name='정렬 순서'),
        ),
        migrations.AlterModelOptions(
            name='solution',
            options={'ordering': ['order', 'id'], 'verbose_name': '솔루션', 'verbose_name_plural': '솔루션 목록'},
        ),
        migrations.AlterModelOptions(
            name='product',
            options={'ordering': ['order', 'platform', 'category'], 'verbose_name': '상세 제품', 'verbose_name_plural': '상세 제품 목록'},
        ),
    ]
