from django.apps import AppConfig


class PatchnoteConfig(AppConfig):
    name = 'apps.patchnote'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import PatchNote, Feature, Improvement, BugFix, Remark, Internal, PatchNoteFile
        auditlog.register(PatchNote)
        auditlog.register(Feature)
        auditlog.register(Improvement)
        auditlog.register(BugFix)
        auditlog.register(Remark)
        auditlog.register(Internal)
        auditlog.register(PatchNoteFile)
