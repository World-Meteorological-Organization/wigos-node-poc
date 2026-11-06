from django.contrib.postgres.operations import CreateExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        # Leave whatever prior migration dependency was automatically listed here
    ]

    operations = [
        CreateExtension('postgis'), # This runs CREATE EXTENSION IF NOT EXISTS postgis;
    ]