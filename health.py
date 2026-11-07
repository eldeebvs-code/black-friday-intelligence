"""Deduplicated failure/recovery alerts, and a user-visible daily receipt."""
from datetime import datetime, timedelta


def update_health(state, report, now, send, daily=True):
    health = state.setdefault('health', {})
    failures = sorted(p['store'] for p in report['providers'] if p['status'] != 'ok')
    if report['errors']:
        failures.append('notification/verification')
    signature = ','.join(failures)
    previous = health.get('signature', '')
    last = health.get('daily_at')
    due = daily and (not last or now - datetime.fromisoformat(last) >= timedelta(hours=24))
    if signature == previous and not due:
        return
    good = sum(p['status'] == 'ok' for p in report['providers'])
    text = ('حالة مراقب الأسعار: ' + ('توجد مصادر تحتاج مراجعة' if failures else 'المصادر المفعلة تعمل')
            + f"\nمصادر سليمة: {good}/{len(report['providers'])}"
            + (f"\nالمتأثر: {signature}" if failures else '')
            + '\nالفحص مجدول كل 15 دقيقة وقد يتأخر. تنبيه الخصم يُرسل فقط بعد التحقق.'
            + '\nالتغطية محدودة بالمصادر والنطاقات المعلنة، وليست كل مواقع مصر.'
            + '\nhttps://github.com/eldeebvs-code/black-friday-intelligence/actions')
    if send(text):
        health.update(signature=signature, daily_at=now.isoformat(timespec='seconds'))
