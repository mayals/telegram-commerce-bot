import os
from celery import Celery

#  to start Celery  - in terminal use "celery -A core worker -l info --pool=solo"


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('core')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
