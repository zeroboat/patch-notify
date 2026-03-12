from django.db import migrations


def set_existing_translation_status(apps, schema_editor):
    """content_en이 있는 섹션이 하나라도 있으면 done으로 설정"""
    PatchNote = apps.get_model('patchnote', 'PatchNote')
    for note in PatchNote.objects.all():
        has_en = (
            note.features.filter(content_en__isnull=False).exists()
            or note.improvements.filter(content_en__isnull=False).exists()
            or note.bugfixes.filter(content_en__isnull=False).exists()
            or note.remarks.filter(content_en__isnull=False).exists()
        )
        if has_en:
            note.translation_status = 'done'
            note.save(update_fields=['translation_status'])


class Migration(migrations.Migration):

    dependencies = [
        ('patchnote', '0003_patchnote_translation_status'),
    ]

    operations = [
        migrations.RunPython(set_existing_translation_status, migrations.RunPython.noop),
    ]
