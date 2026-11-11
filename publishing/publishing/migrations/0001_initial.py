import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("api", "0013_drop_outbox"),
    ]

    operations = [
        migrations.CreateModel(
            name="StationPublication",
            fields=[
                (
                    "station",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="publication",
                        serialize=False,
                        to="api.station",
                    ),
                ),
                ("deliveries", models.JSONField(default=list)),
                ("error", models.TextField(blank=True)),
                ("finished_at", models.DateTimeField(null=True)),
            ],
        ),
    ]
