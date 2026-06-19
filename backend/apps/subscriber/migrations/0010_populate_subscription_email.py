from django.db import migrations


def copy_customer_emails(apps, schema_editor):
    CustomerEmail = apps.get_model('customer', 'CustomerEmail')
    SubscriptionEmail = apps.get_model('subscriber', 'SubscriptionEmail')
    objs = [
        SubscriptionEmail(customer_id=e.customer_id, email=e.email, name=e.name or '')
        for e in CustomerEmail.objects.all()
    ]
    SubscriptionEmail.objects.bulk_create(objs, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('subscriber', '0009_subscription_email'),
        ('customer', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(copy_customer_emails, migrations.RunPython.noop),
    ]
