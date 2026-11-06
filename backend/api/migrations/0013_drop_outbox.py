from django.db import migrations


def forget_outbox(apps, schema_editor):
    """Its permissions go with the content types."""
    apps.get_model("contenttypes", "ContentType").objects.filter(app_label="outbox").delete()


class Migration(migrations.Migration):
    """The outbox app is gone, and its migrations with it. Past publication events
    aren't carried over. Can't be undone."""

    dependencies = [
        ("api", "0012_station_last_changed_by_publication_status"),
        ("auth", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunSQL("DROP TABLE IF EXISTS outbox_publicationevent", migrations.RunSQL.noop),
        migrations.RunSQL("DELETE FROM django_migrations WHERE app = 'outbox'", migrations.RunSQL.noop),
        migrations.RunPython(forget_outbox, migrations.RunPython.noop),
    ]
