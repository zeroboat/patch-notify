from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('customer', '0006_add_on_premise'),
        ('product', '0010_utility_has_download'),
        ('subscriber', '0010_populate_subscription_email'),
    ]

    operations = [
        migrations.CreateModel(
            name='UtilitySubscription',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_active', models.BooleanField(default=True, verbose_name='활성화')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='utility_subscriptions',
                    to='customer.customer',
                    verbose_name='고객사',
                )),
                ('utility', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='subscriptions',
                    to='product.utility',
                    verbose_name='유틸리티',
                )),
            ],
            options={
                'verbose_name': '유틸리티 구독',
                'verbose_name_plural': '유틸리티 구독 목록',
            },
        ),
        migrations.AlterUniqueTogether(
            name='utilitysubscription',
            unique_together={('customer', 'utility')},
        ),
        migrations.AddField(
            model_name='customersubscriptiontoken',
            name='url',
            field=models.CharField(blank=True, max_length=500, verbose_name='구독 페이지 URL'),
        ),
    ]
