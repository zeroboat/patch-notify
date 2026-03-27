from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('subscriber', '0006_alter_subscription_slack_channel'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='subscription',
            name='frequency',
        ),
    ]
