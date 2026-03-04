from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0001_user_profile'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Admin'),
                    ('dev', 'Dev'),
                    ('se', 'SE'),
                    ('guest', 'Guest'),
                ],
                default='guest',
                max_length=10,
                verbose_name='역할',
            ),
        ),
    ]
