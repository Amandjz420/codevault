import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0004_add_entity_description'),
        ('projects', '0003_add_webhook_branch'),
    ]

    operations = [
        migrations.CreateModel(
            name='WebhookEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('branch', models.CharField(max_length=255)),
                ('commit_sha', models.CharField(blank=True, max_length=40)),
                ('commit_message', models.TextField(blank=True)),
                ('pusher', models.CharField(blank=True, max_length=255)),
                ('changed_files', models.JSONField(blank=True, default=list)),
                ('deleted_files', models.JSONField(blank=True, default=list)),
                ('status', models.CharField(
                    choices=[('queued', 'Queued'), ('processed', 'Processed'), ('failed', 'Failed')],
                    default='queued',
                    max_length=20,
                )),
                ('celery_task_id', models.CharField(blank=True, max_length=255)),
                ('received_at', models.DateTimeField(auto_now_add=True)),
                ('project', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='webhook_events',
                    to='projects.project',
                )),
            ],
            options={
                'verbose_name': 'Webhook Event',
                'verbose_name_plural': 'Webhook Events',
                'db_table': 'intelligence_webhook_event',
                'ordering': ['-received_at'],
            },
        ),
    ]
