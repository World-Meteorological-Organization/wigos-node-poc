from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("publishing", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(name="StationPublication"),
    ]
