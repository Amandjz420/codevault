from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0002_add_github_repo_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='webhook_branch',
            field=models.CharField(
                blank=True,
                max_length=100,
                help_text='Branch to watch for webhook-triggered ingestion. Defaults to github_default_branch.',
            ),
        ),
    ]
